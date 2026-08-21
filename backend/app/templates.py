"""
Pre-built flow blueprints. Each one is a working flow a newcomer can open,
run, and pick apart - a much gentler on-ramp than a blank canvas, and since
they're graded roughly by complexity, they double as a curriculum: template
1 teaches "a flow is Input -> something -> Output", template 2 adds a tool,
and so on.

"Using" a template just clones its graph into a brand new flow the person
owns - it's a starting point, not a live link back to this list.
"""

def _pos(i: int) -> dict:
    return {"x": 80 + i * 280, "y": 160}


TEMPLATES = [
    {
        "id": "first-agent",
        "name": "Your first agent",
        "description": "The simplest possible flow: whatever you type goes straight to a model, and its reply comes back out.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "llm", "type": "llm", "position": _pos(1), "data": {
                    "system_prompt": "You are a friendly, concise assistant.",
                }},
                {"id": "out", "type": "output", "position": _pos(2), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "llm"},
                {"id": "e2", "source": "llm", "target": "out"},
            ],
        },
    },
    {
        "id": "ask-your-documents",
        "name": "Ask your documents",
        "description": "Adds a Knowledge base node before the model, so answers are grounded in files you've uploaded instead of the model's general knowledge.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "kb", "type": "knowledge_base", "position": _pos(1), "data": {"kb_id": "", "top_k": 5}},
                {"id": "llm", "type": "llm", "position": _pos(2), "data": {
                    "system_prompt": "Answer the question using only the context provided. If the context doesn't cover it, say so plainly.",
                }},
                {"id": "out", "type": "output", "position": _pos(3), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "kb"},
                {"id": "e2", "source": "kb", "target": "llm"},
                {"id": "e3", "source": "llm", "target": "out"},
            ],
        },
    },
    {
        "id": "quick-calculator",
        "name": "Quick calculator",
        "description": "No model involved at all - just a deterministic tool node evaluating whatever expression you type in.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "calc", "type": "calculator", "position": _pos(1), "data": {}},
                {"id": "out", "type": "output", "position": _pos(2), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "calc"},
                {"id": "e2", "source": "calc", "target": "out"},
            ],
        },
    },
    {
        "id": "inbox-digest",
        "name": "Inbox digest",
        "description": "Searches your inbox for matching emails, then asks a model to summarize what it finds - a good template for a daily-schedule flow.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "email", "type": "email", "position": _pos(1), "data": {
                    "action": "search", "max_results": 10,
                }},
                {"id": "llm", "type": "llm", "position": _pos(2), "data": {
                    "system_prompt": "Summarize these emails in a short bulleted digest, grouping similar ones together.",
                }},
                {"id": "out", "type": "output", "position": _pos(3), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "email"},
                {"id": "e2", "source": "email", "target": "llm"},
                {"id": "e3", "source": "llm", "target": "out"},
            ],
        },
    },
    {
        "id": "save-notes-to-drive",
        "name": "Save notes to Drive",
        "description": "Cleans up whatever text you paste in with a model, then saves the result as a new file in your Drive - chaining a model into a tool.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "llm", "type": "llm", "position": _pos(1), "data": {
                    "system_prompt": "Tidy up this text into clear, well-organized notes. Fix typos, add headings where useful. Return only the notes.",
                }},
                {"id": "drive", "type": "drive", "position": _pos(2), "data": {
                    "action": "create", "name": "notes.txt", "mime_type": "text/plain",
                }},
                {"id": "out", "type": "output", "position": _pos(3), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "llm"},
                {"id": "e2", "source": "llm", "target": "drive"},
                {"id": "e3", "source": "drive", "target": "out"},
            ],
        },
    },
    {
        "id": "notify-me-on-telegram",
        "name": "Notify me on Telegram",
        "description": "Tidies up whatever you type with a model, then sends the result straight to your phone via Telegram - a good one to put on a schedule.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "llm", "type": "llm", "position": _pos(1), "data": {
                    "system_prompt": "Rewrite this as a short, friendly notification - one or two sentences, no preamble.",
                }},
                {"id": "telegram", "type": "telegram", "position": _pos(2), "data": {"action": "send"}},
                {"id": "out", "type": "output", "position": _pos(3), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "llm"},
                {"id": "e2", "source": "llm", "target": "telegram"},
                {"id": "e3", "source": "telegram", "target": "out"},
            ],
        },
    },
]

_BY_ID = {t["id"]: t for t in TEMPLATES}


def list_templates() -> list[dict]:
    return [
        {"id": t["id"], "name": t["name"], "description": t["description"], "node_count": len(t["graph"]["nodes"])}
        for t in TEMPLATES
    ]


def get_template(template_id: str) -> dict | None:
    return _BY_ID.get(template_id)
