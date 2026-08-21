# Agent Hub

Build and run AI agents on your own hardware - a visual flow builder, RAG
over your own documents, Gmail/Drive tools, and a hub-wide choice of
OpenRouter or a local Ollama model, all running on a Raspberry Pi 5.

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
sessions, admin password reset - not the name-only stub earlier versions of
this project used), and per-person credentials (anyone can set their own
Google OAuth app or OpenRouter key on the Account page, which take priority
over the hub-wide defaults for that person only). Known gaps are listed at
the bottom of `backend/README.md` and `frontend/README.md` - mainly: no
email-based "forgot password" flow (admin reset is the recovery path),
no event-based/webhook trigger (only time-based schedules), and flows are
DAGs without branching logic yet.
