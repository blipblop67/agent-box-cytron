# Agent Hub — backend

The FastAPI backend for the agent hub: the flow engine, the LLM provider
abstraction (OpenRouter or Ollama), RAG over your own documents, and Gmail /
Drive tool integrations. Pairs with the React frontend in
`../frontend`, which this app serves as static files once built.

## What it does

- **Real accounts** — name + password, bcrypt-hashed, session tokens, not a
  name-only stub. First person to register becomes admin. An admin can reset
  anyone's password; anyone can change their own (`app/security.py`,
  `app/auth_routes.py`)
- **Flows** — save a graph of nodes (Input, LLM, Knowledge base, Email,
  Drive, Calculator, Output), then run it and get back the final output plus
  a step-by-step trace of what each node did
- **Templates** — a small library of pre-built flows (`app/templates.py`)
  someone can clone into their own flow in one click, graded roughly by
  complexity so they double as an onboarding curriculum
- **Schedules** — a flow doesn't have to wait for someone to click Run; an
  admin-less background scheduler (`app/scheduler.py`, APScheduler under the
  hood) can run it every N minutes or once a day, with a history of what
  each scheduled run did
- **LLM provider** — a hub-wide default (Settings page) picks OpenRouter or
  Ollama; anyone can set their **own** OpenRouter key and preferred model on
  the Account page, which wins for flows they personally run
  (`app/llm_provider.py`, `app/user_settings.py`)
- **Knowledge bases** — upload PDF / DOCX / CSV / TXT / MD files, they get
  chunked, embedded, and stored locally (Chroma); a Knowledge base node
  searches them at run time
- **Gmail** — each team member connects their own account, through either
  the hub's shared Google app (Settings) or their **own** Google app
  (Account page) if they'd rather not trust the admin's OAuth client; send,
  search, and reply from an Email node
- **Drive** — same per-person connection, same personal-app option; list,
  read (including native Docs/Sheets/Slides), and create files from a Drive node
- **Telegram** — each team member connects their own bot (no Google Cloud
  setup needed, just a token from @BotFather); send or read messages from a
  Telegram node - a good fit for notifications
- **Self-updates** — an admin points the hub at a GitHub repo/branch from
  the Settings page; "Check for updates" compares against what's installed,
  "Update now" downloads, rebuilds, and restarts - all from the browser, no
  SSH needed. User data lives entirely outside the code directory this
  touches, so it's untouched by design, not by care (`app/updater.py`)
- **Calculator** — evaluates a math expression safely (no `eval()`)
- Knowledge bases, flows, and Gmail/Drive connections are all **per-person**,
  with shared-vs-private visibility and admin oversight, for a small team
  sharing one hub

## Quickstart

**Deploying to an actual Raspberry Pi 5?** See `deploy/README.md` for the
full walkthrough (flashing the OS, the install script, systemd, Gmail/Drive
redirect URIs). What follows below is the quick local/dev version.

```bash
pip install -r requirements.txt --break-system-packages   # drop the flag on a normal venv
uvicorn app.main:app --host 0.0.0.0 --port 8811
```

Open `http://<pi-hostname>.local:8811` for the UI (once the frontend's been
built into `app/static` — see `../frontend/README.md`), or
`http://<pi-hostname>.local:8811/docs` for interactive API docs.

Run the offline smoke tests any time (no network / real credentials needed —
each test mocks the relevant Google/LLM/embedding calls):

```bash
python3 tests/test_pipeline.py   # RAG: upload -> chunk -> embed -> query
python3 tests/test_gmail.py      # Gmail: connect -> send -> list -> read -> reply
python3 tests/test_drive.py      # Drive: connect -> list -> read -> create -> update
python3 tests/test_flows.py      # Flows: settings -> build a graph -> run it -> trace
python3 tests/test_schedules_and_templates.py   # Templates -> a real scheduled run firing
python3 tests/test_telegram.py   # Telegram: connect a bot -> link a chat -> send -> read
python3 tests/test_google_settings.py   # Gmail/Drive credentials configured entirely via the Settings UI
python3 tests/test_updater.py    # Self-update: swap in new code, prove a flow created beforehand survives
python3 tests/test_auth.py       # Register/login/lockout/claim-old-account/password reset & change
python3 tests/test_personal_settings.py   # Personal Google app / OpenRouter key take priority over hub-wide
```

