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
    {
        "id": "customer-support-assistant",
        "name": "Customer Support Assistant",
        "description": "Answers customer questions from your own docs, staying on-topic and admitting what it doesn't know. Upload your FAQ/help docs to a knowledge base first, then use Chat (not just Run) so it remembers earlier questions in the same conversation.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "kb", "type": "knowledge_base", "position": _pos(1), "data": {"kb_id": "", "top_k": 5}},
                {"id": "llm", "type": "llm", "position": _pos(2), "data": {
                    "system_prompt": (
                        "You are a customer support assistant. Answer using only the context provided. "
                        "Be warm but concise. If the context doesn't cover the question, say so plainly and "
                        "suggest they contact a human - never make up an answer."
                    ),
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
        "id": "product-recommendation-agent",
        "name": "Product Recommendation Agent",
        "description": "Recommends products from a catalog you upload (a CSV of products works well), asking about budget and preferences over a few messages. Use Chat, not Run - it needs to remember what the customer already told it.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "kb", "type": "knowledge_base", "position": _pos(1), "data": {"kb_id": "", "top_k": 6}},
                {"id": "llm", "type": "llm", "position": _pos(2), "data": {
                    "system_prompt": (
                        "You help customers pick a product from the catalog in the context. Ask a clarifying "
                        "question (budget, use case, preferences) if you don't have enough to recommend well; "
                        "otherwise recommend 1-3 specific options from the catalog and briefly say why."
                    ),
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
        "id": "meeting-summarizer",
        "name": "Meeting Summarizer",
        "description": "Turns a raw transcript into a short summary with decisions and action items. Paste the transcript directly, or in Chat use the 📎 attach button to pull the text out of an uploaded file - no need to build a whole knowledge base for a one-off document.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "llm", "type": "llm", "position": _pos(1), "data": {
                    "system_prompt": (
                        "Summarize this meeting transcript. Structure your reply as: a 2-3 sentence overview, "
                        "then 'Decisions' and 'Action items' as bullet lists (owner if mentioned). If something "
                        "isn't in the transcript, don't invent it."
                    ),
                }},
                {"id": "out", "type": "output", "position": _pos(3), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "llm"},
                {"id": "e2", "source": "llm", "target": "out"},
            ],
        },
    },
    {
        "id": "hr-policy-assistant",
        "name": "HR Policy Assistant",
        "description": "Answers questions about company policy from documents you upload (handbook, benefits guide, etc). Same pattern as Customer Support - upload docs to a knowledge base, then use Chat for follow-up questions.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "kb", "type": "knowledge_base", "position": _pos(1), "data": {"kb_id": "", "top_k": 5}},
                {"id": "llm", "type": "llm", "position": _pos(2), "data": {
                    "system_prompt": (
                        "You are an HR policy assistant. Answer using only the context provided, and quote or "
                        "reference the specific policy where relevant. If a question needs a judgment call "
                        "(disputes, terminations, legal questions), say this should go to an actual HR person "
                        "instead of answering it yourself."
                    ),
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
        "id": "research-assistant",
        "name": "Research Assistant",
        "description": "Searches the live web and synthesizes what it finds, with sources - for anything a static knowledge base can't answer because it needs current information. Needs a Tavily API key on the Settings page.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "search", "type": "web_search", "position": _pos(1), "data": {"max_results": 6}},
                {"id": "llm", "type": "llm", "position": _pos(2), "data": {
                    "system_prompt": (
                        "Synthesize the search results into a clear answer to the question. Cite sources by "
                        "URL inline. If the results disagree or are inconclusive, say so rather than picking "
                        "one arbitrarily."
                    ),
                }},
                {"id": "out", "type": "output", "position": _pos(3), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "search"},
                {"id": "e2", "source": "search", "target": "llm"},
                {"id": "e3", "source": "llm", "target": "out"},
            ],
        },
    },
    {
        "id": "technical-support-agent",
        "name": "Technical Support Agent",
        "description": "Walks someone through troubleshooting using your product docs/manuals - upload them to a knowledge base first. Use Chat so it remembers what's already been tried when the first suggestion doesn't fix it.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "kb", "type": "knowledge_base", "position": _pos(1), "data": {"kb_id": "", "top_k": 5}},
                {"id": "llm", "type": "llm", "position": _pos(2), "data": {
                    "system_prompt": (
                        "You are a technical support agent. Using the context, give the single most likely fix "
                        "first as clear numbered steps, not a wall of options. If the context doesn't cover the "
                        "issue, say so and suggest escalating rather than guessing."
                    ),
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
        "id": "student-learning-assistant",
        "name": "Student Learning Assistant",
        "description": "A tutor that explains concepts and checks understanding rather than just handing over answers. Genuinely needs Chat, not Run - tutoring only works as a back-and-forth.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "llm", "type": "llm", "position": _pos(1), "data": {
                    "system_prompt": (
                        "You are a patient tutor. Don't just give the final answer - explain the reasoning, "
                        "check understanding with a short question when it fits, and adjust your explanation "
                        "based on what the student says next. Encourage without being saccharine."
                    ),
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
        "id": "restaurant-recommendation-agent",
        "name": "Restaurant Recommendation Agent",
        "description": "Searches the web for current restaurant options and curates a short list - a static knowledge base can't cover this since restaurants open, close, and change hours. Needs a Tavily API key on the Settings page.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "search", "type": "web_search", "position": _pos(1), "data": {"max_results": 6}},
                {"id": "llm", "type": "llm", "position": _pos(2), "data": {
                    "system_prompt": (
                        "Recommend 3-5 restaurants from the search results that best match what was asked for "
                        "(cuisine, location, vibe, budget). Briefly say why each one fits. Don't recommend a "
                        "place the results don't actually support."
                    ),
                }},
                {"id": "out", "type": "output", "position": _pos(3), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "search"},
                {"id": "e2", "source": "search", "target": "llm"},
                {"id": "e3", "source": "llm", "target": "out"},
            ],
        },
    },
    {
        "id": "personal-productivity-coach",
        "name": "Personal Productivity Coach",
        "description": "An ongoing coach for goals and habits - remembers what you're working on from one check-in to the next, and pulls your upcoming calendar events as context for every message. Use Chat, and keep coming back to the same conversation rather than starting a new one each time. Set up a Google service account on the Settings page, then set the Calendar node's Impersonate field to your own address for the calendar awareness to work.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "cal", "type": "calendar", "position": _pos(1), "data": {"action": "list", "max_results": 5}},
                {"id": "llm", "type": "llm", "position": _pos(2), "data": {
                    "system_prompt": (
                        "You are a supportive but direct productivity coach. The context includes the "
                        "person's next few calendar events - use it where relevant (e.g. noting an "
                        "upcoming deadline or meeting) but don't force it into every reply. Help set "
                        "concrete, specific goals, follow up on ones mentioned earlier in the "
                        "conversation, and push back gently on vague plans ('be more productive') until "
                        "they're actionable."
                    ),
                }},
                {"id": "out", "type": "output", "position": _pos(3), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "cal"},
                {"id": "e2", "source": "cal", "target": "llm"},
                {"id": "e3", "source": "llm", "target": "out"},
            ],
        },
    },
    {
        "id": "youtube-video-idea-generator",
        "name": "YouTube Video Idea Generator",
        "description": "Searches YouTube for what's already been made on a topic - titles, channels, view counts - then proposes concrete new video ideas based on what's covered well, what's thin, and what's missing. Type a topic to get started. Needs a YouTube API key on the Settings page.",
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "yt", "type": "youtube", "position": _pos(1), "data": {"max_results": 10}},
                {"id": "llm", "type": "llm", "position": _pos(2), "data": {
                    "system_prompt": (
                        "You are a YouTube content strategist. The context is a list of existing videos "
                        "on this topic (title, channel, view count, description). Briefly note what's "
                        "already well covered (high view counts) versus thin or missing, then propose "
                        "5-8 concrete video ideas that fill a real gap - specific titles, not vague "
                        "categories. For each idea, say in one line why it's a gap based on what you see "
                        "in the context, not a generic reason."
                    ),
                }},
                {"id": "out", "type": "output", "position": _pos(3), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "yt"},
                {"id": "e2", "source": "yt", "target": "llm"},
                {"id": "e3", "source": "llm", "target": "out"},
            ],
        },
    },
    {
        "id": "sirim-coc-progress-tracker",
        "name": "SIRIM CoC Progress Tracker",
        "description": (
            "Reads certification-related emails, figures out what changed for each application, "
            "and keeps a Google Sheet up to date - updating the existing row for an application it's "
            "already tracking instead of adding a duplicate. Tracks the details that actually matter "
            "for staying on top of a real certification pipeline: which stage each application is at, "
            "who the SIRIM officer is, what's due and when, and priority so nothing urgent gets missed "
            "in a long list. One-time setup needed: run this once with the Sheets node's action "
            "switched to \"Create a new spreadsheet\" (title is enough - the headers below are filled "
            "in automatically, styled and frozen), copy the spreadsheet ID it returns, then switch the "
            "node back to \"Update a row\" and paste that ID in. After that, put this flow on a "
            "Schedule (e.g. every few hours) for a tracker that keeps itself current. Needs a Google "
            "service account set up on the Settings page, with both this flow's Email and Sheets nodes "
            "pointed at whoever's inbox you're tracking via their Impersonate field - adjust the Email "
            "node's search query to match how certification emails actually show up in that inbox."
        ),
        "graph": {
            "nodes": [
                {"id": "in", "type": "input", "position": _pos(0), "data": {}},
                {"id": "email", "type": "email", "position": _pos(1), "data": {
                    "action": "search",
                    "query": "SIRIM OR \"CoC\" OR \"certificate of conformance\" OR \"certificate of conformity\"",
                    "max_results": 15,
                }},
                {"id": "llm", "type": "llm", "position": _pos(2), "data": {
                    "system_prompt": (
                        "You track SIRIM CoC (Certificate of Conformance) certification applications "
                        "from email updates. The context is a set of recent emails - some may not be "
                        "about a certification at all, ignore those.\n\n"
                        "For each email that IS about a CoC application, extract these 9 fields, in "
                        "this exact order:\n\n"
                        "1. Application Ref - the SIRIM reference/application/job number if the email "
                        "states one, otherwise a short stable identifier from the product or company "
                        "name. Reuse the exact same identifier every time the same application comes "
                        "up, so updates land on the same tracker row instead of creating a duplicate.\n"
                        "2. Product / Model - what's being certified (product name and model number "
                        "together, e.g. \"Smart Plug SP-200\"). Leave blank if not mentioned.\n"
                        "3. Status - exactly one of: Submitted, Under review, Sample requested, Testing "
                        "in progress, Action required, Payment pending, Final evaluation, Certificate "
                        "issued, Rejected, Expired. Pick whichever best matches where things stand after "
                        "this email.\n"
                        "4. Scheme - exactly one of: Type Approval, Special Approval, Modular Approval, "
                        "CIDB Certification, Safety & EMC, Unspecified (use Unspecified if the email "
                        "doesn't say).\n"
                        "5. Officer - the SIRIM/certification officer's name and email if mentioned "
                        "(e.g. \"Ahmad Faizal <ahmad@sirim.my>\"), otherwise blank.\n"
                        "6. Target Deadline - a date if one is stated or clearly implied by an SLA "
                        "(e.g. \"2026-09-15\"), otherwise blank.\n"
                        "7. Pending Action - what's needed next and who owns it, prefixed with urgency "
                        "in brackets: [Critical], [High], [Medium], or [Low]. E.g. \"[High] Applicant: "
                        "submit revised test report\". Use \"[Low] None - awaiting SIRIM\" if the ball "
                        "is entirely in SIRIM's court with nothing for the applicant to do.\n"
                        "8. Certificate No - the issued certificate number, only once actually issued, "
                        "otherwise blank.\n"
                        "9. Notes - one short sentence of context that doesn't fit the fields above.\n\n"
                        "Output ONLY the update lines, one per application, pipe-separated in exactly "
                        "that field order, and nothing else - no headers, no commentary, no markdown:\n"
                        "ref | product | status | scheme | officer | deadline | action | certificate | notes\n\n"
                        "If a field is genuinely unknown, leave it blank between the pipes rather than "
                        "guessing or writing \"N/A\" - but always include all 9 fields, even when several "
                        "are blank.\n\n"
                        "If none of the emails are about a CoC application, output exactly: NONE"
                    ),
                }},
                {"id": "sheets", "type": "sheets", "position": _pos(3), "data": {
                    "action": "upsert_row", "spreadsheet_id": "", "sheet_name": "Sheet1",
                    "headers": "Application Ref, Product / Model, Status, Scheme, Officer, Target Deadline, Pending Action, Certificate No, Notes",
                }},
                {"id": "out", "type": "output", "position": _pos(4), "data": {}},
            ],
            "edges": [
                {"id": "e1", "source": "in", "target": "email"},
                {"id": "e2", "source": "email", "target": "llm"},
                {"id": "e3", "source": "llm", "target": "sheets"},
                {"id": "e4", "source": "sheets", "target": "out"},
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
