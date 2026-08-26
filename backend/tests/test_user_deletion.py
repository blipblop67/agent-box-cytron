"""
Covers admin deleting a team member: only an admin can do it, you can't
remove yourself this way, and - the part most likely to silently break -
their shared/private flows and knowledge bases survive by transferring to
whoever removed them, rather than erroring out on a foreign key or vanishing.

Also directly unit-tests the "can't leave the hub with zero admins" guard.
Note this specific rule is currently unreachable through the API alone
(only an admin can call this endpoint, and an admin can't remove themself
via it either, so between those two checks the hub can never actually reach
zero admins) - it's deliberate defense-in-depth for if either of those two
checks ever changes, so it's tested at the function level instead of trying
to force an impossible HTTP scenario.

Run with: python3 tests/test_user_deletion.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-userdel-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db, embeddings  # noqa: E402
from app.main import app  # noqa: E402
from app.routes import _would_remove_last_admin  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


class FakeEmbeddingProvider:
    def embed(self, texts):
        return [[0.1] * 8 for _ in texts]


embeddings.set_embedding_provider(FakeEmbeddingProvider())


def main():
    client = TestClient(app)
    admin_headers = auth_headers(client, "Alex")  # first user -> admin
    sam_headers = auth_headers(client, "Sam")

    # --- a non-admin can't delete anyone ---
    forbidden = client.delete("/api/users/sam", headers=sam_headers)
    assert forbidden.status_code == 403
    print("[ok] a non-admin can't delete team members")

    # --- admin can't remove themselves via this endpoint ---
    self_delete = client.delete("/api/users/alex", headers=admin_headers)
    assert self_delete.status_code == 400
    print("[ok] an admin can't remove their own account this way")

    # --- Sam creates a shared flow, a private KB, and uploads a document ---
    flow = client.post("/api/flows", headers=sam_headers, json={"name": "Sam's shared flow", "visibility": "shared"}).json()
    kb = client.post("/api/knowledge-bases", headers=sam_headers, json={"name": "Sam's KB", "visibility": "private"}).json()
    files = {"file": ("notes.txt", "some notes from Sam", "text/plain")}
    doc = client.post(f"/api/knowledge-bases/{kb['id']}/documents", files=files, headers=sam_headers).json()
    print(f"[ok] Sam created a flow ({flow['id']}), a KB ({kb['id']}), and uploaded a document ({doc['id']})")

    # --- admin removes Sam ---
    deleted = client.delete("/api/users/sam", headers=admin_headers)
    assert deleted.status_code == 200, deleted.text
    print("[ok] admin removed Sam")

    # --- Sam is really gone ---
    team = client.get("/api/users", headers=admin_headers).json()
    assert not any(u["id"] == "sam" for u in team)
    # since the account is gone, this now registers a BRAND NEW "Sam" rather than logging in as the old one
    relogin_attempt = client.post("/api/auth/authenticate", json={"name": "Sam", "password": "brand-new-password"})
    assert relogin_attempt.status_code == 200
    assert relogin_attempt.json()["user"]["role"] == "member"
    print("[ok] the deleted account is really gone - a new registration under the same name starts fresh")

    # --- but Sam's flow, KB, and document all survived, now owned by the admin ---
    flow_after = client.get(f"/api/flows/{flow['id']}", headers=admin_headers).json()
    assert flow_after["owner_id"] == "alex"
    print("[ok] Sam's shared flow survived and transferred to the admin")

    kbs_after = client.get("/api/knowledge-bases", headers=admin_headers).json()
    matching_kb = next(k for k in kbs_after if k["id"] == kb["id"])
    assert matching_kb["owner_id"] == "alex"
    print("[ok] Sam's private KB survived and transferred to the admin")

    docs_after = client.get(f"/api/knowledge-bases/{kb['id']}/documents", headers=admin_headers).json()
    assert any(d["id"] == doc["id"] and d["uploaded_by"] == "alex" for d in docs_after)
    print("[ok] Sam's uploaded document survived with reassigned uploader")

    # --- two admins: one can remove the other, leaving exactly one ---
    priya_member_headers = auth_headers(client, "Priya")
    client.patch("/api/users/priya/role?role=admin", headers=admin_headers)
    priya_headers = auth_headers(client, "Priya")
    remove_alex = client.delete("/api/users/alex", headers=priya_headers)
    assert remove_alex.status_code == 200
    remaining = [u for u in client.get("/api/users", headers=priya_headers).json() if u["role"] == "admin"]
    assert len(remaining) == 1 and remaining[0]["id"] == "priya"
    print("[ok] with two admins, one can remove the other, leaving exactly one")

    # --- direct unit test of the underlying "would this leave zero admins" guard ---
    assert _would_remove_last_admin("priya", "admin") is True  # priya is the only admin left
    assert _would_remove_last_admin("jordan", "member") is False  # deleting a non-admin never counts
    client.patch("/api/users/priya/role?role=admin", headers=priya_headers)  # no-op, still just priya
    auth_headers(client, "Jordan")
    client.patch("/api/users/jordan/role?role=admin", headers=priya_headers)
    assert _would_remove_last_admin("priya", "admin") is False  # jordan is also admin now, so this is safe
    print("[ok] the zero-admins guard itself is correct")

    # --- demoting the last admin is blocked too, not just deleting them - both paths
    # to zero admins use the same guard now ---
    client.patch("/api/users/jordan/role?role=member", headers=priya_headers)  # back to one admin: priya
    demote_last_admin = client.patch("/api/users/priya/role?role=member", headers=priya_headers)
    assert demote_last_admin.status_code == 400
    assert "only admin" in demote_last_admin.text
    still_admin = [u for u in client.get("/api/users", headers=priya_headers).json() if u["id"] == "priya"][0]
    assert still_admin["role"] == "admin"  # unchanged
    print("[ok] demoting the only admin is blocked the same way deleting them is")

    print("\nAll user-deletion smoke tests passed.")


if __name__ == "__main__":
    main()
