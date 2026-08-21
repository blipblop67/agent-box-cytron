"""
Covers templates (list -> use -> get a real flow back) and schedules (create
-> the in-process APScheduler actually fires it -> run history is recorded).
Mocks only the outbound LLM call. Run with: python3 tests/test_schedules_and_templates.py
"""
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-sched-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, scheduler  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()
scheduler.start()


class FakeLlmResponse:
    def __init__(self, content):
        self._content = content

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._content}}]}


def fake_llm_post(url, headers=None, json=None, **kwargs):
    return FakeLlmResponse(f"echo: {json['messages'][-1]['content']}")


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")  # first user -> admin

    client.put("/api/settings", headers=headers, json={
        "llm_provider": "openrouter", "openrouter_api_key": "test-key", "openrouter_model": "test/model",
    })

    # --- templates ---
    templates = client.get("/api/templates", headers=headers).json()
    assert len(templates) == 16, templates
    assert {t["id"] for t in templates} >= {"first-agent", "ask-your-documents", "quick-calculator", "notify-me-on-telegram"}
    print(f"[ok] {len(templates)} templates available")

    flow = client.post("/api/templates/first-agent/use", headers=headers, json={}).json()
    assert len(flow["graph"]["nodes"]) == 3
    assert flow["owner_id"] == "alex"
    print(f"[ok] instantiated template into flow {flow['id']} with {len(flow['graph']['nodes'])} nodes")

    with patch("httpx.post", side_effect=fake_llm_post):
        result = client.post(f"/api/flows/{flow['id']}/run", headers=headers, json={"input": "hello"})
    assert result.status_code == 200
    assert "echo: hello" in result.json()["output"]
    print("[ok] the templated flow actually runs")

    # --- schedules: validation ---
    bad = client.post(f"/api/flows/{flow['id']}/schedules", headers=headers, json={"trigger_type": "interval"})
    assert bad.status_code == 400
    print("[ok] rejects an interval schedule with no interval_minutes")

    bad2 = client.post(f"/api/flows/{flow['id']}/schedules", headers=headers, json={"trigger_type": "daily", "daily_time": "9am"})
    assert bad2.status_code == 400
    print("[ok] rejects a malformed daily_time")

    # --- schedules: create an interval schedule that fires almost immediately ---
    with patch("httpx.post", side_effect=fake_llm_post):
        created = client.post(
            f"/api/flows/{flow['id']}/schedules", headers=headers,
            json={"trigger_type": "interval", "interval_minutes": 1, "input_text": "scheduled run"},
        ).json()
        assert created["enabled"] is True
        assert created["last_run_at"] is None
        print(f"[ok] created schedule {created['id']} (every 1 min)")

        listed = client.get(f"/api/flows/{flow['id']}/schedules", headers=headers).json()
        assert len(listed) == 1
        print("[ok] schedule shows up when listing the flow's schedules")

        # force it to fire right now rather than waiting a full minute, to prove
        # the *running* scheduler (not just the DB row) picked up the new job
        job = scheduler._scheduler.get_job(created["id"])
        assert job is not None, "APScheduler never registered this job"
        job.modify(next_run_time=__import__("datetime").datetime.now(job.next_run_time.tzinfo))

        deadline = time.time() + 5
        runs = []
        while time.time() < deadline:
            runs = client.get(f"/api/schedules/{created['id']}/runs", headers=headers).json()
            if runs:
                break
            time.sleep(0.2)

    assert len(runs) == 1, "the scheduled job never actually ran"
    assert runs[0]["status"] == "success"
    assert "echo: scheduled run" in runs[0]["output"]
    print(f"[ok] the scheduler actually fired the job: \"{runs[0]['output']}\"")

    updated = client.get(f"/api/flows/{flow['id']}/schedules", headers=headers).json()[0]
    assert updated["last_run_status"] == "success"
    print("[ok] schedule row reflects the last run")

    # --- disabling a schedule removes it from the live scheduler ---
    client.patch(f"/api/schedules/{created['id']}", headers=headers, json={"enabled": False})
    assert scheduler._scheduler.get_job(created["id"]) is None
    print("[ok] disabling a schedule unregisters its APScheduler job")

    # --- non-owner, non-admin can't manage someone else's flow's schedule ---
    other_headers = auth_headers(client, "Sam")
    private_flow = client.post("/api/flows", headers=headers, json={"name": "Private", "visibility": "private"}).json()
    forbidden = client.post(
        f"/api/flows/{private_flow['id']}/schedules", headers=other_headers,
        json={"trigger_type": "daily", "daily_time": "09:00"},
    )
    assert forbidden.status_code == 403
    print("[ok] schedules respect the same private-flow access rules as everything else")

    client.delete(f"/api/schedules/{created['id']}", headers=headers)

    print("\nAll schedule/template smoke tests passed.")


if __name__ == "__main__":
    main()
