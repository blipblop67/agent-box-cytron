"""
Executes a saved flow graph node-by-node in topological order. Deliberately
simple: each node consumes the (concatenated) text output of its predecessors
and produces its own text output for whatever comes next - a single "message"
moving through the graph, the same mental model as n8n/Langflow's basic mode.

This is the "flow node" path described in the hub's design notes: deterministic
and inspectable one node at a time, so the trace this returns can show someone
learning the system exactly what happened at each step, not just a final answer.
"""
from . import calculator, db, drive_client, gmail_client, hub_settings, llm_provider, telegram_client, \
    telegram_tokens, vector_store, web_search_client
from .embeddings import get_embedding_provider


class FlowError(Exception):
    def __init__(self, node_id: str, message: str):
        self.node_id = node_id
        super().__init__(message)


def _topological_order(nodes: list[dict], edges: list[dict]) -> list[str]:
    node_ids = [n["id"] for n in nodes]
    incoming: dict[str, list[str]] = {nid: [] for nid in node_ids}
    outgoing: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for e in edges:
        outgoing[e["source"]].append(e["target"])
        incoming[e["target"]].append(e["source"])

    in_degree = {nid: len(incoming[nid]) for nid in node_ids}
    ready = [nid for nid in node_ids if in_degree[nid] == 0]
    order: list[str] = []
    while ready:
        # stable order: always take the earliest-declared ready node, so a run
        # is reproducible rather than depending on set/dict iteration order
        ready.sort(key=node_ids.index)
        nid = ready.pop(0)
        order.append(nid)
        for nxt in outgoing[nid]:
            in_degree[nxt] -= 1
            if in_degree[nxt] == 0:
                ready.append(nxt)

    if len(order) != len(node_ids):
        raise FlowError("", "The flow has a cycle, or a node with no path from Input - check the wiring")
    return order


def run_flow(graph: dict, run_input: str, user_id: str, history: list[dict] | None = None) -> dict:
    """`history`, when given, is prior turns of a conversation
    ([{"role": "user"|"assistant", "content": ...}, ...]) - every LLM node in
    the flow gets it prepended to its own messages, so a flow run through a
    Conversation (see conversation_routes.py) remembers earlier turns instead
    of treating each message as a one-off, the way a plain Run does."""
    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    edges = graph.get("edges", [])
    if not nodes:
        raise FlowError("", "This flow has no nodes yet - add at least an Input and an Output")

    incoming: dict[str, list[str]] = {nid: [] for nid in nodes}
    for e in edges:
        incoming[e["target"]].append(e["source"])

    order = _topological_order(list(nodes.values()), edges)

    outputs: dict[str, str] = {}
    trace = []
    final_output = None

    for node_id in order:
        node = nodes[node_id]
        node_type = node["type"]
        data = node.get("data", {})

        predecessor_ids = incoming[node_id]
        node_input = "\n\n".join(outputs[p] for p in predecessor_ids if p in outputs)

        try:
            output = _execute_node(node_type, data, node_input, run_input, user_id, history)
        except Exception as exc:  # noqa: BLE001 - surface any tool/LLM failure into the trace
            trace.append({"node_id": node_id, "type": node_type, "input": node_input,
                          "output": None, "error": str(exc)})
            raise FlowError(node_id, str(exc)) from exc

        outputs[node_id] = output
        trace.append({"node_id": node_id, "type": node_type, "input": node_input, "output": output, "error": None})
        if node_type == "output":
            final_output = output

    if final_output is None:
        final_output = outputs[order[-1]] if order else ""
    return {"output": final_output, "trace": trace}


def _execute_node(node_type: str, data: dict, node_input: str, run_input: str, user_id: str,
                   history: list[dict] | None = None) -> str:
    if node_type == "input":
        return run_input

    if node_type == "llm":
        messages = []
        if data.get("system_prompt"):
            messages.append({"role": "system", "content": data["system_prompt"]})
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": node_input or run_input})
        return llm_provider.chat_completion(
            messages, model=data.get("model") or None, provider=data.get("provider") or None, user_id=user_id,
        )

    if node_type == "web_search":
        return _execute_web_search_node(data, node_input, run_input)

    if node_type == "knowledge_base":
        kb_id = data.get("kb_id")
        if not kb_id:
            raise ValueError("This Knowledge base node has no knowledge base selected")
        kb = db.get_kb(kb_id)
        if kb is None:
            raise ValueError("The selected knowledge base no longer exists")
        query_text = node_input or run_input
        provider = get_embedding_provider()
        [query_vector] = provider.embed([query_text])
        results = vector_store.query(kb_id, query_vector, data.get("top_k") or 5)
        if not results:
            return "(no matching chunks found in this knowledge base)"
        return "\n\n".join(f"[{r['filename']}] {r['text']}" for r in results)

    if node_type == "calculator":
        expression = data.get("expression") or node_input or run_input
        return str(calculator.evaluate(expression))

    if node_type == "email":
        return _execute_email_node(data, node_input, run_input, user_id)

    if node_type == "drive":
        return _execute_drive_node(data, node_input, run_input, user_id)

    if node_type == "telegram":
        return _execute_telegram_node(data, node_input, run_input)

    if node_type == "output":
        return node_input or run_input

    raise ValueError(f"Unknown node type '{node_type}'")