## Team accounts and admin

The **first person** to hit the hub becomes its admin automatically (same
bootstrap pattern most self-hosted single-box apps use — Nextcloud, Home
Assistant, etc.). An admin can promote or demote anyone via the Team page
(`PATCH /api/users/{id}/role?role=admin`), can see/reach every private
knowledge base and flow on the hub, and is the only one who can change the
hub-wide LLM provider settings.

## Configuration (environment variables)

| Variable | Default | What it does |
|---|---|---|
| `AGENT_HUB_DATA_DIR` | `~/.agent-hub` | Where uploads, the SQLite DB, the vector index, and the encryption key live |
| `EMBEDDING_PROVIDER` | `local` | `local` (on-device ONNX model, no GPU needed) or `ollama` |
| `LOCAL_EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5` | Only used when `EMBEDDING_PROVIDER=local` |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Only used when `EMBEDDING_PROVIDER=ollama` |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | Model name Ollama should embed with |
| `RAG_CHUNK_SIZE` / `RAG_CHUNK_OVERLAP` | `800` / `120` | Characters per chunk / overlap between chunks |
| `RAG_DEFAULT_TOP_K` | `5` | Chunks returned per query if the caller doesn't specify |
| `RAG_MAX_UPLOAD_MB` | `50` | Upload size limit |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | — | Optional fallback - the Settings page is the intended way to set these now, and always takes priority if both are set |

The **LLM provider** (OpenRouter API key/model, or Ollama base URL/model)
and the **Google OAuth client** (Gmail/Drive) aren't environment variables -
both are set at runtime by a hub admin on the Settings page, stored in
SQLite, with secrets encrypted using the same vault as OAuth tokens. This is
deliberate: these are the settings a non-technical admin should be able to
change without SSHing into the Pi or opening a config file, and Google
credentials in particular take effect immediately - no restart, since
`google_oauth.py` reads them fresh on every request rather than caching them
at startup.

On first real request with `EMBEDDING_PROVIDER=local`, `fastembed` downloads
the small model (~130MB for `bge-small`) and caches it — needs internet once,
then works fully offline.

### Setting up Gmail + Drive (one-time, per deployment)

All of this happens from the **Settings** page in the app now - no config
file to open. Four steps, not two - the first and last are easy to miss and
are the most common reason connecting fails:

