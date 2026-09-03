# Agent Hub — backend

The FastAPI backend for the agent hub: the flow engine, the LLM provider
abstraction (OpenRouter or Ollama), RAG over your own documents, and Gmail /
Drive tool integrations. Pairs with the React frontend in
`../frontend`, which this app serves as static files once built.

## What it does

- **Real accounts** — name + password, bcrypt-hashed, session tokens, not a
  name-only stub. First person to register becomes admin. An admin can reset
  anyone's password or remove someone from the team; anyone can change their
  own password (`app/security.py`, `app/auth_routes.py`). "Forgot password?"
  on the login screen is self-service too, if the person set a recovery
  email on their Account page and an admin's configured outgoing email
  (Settings → Outgoing email) - a single-use, hour-long link, the same
  pattern any real app uses, not a plaintext password mailed around
  (`app/email_sender.py`). No recovery email set, or no SMTP configured?
  An admin resets it from the Team page - or if the only admin is the one
  locked out, `backend/reset_password.py` from a terminal (see the Auth
  section below)
- **Flows** — save a graph of nodes (Input, LLM, Knowledge base, Web search,
  Email, Drive, Telegram, Calculator, Output), then run it and get back the
  final output plus a step-by-step trace of what each node did
- **Conversations** — a flow run through Chat (not Run) remembers earlier
  turns: every LLM node gets the conversation so far prepended, so a
  Customer Support Assistant or coaching agent can actually hold a
  back-and-forth instead of treating every message as a fresh one-shot.
  Personal per-user, like chat history, even on a flow the whole team shares
  (`app/conversation_routes.py`, `flow_engine.run_flow`'s `history` param)
- **Web search** — a Web search node backed by Tavily (a free-tier search
  API built for feeding LLMs), for anything that needs current information a
  static knowledge base can't provide - a Research Assistant, a restaurant
  recommendation agent. Hub-wide key on Settings, or anyone can set their
  own on the Account page - same personal-overrides-hub-wide pattern as the
  LLM key and Google app, so a team member without admin rights isn't
  stuck if nobody's configured one for the whole team
  (`app/web_search_client.py`)
- **YouTube search** — a YouTube node backed by the YouTube Data API v3
  (a plain API key, not a Google login - searching YouTube's public catalog
  isn't "acting as" anyone). Returns titles, channels, descriptions, and
  view counts, so an LLM node after it can reason about what's already
  covered on a topic before proposing something new. The YouTube Video
  Idea Generator template is built on exactly this: search a topic, then
  get concrete new video ideas based on the gaps in what's already out
  there. Same personal-key option as Web search above
  (`app/youtube_client.py`)
- **One-off document input** — `POST /api/extract-text` pulls the text out
  of an uploaded PDF/DOCX/CSV/TXT/MD without creating a permanent searchable
  Knowledge base entry, for something like "summarize this transcript" where
  you don't want it indexed forever - wired into Chat's attach button
- **Templates** — a library of pre-built flows (`app/templates.py`) someone
  can clone into their own flow in one click, including nine ready to go for
  common agent use cases (customer support, product recommendations, meeting
  summaries, HR policy Q&A, research, technical support, tutoring, restaurant
  recommendations, productivity coaching)
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
- **Gmail** — send, search, and reply from an Email node, authenticated
  through the hub's one Google service account (Settings) rather than a
  personal login - no browser consent screen, no per-person "Connect"
  step. Leave a node's **Impersonate** field blank and it acts as the
  service account itself (no real inbox by default - a Workspace admin
  would need to have provisioned one); set it to a real address in your
  Google Workspace to act as that specific person's Gmail instead, which
  needs a Workspace super admin to authorize this service account for
  domain-wide delegation once
- **Drive** — same service account, same **Impersonate** field; list,
  read (including native Docs/Sheets/Slides), and create files from a
  Drive node. Left unimpersonated, files land in the service account's
  own Drive space, or wherever's been explicitly shared with its email
  address - a completely normal way to give an agent its own dedicated
  storage without tying it to any one person's account
- **Calendar** — list upcoming events or create new ones from a Calendar
  node, same auth model. The Personal Productivity Coach template uses
  this to pull your next few events as context for every check-in
- **Sheets** — genuine spreadsheet editing, not just file overwrite: a
  Sheets node can create a spreadsheet, read it, or upsert a row - find a
  row by matching its first column against a key, update that row in
  place, or append a new one if the key hasn't been seen before. This is
  what makes a real progress tracker possible (the SIRIM CoC Progress
  Tracker template is built on exactly this): the same application gets
  its row updated as it moves through stages, not duplicated on every
  check. A single run can update several rows at once (one per line of the
  previous node's output), since one email check will often touch more
  than one thing being tracked (`app/sheets_client.py`)
- **Telegram** — named bots (shared or private, same model as knowledge
  bases), not one connection per person: create as many as you want (just a
  token from @BotFather, no Google Cloud setup), and each Telegram node in a
  flow picks which one to use - a Customer Support flow and a Sales flow can
  message through two entirely different bots regardless of who runs them
- **Call Flow** — one agent using another as a tool: a node that runs a
  different flow and hands back its final output, the same way an Email
  or Sheets node hands back whatever it produced. Useful for a router
  flow that delegates to whichever specialist fits the request, or
  reusing one flow as a building block inside several others rather than
  duplicating its logic. The called flow always starts fresh (no shared
  conversation memory), and a flow can't call itself into a cycle -
  direct or indirect - or nest more than 5 levels deep
  (`flow_engine.run_flow`'s `call_stack`/`MAX_CALL_DEPTH`)
- **MCP** — a node that calls a tool on any external MCP (Model Context
  Protocol) server, the same kind of server Claude Desktop or Claude.ai
  connects to. "List tools" on the config panel discovers what a server
  offers and shows each tool's schema, so an LLM node just before it can
  be prompted to produce arguments in the right shape; a tool that only
  takes one plain argument works with un-structured text input too, no
  JSON required. Hand-rolled JSON-RPC client (`mcp_client.py`), not the
  official SDK - same reasoning as every other integration in this
  codebase
- **Publishing a flow also makes it an MCP server** - the same API key
  that unlocks the plain REST publish endpoint also works as a Bearer
  token against `/api/public/flows/{id}/mcp`, a real JSON-RPC 2.0
  endpoint (`initialize`, `notifications/initialized`, `tools/list`,
  `tools/call`) exposing exactly one tool, `run_flow`. Not a separate
  feature to opt into - publish once, reachable both ways. This is what
  makes the MCP node capable of reaching another Agent Hub flow, not just
  third-party servers: point one at another flow's own published MCP URL
  and it's indistinguishable from any other MCP tool call. Verified with
  a genuine end-to-end proof, not just a mocked one - `mcp_client.py`
  calling a real, independently running Agent Hub server process over an
  actual network connection, confirmed correct on both the list and call
  paths
- **Telegram triggers** — wire a flow to a bot (the "Telegram" button in
  the flow editor) and it answers messages automatically: a background job
  checks every few seconds, runs the flow with the same conversation memory
  Chat uses, and sends the reply back - no session, no clicking Run, not
  needing to be anywhere near the hub. This is what makes a Telegram bot
  usable as an actual assistant instead of only something a flow can
  proactively message (`app/telegram_poller.py`)
- **Free remote domain (DuckDNS)** — optional, admin-configurable in
  Settings, for networks where `.local` resolution doesn't work (some
  guest Wi-Fi, some routers). Paste a free DuckDNS token and subdomain,
  and a background job (same pattern as the Telegram poller, every 5
  minutes) keeps that domain pointed at the hub's current LAN IP, so it
  survives a DHCP renewal without anyone noticing. Entirely unrelated to
  Google - a service account has no redirect URI to worry about, so
  nothing about Google integration depends on what hostname or IP the
  hub is reachable at (`app/dynamic_dns.py`)
- **Self-updates** — an admin points the hub at a GitHub repo/branch from
  the Settings page (that part stays admin-only - it decides which code
  the hub trusts). "Check for updates" and "Update now" themselves are
  open to anyone on the team, not just admins - compares against what's
  installed, downloads, rebuilds, and restarts, all from the browser, no
  SSH needed, with a plain confirmation first since it restarts the hub
  for everyone currently using it. User data lives entirely outside the
  code directory this touches, so it's untouched by design, not by care
  (`app/updater.py`)
- **Publish a flow as an API** — the "Publish" button in the flow editor
  generates an API key; anything outside the hub (a website, a script,
  another app) can then call that one flow with `X-API-Key`, no login, no
  session (`app/public_routes.py`). Runs as the flow's owner, since there's
  no logged-in person to act as for an external caller
- **Calculator** — evaluates a math expression safely (no `eval()`)
- Knowledge bases and flows are **per-person**, with shared-vs-private
  visibility and admin oversight, for a small team sharing one hub. Google
  access is hub-wide (one service account), not per-person - see the
  Google setup section below for why

## Quickstart

**Deploying to an actual Raspberry Pi 5?** See `deploy/README.md` for the
full walkthrough (flashing the OS, the install script, systemd). What
follows below is the quick local/dev version.

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
python3 tests/test_personal_search_keys.py   # A member with no admin rights uses Web search/YouTube via their own key
python3 tests/test_user_deletion.py   # Admin removes a team member - their flows/KBs transfer, not vanish
python3 tests/test_conversations.py   # Proves conversation memory by inspecting the actual LLM payload
python3 tests/test_web_search_and_documents.py   # Web search node + one-off document text extraction
python3 tests/test_llm_provider_errors.py   # LLM provider errors are clean messages, not raw httpx text
python3 tests/test_telegram_migration.py   # A pre-upgrade single-bot connection carries forward correctly
python3 tests/test_telegram_triggers.py   # Message a bot, get an auto-reply with real memory - zero /run calls
python3 tests/test_flow_publishing.py   # A published flow is callable with zero session - just an API key
python3 tests/test_call_flow.py   # One flow calling another - cycle detection, depth limit, access control
python3 tests/test_mcp_client.py   # The MCP client against both response transports servers actually use
python3 tests/test_mcp_node.py   # An MCP node working end to end inside a real flow
python3 tests/test_mcp_server.py   # A published flow's MCP endpoint - full JSON-RPC handshake, auth, errors
python3 tests/test_sirim_template.py   # The SIRIM template's 9-column schema, end to end through the real graph
python3 tests/test_dynamic_dns.py   # DuckDNS - saving credentials, and the background job surviving a simulated IP change
python3 tests/test_calendar.py   # Calendar via the service account, listing/creating events, and using both from a flow
python3 tests/test_sheets.py   # The upsert behavior a real progress tracker needs, via the service account
python3 tests/test_service_account_impersonation.py   # The full SIRIM scenario - real JWT, signature independently verified
python3 tests/test_robots_hardening.py   # robots.txt and noindex headers
python3 tests/test_youtube.py   # Search a topic, view counts included, then an LLM turns it into video ideas
python3 tests/test_llm_node_context.py   # An LLM after a tool node sees both the tool output AND the original message
python3 tests/test_reset_password_script.py   # The emergency CLI recovery tool, run as a real subprocess
python3 tests/test_forgot_password.py   # Email-based reset: no enumeration, single-use tokens, rate limiting
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
and the **Google service account key** aren't environment variables -
both are set at runtime by a hub admin on the Settings page, stored in
SQLite, with secrets encrypted using the same vault as everything else. This
is deliberate: these are the settings a non-technical admin should be able
to change without SSHing into the Pi or opening a config file, and the
Google key in particular takes effect immediately - no restart, since
`hub_settings.py` reads it fresh on every request rather than caching it
at startup.

On first real request with `EMBEDDING_PROVIDER=local`, `fastembed` downloads
the small model (~130MB for `bge-small`) and caches it — needs internet once,
then works fully offline.

### Setting up Google (Gmail + Drive + Calendar + Sheets)

One hub-wide service account, not a per-person OAuth flow - no browser
consent screen, no redirect URI to get right, and so none of the
`.local`/raw-IP restrictions a browser-based OAuth flow would run into,
since there's no browser redirect involved at any point.

**Setup, in order** (two different Google consoles - mixing up which one
you're in is the most common way this goes wrong):

1. **In Google Cloud Console** (console.cloud.google.com):
   - Create a project (or use an existing one).
   - Enable whichever of Gmail API / Drive API / Calendar API / Sheets
     API you actually need (Library → search → Enable each).
   - **IAM & Admin → Service Accounts → Create Service Account.** Name
     it whatever's clear (e.g. "agent-hub"). No IAM roles need to be
     granted here.
   - Open the new service account → **Keys → Add Key → Create new key →
     JSON**. This downloads the only copy of the private key - keep it
     safe until step 2.
2. **In Agent Hub**: Settings → **Google (Gmail / Drive / Calendar /
   Sheets)** → paste the entire contents of the JSON key file → Save.
   The card shows "Configured" with the service account's own email
   once it's accepted.
3. **On any Email/Drive/Calendar/Sheets node**, the **Impersonate**
   field decides what it acts as:
   - **Left blank**: the service account's own identity. Drive/Sheets/
     Calendar work immediately this way - files land in its own space,
     or in anything explicitly shared with its email address (exactly
     like sharing with a colleague). Gmail specifically has no real
     inbox for a plain service account, so an Email node with no
     Impersonate set will fail with a clear error pointing at step 4
     below - unless a Workspace admin has specifically provisioned a
     mailbox for the service account itself, which is unusual.
   - **Set to a real address**: acts as that specific person instead -
     needs step 4.
4. **For impersonating a real person** (only needed if a node should
   act as someone specific - e.g. reading an existing person's Gmail): a
   Google Workspace super admin authorizes this exact service account,
   once, in the **Workspace Admin Console** (admin.google.com - a
   different product from Cloud Console, needing different, higher
   access):
   - **Security → Access and data control → API controls →
     Domain-wide delegation → Add new**.
   - **Client ID**: the service account's **Unique ID** (a long number,
     sometimes labeled "OAuth2 Client ID" - found on its detail page in
     Cloud Console, not the same as the `client_email` in the JSON
     file).
   - **OAuth scopes**, comma-separated - only what's actually needed:

     | Node | Scope |
     |---|---|
     | Email | `https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.modify` |
     | Drive | `https://www.googleapis.com/auth/drive` |
     | Calendar | `https://www.googleapis.com/auth/calendar` |
     | Sheets | `https://www.googleapis.com/auth/spreadsheets` |

   - **Authorize.** Skipping this (or getting the Client ID/scopes
     slightly wrong) is the single most common way impersonation fails -
     `app/service_account_auth.py` gives a specific "domain-wide
     delegation not authorized" error for exactly this case, not a
     generic 403.
5. Back on the Settings card, use **Test** (Gmail or Sheets, with or
   without an email address) to confirm this actually works before
   wiring it into a real flow - leaving the address blank tests the
   service account's own identity, filling one in tests impersonation.

This is a bigger trust decision than a per-person login would be:
whoever controls this one key can make it act as anyone a Workspace
admin has authorized it for, not just themselves - treat the key file
the same way you'd treat any other admin-level credential. Setting it up
is admin-only for exactly this reason.

### Setting up Telegram (no cloud console needed)

Bots are a named resource, not a personal connection - shared with the
whole team by default, or private to whoever created it, the exact same
model as a knowledge base. This is what makes "different agents, different
bots" possible: a Telegram node in any flow picks a specific bot from a
dropdown, so a Customer Support Assistant and a completely separate Sales
Outreach agent can message through two different bots even though the same
person might build or run both flows.

1. In Telegram, message **@BotFather**, send `/newbot`, and follow the
   prompts. It replies with a token that looks like `123456789:AA...`.
2. On the Connections page, click "Add a bot" - give it a name (this is
   what shows up in a Telegram node's picker, e.g. "Support Bot"), paste the
   token, and choose whether it's shared with the team or private to you.
   The hub verifies the token immediately against Telegram's API.
3. Open a chat with the new bot (search for the username BotFather gave you)
   and send it any message.
4. Back on Connections, click "Finish linking" on that bot - the hub looks
   at its most recent message to find which chat to talk back to.

Repeat for as many bots as you want. Each one is independent - linking or
removing one doesn't touch any other, and a flow's Telegram node keeps
using whichever bot it's set to regardless of who clicks Run, the same way
a Knowledge base node keeps searching the same knowledge base regardless of
who's asking.

**Upgrading from before this existed**: if you already had a single bot
connected the old way, it's carried forward automatically the first time
the hub starts on this version - named "My bot," private to whoever
connected it, still linked. Nothing to redo.

### Making a bot answer automatically (Telegram triggers)

Connecting a bot (above) lets a *flow* message it - useful for
notifications, but it still needs something to trigger the flow (a click
on Run, a Schedule). A **trigger** flips this around: the *bot* triggers
the flow. Message the bot from your phone, anywhere, and the flow runs and
replies on its own - checked every few seconds by a background job, not
something that needs the hub's web UI open or anyone at the Pi.

1. Connect and link a bot first (above) - a trigger needs a bot that's
   already fully linked.
2. Open the flow in the editor and click **Telegram** in the toolbar (next
   to Publish). Pick the bot, click "Start listening."
3. Message that bot on Telegram. Within a few seconds it replies - the
   flow ran automatically, no Run button involved.

**Build the flow as a plain conversation, not with explicit Telegram
nodes.** A trigger already handles receiving the message and sending the
reply, the same way Chat already handles both ends for the web UI - a flow
meant to power a trigger should just be **Input → LLM → Output** (optionally
with a Knowledge base or Web search node first), exactly like a template
built for Chat. Adding your own "Telegram send" node to a triggered flow
sends the reply *twice* - once from your node, once from the trigger
delivering the flow's final output. If a flow already has explicit
Telegram read/send nodes because it was built before triggers existed
(or copied from one that proactively messages a *different* bot/channel),
simplify it down to Input → LLM → Output before wiring a trigger to it.

**Memory carries over exactly like Chat** - a trigger keeps one ongoing
conversation per bot, visible from the trigger's modal ("View this
conversation in Chat") or the Chat page directly, so a back-and-forth
("what was my goal again?") works the same over Telegram as it does typing
in the browser.

A bot can only power one trigger at a time - wiring a second flow to a bot
that's already listening is rejected with a clear message, since an
incoming message would otherwise be ambiguous about which flow should
answer it. Pausing or removing a trigger (from the same modal) stops the
polling for that bot immediately; the conversation history stays put
either way, so resuming later picks the same relationship back up.

### Setting up web search

Settings → Web search: paste in a Tavily API key. Free tier, no credit card,
at [tavily.com](https://tavily.com) - a few thousand searches a month, which
is generous for personal or small-team use. Hub-wide only, not a per-person
setting like the LLM key - search results aren't billed per-account the same
way LLM tokens are, so there's less reason for everyone to bring their own.

### Setting up YouTube search

Settings → YouTube search: paste in a YouTube API key - a plain API key,
not an OAuth connection, since searching YouTube's public catalog isn't
"acting as" anyone the way Gmail/Drive/Calendar are.

1. In [Google Cloud Console](https://console.cloud.google.com), the same
   project used for Gmail/Drive/Calendar works fine (or a fresh one, if
   this is the only Google integration you want).
2. APIs & Services → Library → enable **YouTube Data API v3**.
3. APIs & Services → Credentials → Create Credentials → **API key** (not
   OAuth client ID). Optionally restrict it to just the YouTube Data API
   for a bit of defense in depth.
4. Paste it into Settings → YouTube search and hit Save.

Free tier is 10,000 quota units/day; a search costs 100 units, so roughly
100 searches a day before you'd hit a limit - generous for personal or
small-team use.

### Conversations (memory)

Every flow can be used two ways: **Run**, in the flow editor, is always a
fresh one-shot - good for testing a flow while building it. **Chat**
(the button next to Schedule) opens a real conversational interface:
start a new conversation, and every message you send after the first
carries the whole conversation with it - the flow's LLM node(s) see
everything said so far, not just the latest message. This is what makes a
template like Customer Support Assistant or Personal Productivity Coach
actually usable instead of just able to answer one isolated question at a
time.

Conversations are personal - like chat history, not a shared team log, even
for a flow the whole team can see and run. Each person's conversations with
a given flow are their own list in the Chat sidebar.

The attach button (📎) in Chat pulls text out of an uploaded PDF/DOCX/CSV/
TXT/MD file and drops it into the message box - useful for something like
Meeting Summarizer where you want to hand over a whole transcript without
first building a permanent searchable knowledge base for a document you'll
only ever use once.

## Self-updates

Settings → Software updates: defaults to `blipblop67/agent-box-cytron`
(main branch) with nothing to configure - every hub ships ready to check
for updates against the reference repo. An admin can point it at a
different repo/branch instead (the "change" link next to the repo name),
typically their own fork. "Check for updates" compares the latest commit
on that branch against what's installed; "Update now" downloads it,
reinstalls Python dependencies, rebuilds the frontend, swaps the new code
in, and restarts - a few minutes, entirely from the browser.

**The repo has to be public.** The check is an anonymous GitHub API
request - no token, nothing to configure - which means it can only see
public repositories. A private repo returns the exact same 404 a
nonexistent one would, so `check_for_update()` gives a specific error
pointing at this ("...the repository is private...") rather than a bare
"not found," and `/api/updates/status` surfaces that error on the page
instead of failing to load at all (it checks on every page load now that
there's always a default repo to check).

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
- **Three ways to recover a forgotten password**, in the order most people
  will actually reach for them:
  1. **Self-service, "Forgot password?" on the login screen** - only works
     if the person set a recovery email (Account page) *and* an admin
     configured outgoing SMTP (Settings → Outgoing email). Sends a
     single-use link that expires in an hour
     (`POST /api/auth/forgot-password`, `POST /api/auth/reset-password`).
     Deliberately returns the exact same response whether the name exists,
     has no email, or hit the rate limit (3 requests / 15 min per name) -
     nothing about this endpoint can be used to discover who's registered.
     A stale link is invalidated the moment the password changes any other
     way (self-service change, admin reset, the CLI tool below), so an old
     email lying around in an inbox can't undo a more recent change.
  2. **An admin resets it** (Team page / `PATCH /api/users/{id}/password`)
     - works regardless of whether that person set a recovery email or SMTP
     is configured at all.
  3. **Locked out entirely** (forgot the only admin's password, no
     recovery email set, no SMTP configured)? From a terminal on the same
     machine the hub runs on:
     ```bash
     cd agent-hub/backend
     python3 reset_password.py
     ```
     Lists every account, asks which one, asks for a new password twice,
     sets it exactly the way a normal reset would (same hashing, same
     session invalidation) - nothing hacky, no editing the database by
     hand. This is a local-shell tool on purpose, not a web endpoint:
     anyone with shell access to the machine already has full access to
     the SQLite file itself, so there's no security gained by making this
     harder to reach - only friction for the actual admin locked out of
     their own hub. `tests/test_reset_password_script.py` runs this exact
     script as a real subprocess and confirms the old password stops
     working and the new one logs in correctly.
  All three end the same way: every existing session for that account is
  invalidated, forcing a fresh login with the new password.

### Setting up outgoing email (for self-service password reset)

Settings → Outgoing email: host, port, username, password, from address,
and whether to use STARTTLS. Any real SMTP server works - a dedicated
transactional-email provider if you have one, or just a personal Gmail
account with an [app password](https://support.google.com/accounts/answer/185833)
(not your regular Gmail password - Google blocks plain-password SMTP
login): host `smtp.gmail.com`, port `587`, STARTTLS on.

Hub-wide only, admin-configured, the same reasoning as the web search and
YouTube keys - this isn't a personal credential like a Google OAuth app,
it's shared infrastructure for one system function (reset emails), so
there's no reason for it to be per-person.

Once it's saved, use "Send a test email" right there on the Settings card
to confirm it actually works - genuinely worth doing before relying on it,
since the whole point is having a working recovery path *before* you need
one, not discovering an SMTP typo during an actual lockout.

Each person then sets their own recovery email on the Account page - it's
optional, personal, and nobody else (including admins) can see it. Without
it, "Forgot password?" for that account always falls through to its
generic "if that account has a recovery email set up..." response, same as
if SMTP weren't configured at all.

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

- **DuckDNS came back as a standalone network-reachability feature, not
  the OAuth workaround it originally was.** It existed once already, in
  this codebase's history, specifically to satisfy Google's OAuth
  redirect-URI rules - removed entirely when Google auth moved to a
  service account, which has no redirect URI at all and so no longer
  cares what hostname or IP the hub is reachable at. It's back now for a
  genuinely different, unrelated reason: some networks (guest Wi-Fi,
  certain routers, some enterprise setups) block mDNS/`.local`
  resolution outright, and a real DNS name resolves everywhere normal
  DNS works. Deliberately opt-in and customer-configurable (a Settings
  card, not baked into the golden image or required at manufacturing
  time) - each customer who actually hits an mDNS problem sets up their
  own free account and turns it on themselves; everyone else never sees
  it. `dynamic_dns.py`'s core logic (the DuckDNS API call, LAN IP
  detection, the background refresh job surviving a DHCP renewal) is
  unchanged from the original implementation - that part was already
  correct, the only thing that changed is what it's *for*.
- **Verified past the point of trusting the mocked tests**: after
  building the Settings card, ran the actual save-and-update flow
  through a real browser against a real (deliberately fake) DuckDNS
  token, letting the request genuinely reach `duckdns.org` and come back
  rejected - confirming the whole chain end to end, not just that each
  piece looks right in isolation.

- **A Google AI Studio sample app of the same SIRIM tracker concept was a
  genuinely useful reference for *what to track*, not *how to
  authenticate*.** It used Firebase Auth's popup-based per-user Google
  sign-in - functionally a variant of the exact per-user OAuth model this
  codebase moved away from, needing the same real-domain/redirect
  requirements a `.local` appliance address can't satisfy. What was worth
  keeping was its data model: a much richer set of tracked fields
  (certification scheme, officer contact, target deadline,
  priority-tagged pending actions, certificate number) than the original
  3-column example. Brought into the existing pipe-delimited convention
  as a 9-column schema (`templates.py`'s SIRIM template) - no new parsing
  logic needed, since `_execute_sheets_node` already split on `|` and
  handled however many fields were there; verified against the *actual,
  unmodified* template graph end to end in `test_sirim_template.py`
  rather than just trusting the prompt reads correctly.
- **A spreadsheet's header row gets styled automatically on creation** -
  frozen, bold white text on Agent Hub's own copper-dim brand color -
  rather than left as plain unstyled text the way every Sheets-created
  tracker previously looked. Deliberately fails silently
  (`sheets_client._format_header_row`) if the styling call itself errors
  - it's cosmetic, and a flow's actual Create action succeeding matters
  far more than the header looking nice, so a styling hiccup should never
  be why someone's tracker failed to get created.

- **The MCP client handles both response shapes real servers use, and
  re-initializes on every call rather than caching a session.** MCP's
  "Streamable HTTP" transport lets a server reply to the same kind of
  request with either a plain JSON body or a Server-Sent-Events stream -
  `mcp_client.py` handles both, verified against a mock of each in
  `test_mcp_client.py` rather than assumed from reading the spec. Re-running
  the `initialize` handshake on every `list_tools`/`call_tool` (instead of
  keeping a session alive across calls) costs an extra round trip per
  call, in exchange for not having to track session expiry or handle a
  stale session failing mid-flow - the same "simple over clever, revisit
  if profiling says otherwise" trade this codebase already makes for
  Google OAuth tokens and LLM provider credentials.
- **An MCP node's input can be plain text, not just JSON.** Real tools
  vary a lot in how many arguments they take - a tool with a single
  string parameter is common enough that requiring an upstream LLM node
  to always produce a JSON object would be needless ceremony for the
  simple case. If the node's input parses as a JSON object, that becomes
  the tool's arguments directly; otherwise the raw text is wrapped as
  `{"input": <text>}`, which happens to match a very common single-argument
  tool shape. Getting a tool with a genuinely different single-argument
  name would still need an upstream LLM node producing real JSON - the
  fallback is a convenience for the common case, not a way to avoid
  reading a tool's actual schema.

- **Call Flow (one flow invoking another) needed two independent safety
  nets, not one.** Cycle detection (`call_stack`, a frozenset of every
  flow_id already running higher up the same call chain) catches A
  calling B calling A - direct or indirect - but a long, genuinely
  acyclic chain (A→B→C→D→...) would sail straight through cycle
  detection while still being something nobody actually wants to happen
  by accident. `MAX_CALL_DEPTH` (5) catches that second case
  independently. Both are proven with dedicated tests in
  `test_call_flow.py` - a direct self-call, an indirect A→B→A cycle, and
  a deliberately-constructed 8-flow chain that's acyclic but too deep.
- **The called flow always starts fresh - no history carried over, even
  inside a Chat conversation.** A Call Flow node is a tool call, not a
  merge of two conversations - the calling flow keeps its own
  conversation memory; the called flow gets exactly what the node's
  input was, the same as if someone had typed it into that flow's own
  Input node, and nothing else.

- **Google access became one hub-wide service account, replacing
  per-person OAuth entirely** - a real architectural pivot, not an
  incremental addition. The earlier per-person OAuth model hit a genuine
  wall: Google's OAuth client will only ever accept a redirect URI whose
  host is `localhost`/`127.0.0.1` or a domain with a real public suffix,
  which a self-hosted hub reached by `.local` name or a raw LAN IP could
  never satisfy without extra infrastructure (a dynamic-DNS domain, an
  SSH tunnel) just to make a browser-based consent flow possible. A
  service account has no browser redirect at all, so that whole class of
  problem doesn't apply - not worked around, just absent. The tradeoff
  is a bigger trust surface (one credential that can act as anyone a
  Workspace admin has authorized it for, versus a personal login that
  only ever grants access to the one account that clicked Allow), which
  is why setting the key is admin-only.
- **Every Email/Drive/Calendar/Sheets node shares one `impersonate`
  parameter with two meanings, not two separate features.** Left blank,
  a node acts as the service account's own identity - genuinely useful
  for Drive/Sheets/Calendar (its own space, or anything shared with its
  email address), and a clean, specific failure for Gmail (no real inbox
  by default). Set to a real address, it acts as that Workspace person
  instead, which needs a super admin to have authorized domain-wide
  delegation for this exact service account and scope. Both paths run
  through the same `service_account_auth.get_access_token()` - the only
  difference is whether a `sub` claim is present in the signed JWT (see
  its docstring) - so every `*_client.py` module has one auth code path,
  not a branch between two systems.
- **Hand-rolled RS256 JWT signing, not `google-auth`.** Consistent with
  every other Google integration in this codebase (plain httpx REST calls
  instead of the official SDKs) - a service account token exchange is
  header + claims + one RSA signature + one POST, and `cryptography`
  (already a dependency, used for the encryption vault) has everything
  needed. Verified this produces genuinely valid tokens, not just
  plausible-looking ones, by decoding a real signed JWT in testing and
  checking the signature against the public key directly - independent
  proof it's spec-correct, not just "the mocked HTTP call accepted it."
- **`X-Robots-Tag: noindex` on every response, plus a disallow-all
  `robots.txt`** - cheap, standard hardening for any admin-style tool,
  kept even after the service-account switch removed the specific
  DNS-exposure scenario it was originally added for. Costs nothing for
  the overwhelming majority of installs where it was never a real risk.

- **Sheets is a real API integration, not a bigger Drive node.** Drive
  treats a file as an opaque blob - creating one works fine, but "editing"
  it means regenerating the entire content and overwriting the whole
  file, which doesn't scale for a spreadsheet that's meant to be updated
  incrementally over time. `sheets_client.py` uses the actual Sheets API
  (`spreadsheets.values.update`/`.append`) so `upsert_row` can touch just
  one row - find it by matching the first column against a key, update it
  in place, or append a new one if the key hasn't been seen before. A flow
  passes one text string between nodes, so the handoff into a Sheets node
  is a small, deliberate convention: one row per line, values separated by
  `|`, first value is the key - simple enough for a system prompt to
  produce reliably, and readable if you're staring at the trace trying to
  see what happened. A single run updates as many rows as the previous
  node's output has lines, since a realistic use case (checking email for
  updates across several things being tracked) will often touch more than
  one row per check - this wasn't the original design, it came from
  actually building the SIRIM CoC Progress Tracker template and realizing
  a single-row-per-run node would silently drop every application after
  the first one mentioned in a given batch of emails.
- **A Sheets node references a fixed spreadsheet ID, the same pattern a
  Knowledge base node uses for `kb_id` or a Telegram node uses for
  `bot_id`.** There's no "create if missing" magic - you create the
  tracker once (temporarily switch the node to the "Create" action, run
  it, copy the ID it returns), then point every subsequent node at that
  same ID. Explicit over clever: the alternative (a flow that silently
  creates a new spreadsheet on first run and somehow remembers it for
  next time) would need to persist state outside the flow graph itself,
  which nothing else in this system does.
- **Web search and YouTube keys got the same personal-override treatment
  the LLM key and Google app already had**, rather than staying hub-wide
  only. The distinction that matters for "should this be per-person or
  admin-only": a hub-wide *default* that anyone can supplement with their
  own is fine to open up (worst case, someone spends their own Tavily/
  YouTube quota); a *shared, team-affecting* setting like the SMTP
  credentials or which GitHub repo the hub trusts is a different kind of
  decision and stays admin-only. `user_settings.py`'s
  `resolve_web_search_api_key`/`resolve_youtube_api_key` mirror
  `resolve_openrouter_credentials` exactly - personal wins if set,
  otherwise hub-wide, otherwise a clear error naming both places to fix it
  (`flow_engine.py`'s node executors now take `user_id` for this, the same
  way the LLM node already did).
- **Checking/applying an update is open to the whole team; choosing which
  repo to trust isn't.** `update_routes.py` splits these on purpose: the
  repo/branch a hub pulls code from (`PUT /config`) stays admin-only,
  since that's a supply-chain decision - who gets to point the hub at
  arbitrary code - while running an update from whatever source is
  *already* configured (`POST /check`, `POST /apply`) doesn't carry that
  same risk, so there's no reason to gate it to admins specifically. The
  frontend still confirms before applying (it restarts the hub for
  everyone currently using it), just no longer checks role first.
- **A GitHub 403 gets the same clean-error treatment a 404 already got.**
  Found by hitting it directly, not hypothetically: `check_for_update()`
  only converted a 404 (private/missing repo) into a readable message -
  anything else, including GitHub's anonymous rate limit (60 requests/
  hour, returned as a 403), fell through to a raw `raise_for_status()`
  and crashed the endpoint with an unhandled 500. Worth fixing regardless,
  but especially now: opening "check for updates" to everyone makes that
  shared 60/hour limit easier to hit, not harder.
- **The forgot-password endpoint always returns the same response.**
  `POST /api/auth/forgot-password` looks identical to the caller whether
  the name doesn't exist, exists but has no recovery email, exists and has
  one but SMTP isn't configured, or hit its rate limit - every branch in
  `auth_routes.py` returns the exact same generic message. This is a
  standard property for any account-recovery endpoint (not unique to this
  project) because the alternative - a different response for "no such
  account" vs "email sent" - turns the endpoint into a way to enumerate
  which names are registered on the hub, one guess at a time.
  `tests/test_forgot_password.py` asserts the response bodies are
  byte-for-byte identical across all of those cases, not just that they
  all happen to return 200.
- **Password-reset-email rate limiting is a separate throttle from login
  throttling** (`security.py`'s `can_request_password_reset`, distinct
  from the existing `is_locked_out`), because they're protecting against
  different things: login throttling limits guessed passwords, this limits
  how many emails a name can trigger - protecting the SMTP account/quota
  and whoever owns that inbox from being spammed, which a failed-login
  counter has nothing to do with.
- **Polling, not webhooks, for Telegram triggers.** A real Telegram
  webhook needs a stable public HTTPS URL, which a Pi on a home/office LAN
  usually doesn't have (dynamic IP, no port forwarding guaranteed). A fixed
  3-second poll (`scheduler.py`'s `telegram-trigger-poll` job, reusing the
  APScheduler instance schedules already run on) is what actually works
  out of the box on the hardware this targets, and 3 seconds is
  indistinguishable from instant for a chat use case. `getUpdates`'
  `offset` parameter does the heavy lifting - passing the last-seen
  update id both fetches only what's new *and* tells Telegram's servers to
  stop redelivering everything before it, so there's no separate
  dedup bookkeeping needed beyond storing that one integer per trigger.
- **The poller is one plain synchronous function, not baked into
  APScheduler's callback.** `telegram_poller.check_all_triggers()` takes no
  arguments and returns nothing - the scheduler just calls it on an
  interval. Every test in `test_telegram_triggers.py` calls this exact same
  function directly, so the tests exercise the real trigger-checking logic
  instead of a simplified stand-in, without needing to wait on a live
  background scheduler tick (which would make the tests slow and, worse,
  flaky under load).
- **A trigger reuses the Chat conversation machinery wholesale**, not a
  parallel memory system - creating a trigger calls the exact same
  `db.create_conversation` Chat uses, and `_handle_message` loads/appends
  history through the exact same functions `conversation_routes.py` does.
  One person's back-and-forth over Telegram and the same conversation
  viewed in the web Chat UI are *the same conversation*, not two things
  kept in sync.
- **YouTube search is modeled on Web search, not on Gmail/Drive/Calendar** -
  a hub-wide API key (`app/youtube_client.py`, `hub_settings.py`), not a
  per-person OAuth connection. The distinguishing question for any new
  integration is "does this act as a specific person, or read something
  public?" Gmail sending an email has to be *someone's* email; searching
  YouTube's public catalog isn't attributable to anyone, so there's no
  account to connect and no reason to make every team member set it up
  individually - one key, admin-configured, same as Tavily.
- **Calendar is a third sibling of Gmail/Drive/Sheets, not a variant.**
  Adding a new Google product is almost entirely mechanical because the
  service-account auth is already generic - `calendar_client.py` mirrors
  the shape of `gmail_client.py`/`drive_client.py`/`sheets_client.py`
  field-for-field (a `SCOPES` list, an `_headers(impersonate)` helper
  that calls `service_account_auth.get_access_token`, then plain REST
  calls), differing mainly in scopes and the API calls themselves.
- **A tool node's output augments the original message for the next LLM
  node - it doesn't replace it.** Found while building the Calendar
  template: chaining Knowledge base/Web search/Calendar into an LLM node
  used to pass only the tool's output as the "user message," silently
  dropping whatever was actually asked - a Calendar listing has no idea
  what the person said, so the model would respond to five event titles
  instead of the person's actual message. `_execute_node`'s "llm" branch
  now builds `"Context:\n{tool_output}\n\nMessage: {original_message}"`
  when both differ, and falls back to the old simple behavior for a plain
  Input → LLM chain where there's nothing to combine
  (`tests/test_llm_node_context.py`).
- **API keys are hashed with SHA-256, not bcrypt.** Passwords need a slow,
  salted hash because people choose low-entropy secrets an attacker can
  guess offline; a generated `ahub_...` key is 256 bits of randomness with
  nothing to guess, and a published flow needs a fast, indexable lookup on
  every public call, which is exactly what bcrypt is designed to prevent.
  Same reasoning session tokens already used (`app/security.py`), now
  reused for the same category of secret.
- **A published flow runs as its owner**, not "whoever's logged in" -
  there isn't anyone logged in for an external caller. This is the same
  rule scheduled runs already followed (`app/scheduler.py`), just extended
  to a second no-session context rather than invented fresh for this.
- **Telegram bots are a resource, not a connection.** Gmail/Drive are
  personal - a tool node acts as whoever runs the flow, since a Gmail node
  sending "from you" only makes sense if it's *your* Gmail. A bot doesn't
  work that way: its identity (the username people message) is fixed
  regardless of who built or runs the flow, so it's modeled like a
  knowledge base instead - a named, ownable, shared-or-private resource
  (`telegram_bots` table) that a Telegram node picks by id
  (`data.bot_id`), the same way a Knowledge base node picks a `kb_id`.
  This is what actually makes "different agents, different bots" work:
  the bot is a property of the flow's wiring, not of whoever's logged in.
- **LLM output is rendered as markdown everywhere it's shown** - Chat
  messages and the Run panel's output share one component
  (`components/common/Markdown.jsx`, react-markdown + remark-gfm +
  remark-math + rehype-katex) rather than each screen inventing its own
  text-formatting rules. Math renders as actual typeset formulas via
  KaTeX, not literal `$...$` characters - worth knowing if you ever swap
  the LLM provider or model: whatever markdown/LaTeX conventions it uses
  should render correctly without any hub-side changes, since parsing
  happens generically, not by pattern-matching your prompts.
- **Conversation memory is a parameter, not a fork.** `flow_engine.run_flow`
  takes an optional `history` list; a plain Run never passes one (unchanged,
  one-shot behavior), while `conversation_routes.py`'s send-message endpoint
  loads prior turns and passes them through. Every LLM node in the flow gets
  the same history prepended - there's no separate "conversational flow"
  concept or duplicated execution path, just one flow engine that behaves
  differently based on whether it was handed something to remember.
- **Deleting a user reassigns their data instead of cascading the delete.**
  `db.reassign_user_data` hands off owned flows, knowledge bases, uploaded
  documents, and schedules to whichever admin performed the deletion, before
  the account itself is removed - a private flow doesn't just vanish, and a
  shared one doesn't orphan a foreign key. Personal connections (Gmail,
  Drive, Telegram) are the one exception: those are deleted outright, since
  handing someone else's OAuth token to the admin would be nonsensical, not
  a courtesy.
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
  (`user_settings.resolve_openrouter_credentials`,
  `resolve_web_search_api_key`, `resolve_youtube_api_key`) that every
  caller goes through, so there's exactly one place that decides
  "personal, or fall back to hub-wide." Google has no equivalent - one
  hub-wide service account, not a per-person setting - which is itself
  a deliberate simplification: a shared credential that can act as
  anyone a Workspace admin authorizes doesn't have a sensible "personal
  override" version the way an LLM API key does. The Account page
  fetches both `/api/settings` (hub-wide, readable by anyone) and
  `/api/account/settings` (personal) and computes the same "which one's
  actually active" logic client-side for the settings that do have a
  personal option, so the UI states what's in effect right now rather
  than just listing two separate config forms and leaving the
  relationship to be inferred.
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
- **Drive uses the full `drive` scope, not the narrower `drive.file`.**
  With a shared service account rather than a personal login, `drive.file`
  would only let it see files it created itself - too limiting for the
  common case of pointing it at an existing folder or spreadsheet someone
  else set up and explicitly shared with its email address. Worth knowing
  if this ever needs tightening for a specific deployment - change the
  scope in `drive_client.py`.
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

- No email verification step when someone sets a recovery email on the
  Account page - it's trusted at face value. A typo'd or someone-else's
  address means a reset link would go nowhere useful (harmless) or
  somewhere it shouldn't (worth knowing, low severity since a reset link
  alone doesn't reveal the account's current password, just lets someone
  set a new one - which they'd then need the login screen to actually use)
- No confirmation email after a successful reset - the request email
  itself says "someone (hopefully you) asked to reset..." as a notice, but
  there's no separate "your password was just changed" email sent
  afterward, so someone who requested a reset then got interrupted
  wouldn't get a second signal that it actually completed
- Two-factor auth / passkeys - password-only for now
- Delete-file-from-disk cleanup when a document row is deleted (currently
  leaves the raw upload on disk even after the DB row and vectors are gone)
- IMAP/SMTP fallback for non-Gmail email providers
- Rate limiting on `/documents` uploads
- A `PATCH` endpoint to rename a knowledge base or change its visibility
- Event-based triggers for Gmail/Drive (e.g. "run when a new email
  arrives") - Telegram has this now (see "Telegram triggers" above,
  polling-based); Gmail/Drive don't yet, and would need either polling or
  a push mechanism (a Gmail/Drive push notification needs a public URL the
  same way a Telegram webhook would, so this would likely follow the same
  polling approach rather than waiting on that)
- A true "autonomous agent" node - LLM decides which tools to call, vs. the
  deterministic wiring flows use today
- A GitHub token option for the updater (private repos, and GitHub's 60/hour
  unauthenticated rate limit)
- Conversation history has no summarization/compaction - it's capped at the
  last `MAX_HISTORY_MESSAGES` (40) turns, so a very long-running conversation
  eventually starts dropping its earliest messages rather than summarizing them
- No editing a document already extracted into a chat message - if the
  extracted text needs a correction, remove it from the message box and
  re-attach
- No spreadsheet picker for the Sheets node - you paste in an ID by hand
  (from the sheet's URL, or the output of a one-time "Create" run), the
  same way a Telegram node's bot or a Knowledge base node's `kb_id` work,
  rather than browsing a list. A Drive-style picker would be nicer but
  needs its own "list spreadsheets I can see" endpoint this doesn't have yet
- The Sheets node only writes plain values - no cell formatting,
  conditional formatting (e.g. color-coding a Status column by value), or
  formulas. Whatever the LLM's line becomes is exactly what lands in the
  row, verbatim
- Sheets row-matching is always column A - no configurable "match on this
  other column instead" for a spreadsheet where the natural key isn't the
  first one
- An update history/changelog view beyond the single `app.bak` rollback slot
- No rate limiting on the public flow API (`/api/public/flows/{id}/run`) -
  a published flow can be called as fast as the caller wants; fine for the
  "call this from my own script/website" use case it's built for, worth
  revisiting before pointing anything untrusted at a published URL
- No usage/call count shown for a published flow - it works, but there's no
  "this key has been used N times, last seen at..." on the Publish modal yet
- MCP export - turning a flow into a tool an MCP client (Claude Desktop,
  Cursor) can call directly, the way the flow API above lets a website or
  script call it. Same shape of feature, different protocol; a natural
  next step once there's a concrete need for it
- Branching/conditional logic in a flow (an If/Else or Router node) -
  flows are still a strict DAG that runs every reachable node, no
  LLM-driven "decide which path to take" yet
- A Telegram trigger only replies to the one chat linked when the bot was
  connected - if the bot is added to a group, or DMed by someone other
  than whoever linked it, those messages are polled past but never
  answered, matching the single-chat design the whole Telegram integration
  already used. Multi-chat support (a bot that independently converses
  with anyone who messages it) would need per-chat conversation state
  instead of the one conversation a trigger keeps today
- No flood protection on a trigger - each incoming message runs a full
  flow (an LLM call, possibly a tool call) with no rate limit, so a chat
  that gets spammed runs the flow that many times