def _execute_email_node(data: dict, node_input: str, run_input: str, user_id: str) -> str:
    action = data.get("action", "send")
    if action == "send":
        to = data.get("to")
        if not to:
            raise ValueError("This Email node has no recipient configured")
        subject = data.get("subject") or "(no subject)"
        body = node_input or data.get("body") or run_input
        result = gmail_client.send_email(user_id, to=to, subject=subject, body=body)
        return f"Sent to {to} (message id: {result.get('id')})"
    if action == "search":
        query = data.get("query") or node_input or run_input
        messages = gmail_client.list_messages(user_id, query=query, max_results=data.get("max_results") or 5)
        if not messages:
            return "(no matching emails found)"
        return "\n\n".join(f"From {m['from']} - {m['subject']}\n{m['snippet']}" for m in messages)
    raise ValueError(f"Unknown email action '{action}'")


def _execute_drive_node(data: dict, node_input: str, run_input: str, user_id: str) -> str:
    action = data.get("action", "list")
    if action == "list":
        search = data.get("search") or node_input or run_input
        files = drive_client.list_files(user_id, search=search, max_results=data.get("max_results") or 10)
        if not files:
            return "(no matching files found)"
        return "\n".join(f"{f['name']} ({f['mimeType']}) - id: {f['id']}" for f in files)
    if action == "read":
        file_id = data.get("file_id")
        if not file_id:
            raise ValueError("This Drive node has no file selected to read")
        result = drive_client.read_file_content(user_id, file_id)
        return result["content"]
    if action == "create":
        name = data.get("name") or "agent-output.txt"
        content = node_input or data.get("content") or run_input
        result = drive_client.create_file(user_id, name=name, content=content,
                                           mime_type=data.get("mime_type") or "text/plain")
        return f"Created '{result['name']}' (id: {result['id']})"
    raise ValueError(f"Unknown drive action '{action}'")


def _execute_telegram_node(data: dict, node_input: str, run_input: str) -> str:
    bot_id = data.get("bot_id")
    if not bot_id:
        raise ValueError("This Telegram node has no bot selected")
    bot = db.get_telegram_bot(bot_id)
    if bot is None:
        raise ValueError("The selected bot no longer exists")
    creds = telegram_tokens.get_credentials(bot_id)
    if creds is None or creds["chat_id"] is None:
        raise ValueError(f"'{bot['name']}' isn't fully linked yet - see the Connections page")

    action = data.get("action", "send")
    if action == "send":
        text = node_input or data.get("message") or run_input
        telegram_client.send_message(creds["bot_token"], creds["chat_id"], text)
        return f"Sent via {bot['name']} ({creds['bot_username']})"
    if action == "read":
        messages = telegram_client.get_recent_messages(
            creds["bot_token"], creds["chat_id"], limit=data.get("max_results") or 10,
        )
        if not messages:
            return "(no recent messages)"
        return "\n".join(f"{m['from']}: {m['text']}" for m in messages)
    raise ValueError(f"Unknown telegram action '{action}'")


def _execute_web_search_node(data: dict, node_input: str, run_input: str) -> str:
    api_key = hub_settings.get_web_search_api_key()
    if not api_key:
        raise ValueError("Web search isn't configured yet - add a Tavily API key on the Settings page")
    query = data.get("query") or node_input or run_input
    if not query:
        raise ValueError("This Web search node has nothing to search for")
    results = web_search_client.search(api_key, query, max_results=data.get("max_results") or 5)
    if not results:
        return "(no results found)"
    return "\n\n".join(f"[{r['title']}]({r['url']})\n{r['content']}" for r in results)