1. In [Google Cloud Console](https://console.cloud.google.com), create a
   project.
2. **Enable the APIs**: APIs & Services → Library → search for and enable
   both **Gmail API** and **Google Drive API**. Creating OAuth credentials
   without this step lets someone connect, but every actual send/list/read
   call then fails.
3. Configure the **OAuth consent screen**: User Type "External" (unless you
   have Google Workspace), fill in the required fields. While it's in
   **Testing** mode (the default, and fine for a small team), Google will
   silently refuse to let anyone sign in who isn't listed under **Test
   users** on that same page - add every team member's Google account there.
   This is far and away the most common cause of "I click Connect and it
   just fails."
4. Create **one** OAuth client ID (Credentials → Create Credentials → OAuth
   client ID → type "Web application") — Gmail and Drive share it. The
   Settings page shows the exact two redirect URIs to add here (they're
   derived from however you're currently reaching the hub, so they're always
   right - a "Copy" button sits next to each one).
5. Paste the client ID and secret into the Settings page and hit Save -
   takes effect immediately, no restart. (An admin who'd rather set these
   via `.env`/environment variables instead still can - see the
   configuration table above - but the Settings page always wins if both
   are set.)
6. Each team member connects from the Connections page. The first time,
   Google shows an "unverified app" warning - that's expected for a personal
   project not submitted for Google's review; click **Advanced → Go to
   (app name)** to proceed.

If a connection attempt does fail, it now lands on a page explaining the
likely cause (`app/oauth_errors.py`) instead of a bare error - that's the
first place to look.

### Setting up Telegram (per person, no cloud console needed)

No project or credentials to set up - each person creates their own bot:

1. In Telegram, message **@BotFather**, send `/newbot`, and follow the
   prompts. It replies with a token that looks like `123456789:AA...`.
2. On the Connections page, paste that token in and save - the hub verifies
   it immediately against Telegram's API.
3. Open a chat with the new bot (search for the username BotFather gave you)
   and send it any message.
4. Back on the Connections page, click "Finish linking" - the hub looks at
   the bot's most recent message to find which chat to talk back to.

A Telegram node can then send or read messages from that same chat.

## Self-updates

Settings → Software updates: point the hub at a GitHub repo (`owner/repo`)
and branch you control - typically your own fork or copy of this project.
"Check for updates" compares the latest commit on that branch against what's
installed; "Update now" downloads it, reinstalls Python dependencies,
rebuilds the frontend, swaps the new code in, and restarts - a few minutes,
entirely from the browser.

**Why this is safe to leave data alone about**: `AGENT_HUB_DATA_DIR` (the
SQLite database, uploaded documents, vector index) lives outside
`backend/` and `frontend/` entirely - by default in `~/.agent-hub`, nowhere
near the code directories an update touches. This isn't a precaution the
update code takes; it's a directory it never has a reason to look in.
`tests/test_updater.py` proves this concretely: it creates a flow, applies a
(mocked) update, and asserts the flow is still there afterward via the API.

**Why a failed update can't brick the hub**: everything risky - downloading
the tarball, extracting it, checking it actually looks like this project,
reinstalling dependencies, rebuilding the frontend - happens in a temp
staging directory first. The live installation is only touched in the final
step, which is just a few directory moves. If anything upstream fails, that
step never runs.

**The one thing that isn't automatic**: restarting only happens if the hub
detects it's running under `systemd` (checking for the `INVOCATION_ID`
environment variable systemd sets on every unit it manages) - which is true
on a Pi set up via `deploy/install.sh`, and not true if you're running it
manually (`uvicorn ...` in a terminal, or `windows-run.ps1`). In the second
case, the update still installs, you just need to restart it yourself
(Ctrl+C, then re-run).

**If an update goes wrong**: the previous `backend/app` is kept as
`backend/app/../app.bak` (one slot, overwritten each update, not a full
history). Manual rollback: stop the hub, `rm -rf backend/app && mv backend/app.bak backend/app`, start it again.

**Worth knowing**: this executes whatever's on the branch you point it at -
same as `git pull && restart` would. It's meant for a repo you control, not
a third party's. GitHub's API also rate-limits unauthenticated requests to
60/hour, which "Check for updates" uses one of - a non-issue for occasional
manual checks, but not something to poll aggressively.

## Auth

Real password auth, not a stub: `POST /api/auth/authenticate` combines
login and registration behind one call - a name the hub hasn't seen creates
an account (bcrypt-hashed password), a name it has verifies the password.
First person to register becomes admin, same bootstrap as before. A session
is an opaque random token (`app/security.py`), stored server-side with a
30-day expiry, sent back as `Authorization: Bearer <token>`.

A few things worth knowing:

- **Upgrading from before passwords existed**: if you have an existing hub
  with name-only accounts, the first time each name "registers" with a
  password, it *claims* that existing account (same id, same role, same
  flows) rather than erroring or creating a duplicate. Nothing else to do.
- **Login is rate-limited** per name (5 failed attempts / 5 minutes,
  in-memory - resets on restart), not per-IP, since a LAN often shares one
  IP across everyone.
- **Password hashes never leave the backend** - `routes.py`'s `_user_out`
  is the one place that decides what's safe to return from `list_users()`.
