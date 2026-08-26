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
- **Gmail** — each team member connects their own account, through either
  the hub's shared Google app (Settings) or their **own** Google app
  (Account page) if they'd rather not trust the admin's OAuth client; send,
  search, and reply from an Email node
- **Drive** — same per-person connection, same personal-app option; list,
  read (including native Docs/Sheets/Slides), and create files from a Drive node
- **Calendar** — same per-person connection again (Google Calendar
  specifically); list upcoming events or create new ones from a Calendar
  node. The Personal Productivity Coach template uses this to pull your
  next few events as context for every check-in
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
- **Domain-wide delegation** (Google Workspace only) — a second, optional
  way for an Email/Drive/Calendar/Sheets node to act as a specific
  person, without that person ever clicking Connect. A Workspace super
  admin authorizes one service account, once, to impersonate anyone in
  the organization for chosen scopes; from then on, any node's
  **Impersonate** field can target that address directly. Genuinely
  different from personal OAuth, not a variant of it - no browser
  redirect at all, so it sidesteps Google's redirect-URI restrictions
  entirely (see the callout above) and works from a `.local`/LAN-IP-only
  hub without a workaround. A bigger trust decision than a personal
  connection (one credential, many mailboxes), so it's admin-only to set
  up (`app/service_account_auth.py`)
- **Telegram** — named bots (shared or private, same model as knowledge
  bases), not one connection per person: create as many as you want (just a
  token from @BotFather, no Google Cloud setup), and each Telegram node in a
  flow picks which one to use - a Customer Support flow and a Sales flow can
  message through two entirely different bots regardless of who runs them
- **Telegram triggers** — wire a flow to a bot (the "Telegram" button in
  the flow editor) and it answers messages automatically: a background job
  checks every few seconds, runs the flow with the same conversation memory
  Chat uses, and sends the reply back - no session, no clicking Run, not
  needing to be anywhere near the hub. This is what makes a Telegram bot
  usable as an actual assistant instead of only something a flow can
  proactively message (`app/telegram_poller.py`)
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
python3 tests/test_personal_search_keys.py   # A member with no admin rights uses Web search/YouTube via their own key
python3 tests/test_user_deletion.py   # Admin removes a team member - their flows/KBs transfer, not vanish
python3 tests/test_conversations.py   # Proves conversation memory by inspecting the actual LLM payload
python3 tests/test_web_search_and_documents.py   # Web search node + one-off document text extraction
python3 tests/test_llm_provider_errors.py   # LLM provider errors are clean messages, not raw httpx text
python3 tests/test_telegram_migration.py   # A pre-upgrade single-bot connection carries forward correctly
python3 tests/test_telegram_triggers.py   # Message a bot, get an auto-reply with real memory - zero /run calls
python3 tests/test_flow_publishing.py   # A published flow is callable with zero session - just an API key
python3 tests/test_calendar.py   # Calendar OAuth, listing/creating events, and using both from a flow
python3 tests/test_sheets.py   # Sheets OAuth, and the upsert behavior a real progress tracker needs
python3 tests/test_google_oauth_warning.py   # Warns before Google rejects a .local/raw-IP redirect URI
python3 tests/test_service_account_impersonation.py   # Domain-wide delegation - real JWT, signature independently verified
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

### Setting up Gmail + Drive + Calendar + Sheets (one-time, per deployment)

All of this happens from the **Settings** page in the app now - no config
file to open. Four steps, not two - the first and last are easy to miss and
are the most common reason connecting fails:

1. In [Google Cloud Console](https://console.cloud.google.com), create a
   project.
2. **Enable the APIs**: APIs & Services → Library → search for and enable
   **Gmail API**, **Google Drive API**, **Google Calendar API**, and
   **Google Sheets API** (all four, even if you only plan to use one right
   now - each is free to enable and costs nothing to leave on). Creating
   OAuth credentials without this step lets someone connect, but every
   actual send/list/read/update call then fails.
3. Configure the **OAuth consent screen**: User Type "External" (unless you
   have Google Workspace), fill in the required fields. While it's in
   **Testing** mode (the default, and fine for a small team), Google will
   silently refuse to let anyone sign in who isn't listed under **Test
   users** on that same page - add every team member's Google account there.
   This is far and away the most common cause of "I click Connect and it
   just fails."
4. Create **one** OAuth client ID (Credentials → Create Credentials → OAuth
   client ID → type "Web application") — Gmail, Drive, Calendar, and Sheets
   all share it. The Settings page shows the exact four redirect URIs to
   add here (they're derived from however you're currently reaching the
   hub, so they're always right - a "Copy" button sits next to each one).
   **If the Settings page shows a red warning above those URIs, read it
   before pasting anything into Google Cloud Console** - see the note right
   after this list; it'll save you a confusing round trip through Google's
   own error messages.
5. Paste the client ID and secret into the Settings page and hit Save -
   takes effect immediately, no restart. (An admin who'd rather set these
   via `.env`/environment variables instead still can - see the
   configuration table above - but the Settings page always wins if both
   are set.)
6. Each team member connects whichever of the four they want from the
   Connections page - Gmail, Drive, Calendar, and Sheets are independent
   connections, so someone can connect just Sheets without Gmail if
   that's all they need. The first time, Google shows an "unverified app"
   warning - that's expected for a personal project not submitted for
   Google's review; click **Advanced → Go to (app name)** to proceed.

If a connection attempt does fail, it now lands on a page explaining the
likely cause (`app/oauth_errors.py`) instead of a bare error - that's the
first place to look.

**A hard requirement of Google's, not anything to do with this hub**:
Google's OAuth client will only accept a redirect URI whose host is either
`localhost`/`127.0.0.1`, or a domain with a real, ownable public suffix.
This means **the two most common ways to reach this hub - a `.local` mDNS
name (the default `agenthub.local`) and a raw LAN IP address - are both
rejected**, with a genuinely confusing error
("must use a domain that is a valid top private domain") that has nothing
to do with anything you did wrong. The Settings and Account pages detect
this automatically and show a warning right above the redirect URIs box
if the hub is currently being reached in a way Google won't accept, so
you see this *before* pasting a doomed URI into Google Cloud Console, not
after. Two ways forward:
- **Get a free dynamic-DNS name** (e.g. [DuckDNS](https://www.duckdns.org))
  and point it at the hub's LAN IP - resolves fine for anyone on your
  network, and satisfies Google's "real domain" requirement since it's
  checking the string format, not that it's reachable from the public
  internet.
- **Do the one-time Connect step from a browser on the same machine the
  hub runs on**, using `http://localhost:8811` instead of the `.local`
  name or IP - Google's one real exception, no domain needed. (An SSH
  local port-forward - `ssh -L 8811:localhost:8811 you@pi` - lets you do
  this from your own laptop without physically sitting at the Pi.)

### Setting up domain-wide delegation (Google Workspace only, optional)

Everything above is per-person OAuth: each team member clicks Connect and
grants access to their own Google account. That has a hard limit -
Google's OAuth client will only ever redirect to `localhost`/`127.0.0.1`
or a real public domain, so it can't reach a hub that's only accessible
by `.local` name or a raw LAN IP (see the callout above), and it always
needs the actual account owner to personally click Allow.

**Domain-wide delegation is a different mechanism for Google Workspace
domains specifically**, that sidesteps both of those: a Workspace super
admin authorizes one service account, once, in the Admin Console (not
Cloud Console), to act as *any* user in the organization for specific
Google scopes. From then on, an Email/Drive/Calendar/Sheets node's
**Impersonate** field can target any address in your Workspace directly -
no browser redirect, no per-person consent, and nothing for Google's
redirect-URI rules to reject, since there's no redirect involved at all.

This is a genuinely bigger trust decision than a personal connection -
one credential that can act as anyone in the domain, for whatever's been
granted - so it's admin-only to configure, and worth treating the key
file the same way you'd treat any other admin-level secret.

**Setup, in order** (the two consoles below are different products -
mixing up which one you're in is the most common way this goes wrong):

1. **In Google Cloud Console** (the same `sirim-coc-agent`-style project
   used for OAuth, or a fresh one - doesn't matter which):
   - Enable whichever of Gmail API / Drive API / Calendar API / Sheets API
     you actually need (IAM & Admin doesn't require all four).
   - **IAM & Admin → Service Accounts → Create Service Account.** Name it
     whatever's clear (e.g. "agent-hub-delegation"). No roles need to be
     granted here - domain-wide delegation is authorized separately, in
     the Workspace Admin Console, not through IAM roles.
   - Open the new service account → **Keys → Add Key → Create new key →
     JSON**. This downloads a `.json` file - this is the *only* copy of
     the private key; Google doesn't keep a spare. Keep it somewhere
     safe until it's pasted into the hub.
   - Still on the service account's detail page, copy its **Unique ID** (a
     long number, sometimes labeled "OAuth2 Client ID" - not the same as
     the `client_email` in the JSON file). The next step needs this exact
     number.
2. **In the Google Workspace Admin Console** (`admin.google.com` - needs a
   super admin, not just any Workspace user):
   - **Security → Access and data control → API controls → Domain-wide
     delegation → Add new**.
   - **Client ID**: paste the Unique ID copied above.
   - **OAuth scopes**: a comma-separated list of exactly the scopes you
     want this service account able to use. Only add what you actually
     need:
     | Node | Scope |
     |---|---|
     | Email | `https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.modify` |
     | Drive | `https://www.googleapis.com/auth/drive` |
     | Calendar | `https://www.googleapis.com/auth/calendar` |
     | Sheets | `https://www.googleapis.com/auth/spreadsheets` |
   - **Authorize**. This is the step that actually grants the delegation -
     without it, the service account exists but every impersonation
     attempt fails with a clear "domain-wide delegation not authorized"
     error (`app/service_account_auth.py` surfaces this specifically,
     rather than a generic auth failure, since it's such a common thing
     to skip or get slightly wrong).
3. **Back in the hub**: Settings → **Google service account (domain-wide
   delegation)** → paste the entire contents of the JSON key file → Save.
   Then use **Test impersonation** right there on the same card - enter
   the Workspace address you actually want to act as (e.g.
   `hairil@cytron.io`) and confirm it works *before* wiring it into a real
   flow. If it fails, the error names the likely cause (scopes not
   authorized, wrong Client ID, the target address not actually in this
   Workspace) rather than a generic 403.
4. **On any Email/Drive/Calendar/Sheets node**, fill in the **Impersonate**
   field (only visible once step 3 is done) with the Workspace address to
   act as. Leave it blank on any node that should keep using the person
   running the flow's own personal connection instead - the two models
   coexist per-node, not hub-wide.

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

- **Domain-wide delegation is additive, not a replacement for per-user
  OAuth** - a real design decision, not the default choice. Replacing
  OAuth entirely would break the hub for anyone not on Google Workspace
  (personal Gmail accounts can't use domain-wide delegation at all - it's
  a Workspace-only mechanism), so both live side by side: an
  **Impersonate** field on a node, left blank, behaves exactly as before
  this existed; filled in, it switches that one node to service-account
  auth for that one call. The two models are genuinely different things
  (see `service_account_auth.py`'s docstring) sharing the same client
  modules (`gmail_client.py`/`drive_client.py`/`calendar_client.py`/
  `sheets_client.py` each just branch in `_headers()` on whether
  `impersonate` was passed), not one flow with a toggle.
- **Hand-rolled RS256 JWT signing, not `google-auth`.** Consistent with
  every other Google integration in this codebase (plain httpx REST calls
  instead of the official SDKs) - a service account token exchange is
  header + claims + one RSA signature + one POST, and `cryptography`
  (already a dependency, used for the encryption vault) has everything
  needed. Verified this produces genuinely valid tokens, not just
  plausible-looking ones, by decoding a real signed JWT in testing and
  checking the signature against the public key directly - independent
  proof it's spec-correct, not just "the mocked HTTP call accepted it."
- **`google_oauth_warning_for` looks for `.local` names and raw IPs
  before Google gets a chance to reject them.** Found via a real user
  hitting Google's actual error screen - `google_oauth.py`'s docstring
  had claimed "no public domain needed" right up until that happened.
  Now the Settings/Account pages warn before anyone pastes a doomed URI
  into Google Cloud Console, and the fix (a domain, even a free
  dynamic-DNS one pointed at a private IP, or a localhost tunnel) is
  stated directly in the warning rather than left as a mystery error.

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
- **Calendar is a third sibling of Gmail/Drive, not a variant.** Adding a
  new Google product connection is almost entirely mechanical because the
  OAuth machinery was already generic: `calendar_oauth.py` /
  `calendar_tokens.py` / `calendar_client.py` / `calendar_routes.py` mirror
  the Gmail files field-for-field, differing mainly in scopes
  (`calendar.events`, read/write on events but not calendar settings) and
  the API calls themselves. It's a genuinely separate OAuth connection from
  Gmail/Drive, not an added scope on an existing one - someone who already
  connected Gmail isn't silently granted Calendar access, and connecting
  Calendar doesn't force a Gmail re-consent.
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
  (`user_settings.resolve_google_credentials`,
  `user_settings.resolve_openrouter_credentials`) that every caller goes
  through - `google_oauth.py`'s functions take `client_id`/`client_secret`
  as plain arguments rather than looking anything up themselves, so there's
  exactly one place that decides "personal, or fall back to hub-wide." The
  Account page fetches both `/api/settings` (hub-wide, readable by anyone)
  and `/api/account/settings` (personal) and computes the same "which one's
  actually active" logic client-side, so the UI states what's in effect
  right now rather than just listing two separate config forms and leaving
  the relationship to be inferred.
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
