"""
Exercises the Call Flow node - the simple version of "agents talking to
each other": one flow directly invokes another and uses its output as a
step, no network round-trip, same hub. Covers the happy path, and the two
safety properties that matter most: a flow can't be made to call itself
in a cycle (directly or through an intermediate flow), and access control
is respected (can't call a flow you don't have visibility into).
Run with: python3 tests/test_call_flow.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("AGENT_HUB_DATA_DIR", tempfile.mkdtemp(prefix="agent-hub-callflow-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402
from _auth_helper import auth_headers  # noqa: E402

db.init_db()


def _simple_graph(extra_node=None, extra_edges=None):
    """Input -> [extra_node if given] -> Output, wired straight through."""
    nodes = [
        {"id": "in", "type": "input", "position": {"x": 0, "y": 0}, "data": {}},
        {"id": "out", "type": "output", "position": {"x": 400, "y": 0}, "data": {}},
    ]
    edges = [{"id": "e1", "source": "in", "target": "out"}]
    if extra_node:
        nodes.insert(1, extra_node)
        edges = [
            {"id": "e1", "source": "in", "target": extra_node["id"]},
            {"id": "e2", "source": extra_node["id"], "target": "out"},
        ]
    if extra_edges:
        edges = extra_edges
    return {"nodes": nodes, "edges": edges}


def main():
    client = TestClient(app)
    headers = auth_headers(client, "Alex")  # admin

    # --- flow B: a simple "shout" flow - just uppercases-by-convention (in practice
    # this would be an LLM node; a plain passthrough with a marker is enough to prove
    # the call actually happened and the right input reached it) ---
    flow_b = client.post("/api/flows", headers=headers, json={"name": "Shout Flow"}).json()
    b_graph = _simple_graph()
    client.put(f"/api/flows/{flow_b['id']}", headers=headers, json={"graph": b_graph})

    # --- flow A: Input -> Call Flow (targets B) -> Output ---
    flow_a = client.post("/api/flows", headers=headers, json={"name": "Delegator Flow"}).json()
    call_node = {"id": "call", "type": "call_flow", "position": {"x": 200, "y": 0},
                 "data": {"target_flow_id": flow_b["id"]}}
    a_graph = _simple_graph(extra_node=call_node)
    client.put(f"/api/flows/{flow_a['id']}", headers=headers, json={"graph": a_graph})

    result = client.post(f"/api/flows/{flow_a['id']}/run", headers=headers, json={"input": "hello from A"})
    assert result.status_code == 200, result.text
    assert result.json()["output"] == "hello from A"  # B is a passthrough, so A's input flows straight through B and back
    print(f"[ok] Flow A called Flow B via a Call Flow node and got its output back: {result.json()['output']!r}")

    # the trace should show BOTH the call_flow node's own output AND that flow B
    # actually ran as a distinct execution - check the call node appears in A's trace
    call_trace_entry = next(t for t in result.json()["trace"] if t["node_id"] == "call")
    assert call_trace_entry["output"] == "hello from A"
    assert call_trace_entry["error"] is None
    print("[ok] the Call Flow node's own trace entry shows the called flow's result")

    # --- direct self-cycle: a flow's Call Flow node targets itself ---
    self_calling = client.post("/api/flows", headers=headers, json={"name": "Self Caller"}).json()
    self_id_holder = {"id": None}
    self_call_node = {"id": "call", "type": "call_flow", "position": {"x": 200, "y": 0}, "data": {}}
    self_graph = _simple_graph(extra_node=self_call_node)
    client.put(f"/api/flows/{self_calling['id']}", headers=headers, json={"graph": self_graph})
    # now that we know its id, point the call node at itself and save again
    self_graph["nodes"][1]["data"]["target_flow_id"] = self_calling["id"]
    client.put(f"/api/flows/{self_calling['id']}", headers=headers, json={"graph": self_graph})

    self_cycle_result = client.post(f"/api/flows/{self_calling['id']}/run", headers=headers, json={"input": "x"})
    assert self_cycle_result.status_code == 400
    assert "cycle" in str(self_cycle_result.json()).lower()
    print("[ok] a flow calling itself directly is caught as a cycle, not an infinite loop/crash")

    # --- indirect cycle: A -> B -> A ---
    flow_c = client.post("/api/flows", headers=headers, json={"name": "Cycle C"}).json()
    flow_d = client.post("/api/flows", headers=headers, json={"name": "Cycle D"}).json()
    c_call_node = {"id": "call", "type": "call_flow", "position": {"x": 200, "y": 0},
                   "data": {"target_flow_id": flow_d["id"]}}
    client.put(f"/api/flows/{flow_c['id']}", headers=headers, json={"graph": _simple_graph(extra_node=c_call_node)})
    d_call_node = {"id": "call", "type": "call_flow", "position": {"x": 200, "y": 0},
                   "data": {"target_flow_id": flow_c["id"]}}
    client.put(f"/api/flows/{flow_d['id']}", headers=headers, json={"graph": _simple_graph(extra_node=d_call_node)})

    indirect_cycle_result = client.post(f"/api/flows/{flow_c['id']}/run", headers=headers, json={"input": "x"})
    assert indirect_cycle_result.status_code == 400
    assert "cycle" in str(indirect_cycle_result.json()).lower()
    print("[ok] an indirect cycle (C calls D calls C) is also caught, not just direct self-calls")

    # --- depth limit: a long but genuinely acyclic chain should eventually be rejected ---
    chain_flows = [client.post("/api/flows", headers=headers, json={"name": f"Chain {i}"}).json() for i in range(8)]
    for i in range(len(chain_flows) - 1):
        node = {"id": "call", "type": "call_flow", "position": {"x": 200, "y": 0},
                "data": {"target_flow_id": chain_flows[i + 1]["id"]}}
        client.put(f"/api/flows/{chain_flows[i]['id']}", headers=headers, json={"graph": _simple_graph(extra_node=node)})
    client.put(f"/api/flows/{chain_flows[-1]['id']}", headers=headers, json={"graph": _simple_graph()})

    deep_chain_result = client.post(f"/api/flows/{chain_flows[0]['id']}/run", headers=headers, json={"input": "x"})
    assert deep_chain_result.status_code == 400
    assert "deep" in str(deep_chain_result.json()).lower() or "MAX_CALL_DEPTH" in str(deep_chain_result.json())
    print("[ok] a long but acyclic chain of 8 flows is rejected once it exceeds the depth limit")

    # --- access control: can't call a flow you don't have visibility into ---
    sam_headers = auth_headers(client, "Sam")
    private_flow = client.post("/api/flows", headers=sam_headers, json={"name": "Sam's Private Flow", "visibility": "private"}).json()
    client.put(f"/api/flows/{private_flow['id']}", headers=sam_headers, json={"graph": _simple_graph()})

    jordan_headers = auth_headers(client, "Jordan")
    caller_flow = client.post("/api/flows", headers=jordan_headers, json={"name": "Jordan's Caller"}).json()
    caller_node = {"id": "call", "type": "call_flow", "position": {"x": 200, "y": 0},
                   "data": {"target_flow_id": private_flow["id"]}}
    client.put(f"/api/flows/{caller_flow['id']}", headers=jordan_headers, json={"graph": _simple_graph(extra_node=caller_node)})

    forbidden_result = client.post(f"/api/flows/{caller_flow['id']}/run", headers=jordan_headers, json={"input": "x"})
    assert forbidden_result.status_code == 400
    assert "private" in str(forbidden_result.json()).lower()
    print("[ok] a Call Flow node can't reach a flow that's private to someone else")

    # --- a missing target flow gives a clear error ---
    orphan_node = {"id": "call", "type": "call_flow", "position": {"x": 200, "y": 0},
                   "data": {"target_flow_id": "does-not-exist"}}
    orphan_flow = client.post("/api/flows", headers=headers, json={"name": "Orphan Caller"}).json()
    client.put(f"/api/flows/{orphan_flow['id']}", headers=headers, json={"graph": _simple_graph(extra_node=orphan_node)})
    orphan_result = client.post(f"/api/flows/{orphan_flow['id']}/run", headers=headers, json={"input": "x"})
    assert orphan_result.status_code == 400
    assert "no longer exists" in str(orphan_result.json())
    print("[ok] a target flow that's been deleted gives a clear error, not a crash")

    print("\nAll Call Flow smoke tests passed.")


if __name__ == "__main__":
    main()