- **An admin can reset anyone's password** (Team page /
  `PATCH /api/users/{id}/password`) - useful since there's no email-based
  reset flow. Self-service change is on the Account page
  (`POST /api/auth/change-password`); both invalidate every existing
  session for that user, forcing a fresh login with the new password.

## How a flow actually runs

`app/flow_engine.py` topologically sorts the saved graph and executes each
node once, passing a single text "message" from node to node (the same
mental model as n8n/Langflow's basic mode - deterministic and inspectable,
not an autonomous agent deciding what to call). Every node type is a small,
readable function:

```
POST /api/flows/{flow_id}/run
{ "input": "whatever the Input node should receive" }
→ { "output": "...", "trace": [{"node_id", "type", "input", "output", "error"}, ...] }
```

The trace is what the Run panel in the UI renders step by step - the point
is that someone learning the system can see exactly what happened at each
node, not just a final answer.

## Design notes / why it's built this way

- **Sessions are opaque random tokens in a database table, not JWTs.**
  Revoking one (logout, password change, admin reset) is a `DELETE`, not a
  denylist you have to maintain alongside a stateless token scheme - simpler
  to reason about for a single-process hub, at the cost of one DB lookup per
  request, which is not the bottleneck here.
- **Login and registration are one endpoint** (`POST /api/auth/authenticate`):
  a name the hub hasn't seen creates an account, one it has checks the
  password. Mirrors the old "just type a name" UX as closely as a real auth
  system can, including the one-time path for claiming a pre-password
  account without losing its id/role/history.
- **Per-user credentials resolve through one function each**
  (`user_settings.resolve_google_credentials`,
  `user_settings.resolve_openrouter_credentials`) that every caller goes
  through - `google_oauth.py`'s functions take `client_id`/`client_secret`
  as plain arguments rather than looking anything up themselves, so there's
  exactly one place that decides "personal, or fall back to hub-wide."
- **No LangChain/LlamaIndex, no google-api-python-client, no agent
  framework.** Chunking is ~30 readable lines (`app/chunking.py`), the flow
  engine is one file you can read top to bottom (`app/flow_engine.py`), and
  Gmail/Drive/LLM calls are plain REST via `httpx`. Since part of the product
  is teaching people how this stuff works, frameworks that hide the
  mechanism work against the goal - and it keeps the dependency footprint
  lighter on a Pi.
- **One LLM client for both providers** (`app/llm_provider.py`): Ollama
  exposes an OpenAI-compatible `/v1/chat/completions` endpoint and
  OpenRouter is fully OpenAI-compatible too, so switching providers is just
  `base_url` + API key + model name.
- **`fastembed` over `sentence-transformers`.** No PyTorch dependency, ONNX
  runtime only — meaningfully lighter and faster to start on a Pi 5 CPU.
- **One Chroma collection per knowledge base**, not one big collection
  filtered by KB id. Makes delete-a-KB and per-KB stats trivial, and access
  control never has to leak into vector queries.
- **`google_oauth.py` / `google_tokens.py` are provider-agnostic.** Gmail and
  Drive are each a thin ~20-line wrapper (their own scopes + redirect URI)
  over shared connect/refresh/store logic — adding a third Google product
  later (Calendar, say) is mostly copying one of those wrappers.
- **Drive write access defaults to the narrower `drive.file` scope**, not
  full `drive` — the hub can create files and edit ones it created, but can't
  silently modify a pre-existing document it never touched. Broaden the scope
  in `drive_oauth.py` if a team needs to edit arbitrary existing files.
- **Calculator uses `simpleeval`, never `eval()`.** Once an expression can
  contain arbitrary agent/LLM output, raw `eval()` is a code-execution hole.
- **Every Google/LLM API call re-refreshes/re-authenticates per request**
  rather than caching until near-expiry. A little extra HTTP traffic, in
  exchange for not tracking expiry timestamps or clock skew — a reasonable
  trade for a first version.
