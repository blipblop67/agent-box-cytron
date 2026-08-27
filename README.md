# Agent Hub

Build and run AI agents on your own hardware - a visual flow builder, RAG
over your own documents, Gmail/Drive tools, and a hub-wide choice of
OpenRouter or a local Ollama model, all running on a Raspberry Pi 5.

**Setting this up for someone to actually use — yourself, a team, a
customer?** Start with [`GETTING_STARTED.md`](GETTING_STARTED.md) instead
of this file - a complete walkthrough from "nothing installed" to a
working team, written for the person using the product rather than the
person maintaining its code. What follows below is the technical/developer
reference: architecture, design rationale, and where to find things in
the codebase.

```
agent-hub/
├── backend/    FastAPI app - flow engine, RAG, Gmail/Drive, scheduler, API
├── frontend/   React flow-builder UI
└── deploy/     Everything needed to run this on a Raspberry Pi 5, including
                on every future boot - start here
```

## Getting this running

**On a Raspberry Pi 5** (the intended target): see
[`deploy/README.md`](deploy/README.md) - one script handles building the
frontend, setting up the backend, and installing it as a service that starts
on boot.

**Locally, for development**: see [`backend/README.md`](backend/README.md)
and [`frontend/README.md`](frontend/README.md) - run the backend with
`uvicorn`, the frontend with `npm run dev`, and Vite proxies API calls
between them.

## What's actually in each piece

- **`backend/`** - a plain FastAPI app (no LangChain, no agent framework, no
  ORM) with SQLite for metadata, Chroma for vectors, and `httpx` for every
  outbound call (LLM providers, Gmail, Drive). Read `backend/README.md`'s
  "Design notes" section for the reasoning behind those choices - most of
  them trade a little convenience for staying readable to someone learning
  how the system works, which matters for a product meant to teach this.
- **`frontend/`** - React + `@xyflow/react` for the canvas, Tailwind for
  styling, `zustand` for state. A dark, PCB-inspired look (copper + signal
  green) rather than a generic AI-product gradient, since this is literally
  running on the board it's styled after.
- **`deploy/`** - a `systemd` unit and an install script that sets up both
  halves and enables the service, so the hub survives reboots without anyone
  SSHing back in.

## Status

Everything through templates and scheduling from the original build plan is
in place and covered by the test suites in `backend/tests/`, plus a
Telegram connection (bot token + chat linking, no Google Cloud setup
needed) alongside Gmail and Drive, a self-update feature (Settings →
Software updates: point at a GitHub repo you control, check, and apply -
all from the browser, with user data structurally outside anything an
update touches), real password authentication (bcrypt, server-side
sessions, admin password reset and removal - not the name-only stub earlier
versions of this project used), per-person credentials (anyone can set
their own OpenRouter key on the Account page, which takes priority over
the hub-wide default for that person only - Google has no per-person
setting, it's one hub-wide service account), and three
capabilities added specifically to close the gap between "can build a flow"
and "can build the kind of assistant people actually ask for": conversation
memory (Chat, not just Run - a flow remembers earlier turns), a web search
node (Tavily-backed, for anything needing current information), and one-off
document input (attach a file to a chat message without building a
permanent knowledge base for it). Nine ready-to-use templates - customer
support, product recommendations, meeting summaries, HR policy Q&A,
research, technical support, tutoring, restaurant recommendations, and
productivity coaching - put these together as concrete starting points.
Two more rounds landed since: LLM output renders as real markdown and math
(bold, tables, code blocks, LaTeX formulas via KaTeX) everywhere it's shown,
instead of showing literal `**`/`$...$` syntax; Telegram bots became a
named, shared-or-private resource like a knowledge base rather than one
connection per person, so different flows can message through entirely
different bots regardless of who runs them; and any flow can be published
with an API key for an external website/script to call with no login at
all. That last one came out of a deliberate comparison against Langflow
(the established open-source visual-flow competitor) - see
`backend/README.md`'s design notes for what that comparison found worth
adopting (a flow callable as an API), what's a bigger lift worth queuing
(MCP export, branching), and what Langflow does that's deliberately absent
here, including a real 2026 CVE in Langflow rooted in exactly the
auth-optional-by-default and raw-code-execution patterns this project
avoided from the start. Most recently: Google Calendar joined Gmail/Drive
as a third Google integration (list or create events; the Personal
Productivity Coach template pulls upcoming events as context for every
check-in), and a YouTube search node (API-key-based, like web search, not
tied to any one identity) powers a new
YouTube Video Idea Generator template that searches a topic and proposes
concrete new videos based on what's already covered. Building Calendar
surfaced a real, pre-existing bug affecting every tool-then-LLM template:
the LLM only ever saw a tool's raw output, silently losing whatever the
person actually asked - fixed and regression-tested, see the design notes.
Most recently: Telegram bots can now trigger a flow automatically -
message a connected bot and a background job (polling every 3 seconds,
not a webhook, since a Pi on a home network usually has no stable public
URL) runs the flow and replies with no one needing to click Run or be near
the hub, with the same conversation memory Chat already uses so it's a
real back-and-forth, not one-shot answers. Since then: a `reset_password.py`
CLI tool for the genuinely-locked-out case (forgot the only admin's
password, no recovery email set, no SMTP configured) - a local-shell
recovery path, not a web endpoint, since anyone with shell access to the
hub's machine already has full access to the database file itself; and, on
top of that, a real self-service "Forgot password?" flow in the browser -
an optional recovery email per person, admin-configured outgoing SMTP, and
a single-use emailed link, verified end-to-end through an actual browser
against an actual running server (not just backend tests) by capturing the
real email content, extracting the real link from it, and completing a
real login with the new password. Also fixed a real bug in
`deploy/windows-run.ps1`: it was binding to `127.0.0.1` (localhost-only),
which would silently block every other device on the same Wi-Fi from
reaching the hub - now binds to `0.0.0.0` and prints the LAN IP to use from
another device on startup. Any team member (not just admins) can also
check for and apply software updates now, and set their own personal Web
search/YouTube keys the same way they already could for the LLM key.
Most recently: a genuine Google Sheets integration, not just a bigger
Drive node - a Sheets node can create a spreadsheet, read it, or upsert a
row (find by a key in the first column, update that row in place, or
append if it's new), which is what makes an actual progress tracker
possible rather than only ever overwriting a whole file. The SIRIM CoC
Progress Tracker template is built on this: reads certification-related
emails, extracts what changed for each application, and keeps a
spreadsheet current without duplicating rows - verified with a full
realistic simulation (plausible SIRIM emails in, correct tracker rows out,
a second run with only irrelevant email content correctly doing nothing).
Known gaps are listed at the bottom of `backend/README.md` and
`frontend/README.md` - mainly: no email verification step when someone
sets a recovery email (trusted at face value), Gmail/Drive still have no
event-based trigger (only Telegram, and only time-based Schedules
otherwise), the Sheets node has no spreadsheet picker (paste an ID by
hand) and writes plain values only (no formatting or formulas), and flows
are DAGs without branching logic yet.