- **Two schedule types, not raw cron** (`app/scheduler.py`): "every N minutes"
  and "daily at HH:MM" cover the overwhelming majority of what someone
  building their first agent actually wants, without asking a newcomer to
  learn cron syntax. `BackgroundScheduler`, not `AsyncIOScheduler` - the job
  function is synchronous blocking I/O (same `flow_engine.run_flow` a manual
  Run uses), so it belongs in its own thread rather than requiring an asyncio
  event loop.
- **Templates are just graphs, not a special flow type** (`app/templates.py`):
  "using" one clones its `graph_json` into a brand new flow the person owns.
  No live link back to the template, no separate code path to maintain.
- **The updater stages everything before touching anything** (`app/updater.py`):
  download, extract, and validate happen in a temp directory; dependency
  install and the frontend build run against that staged copy; only the
  final swap touches the live `backend/app`. Restart relies on
  `Restart=always` in the systemd unit plus a self-triggered exit, detected
  via the `INVOCATION_ID` env var systemd sets - no `sudo systemctl restart`
  needed from inside a web-facing process, which would've been a much bigger
  privilege-escalation surface for not much benefit.
- **OAuth failures render a page explaining what went wrong**
  (`app/oauth_errors.py`), not a raw 500 or a 422 for a "missing" `code`
  parameter. That second case isn't an edge case - it's exactly what happens
  every time someone hits Cancel, or isn't an approved test user yet, since
  Google redirects back with `?error=...` and no code at all.
- **The Gmail/Drive redirect URI is derived from the request, not
  configured** (`google_oauth.redirect_uri_for`). It's whatever host/port
  someone is actually using to reach the hub when they click Connect -
  nothing to keep in sync if the hub is reachable by more than one hostname
  (`agenthub.local` and a raw IP, say), as long as every one actually used
  is also registered in Google Cloud Console. The Settings page shows the
  live computed value so there's something exact to copy in.
- **`config.py` loads `backend/.env` itself** (via `python-dotenv`) rather
  than relying on the OS to inject it - `.env` files "just working" on
  Windows the same way they do on Linux/systemd was worth a two-line
  dependency.
- **Telegram reuses the Gmail/Drive credential table and vault**, even
  though it's a bot token, not an OAuth refresh token - same shape
  (`user_id`, `provider`, an encrypted secret, a human-readable label), one
  less table to reason about. Connecting is two steps (save the token, then
  link a chat by messaging the bot once) because unlike Google's OAuth
  redirect, there's no other way for the hub to learn which Telegram chat
  belongs to which hub user.
- **Plain `sqlite3`, no ORM.** A single Pi is a single writer; this stays easy
  to read for someone learning the codebase, and easy to swap later if a
  future multi-hub/cloud-sync feature ever needs it.

## Not done yet (natural next slices)

- Email-based password reset (an admin resetting a teammate's password from
  the Team page is the only recovery path right now - no "forgot password"
  self-service flow, since that needs outbound email the hub doesn't send)
- Two-factor auth / passkeys - password-only for now
- Delete-file-from-disk cleanup when a document row is deleted (currently
  leaves the raw upload on disk even after the DB row and vectors are gone)
- IMAP/SMTP fallback for non-Gmail email providers
- Rate limiting on `/documents` uploads
- A `PATCH` endpoint to rename a knowledge base or change its visibility
- Webhook-style triggers (e.g. "run when a new email arrives") - schedules
  cover time-based triggers; event-based ones would need either polling or a
  push mechanism from Gmail/Drive/Telegram (Telegram in particular could move
  to a webhook instead of the `getUpdates` polling `telegram_client.py` uses
  now, once the hub has a stable public URL)
- Branching/conditional logic in a flow, and a true "autonomous agent" node
  (LLM decides which tools to call, vs. the deterministic wiring flows use today)
- A GitHub token option for the updater (private repos, and GitHub's 60/hour
  unauthenticated rate limit)
- An update history/changelog view beyond the single `app.bak` rollback slot
