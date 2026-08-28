# Agent Hub — Getting Started, A to Z

This is the complete path from "nothing installed" to "a working team of AI
agents on your own hardware." It assumes no prior familiarity with the
project. If you just want a quick reference after you're up and running,
the three README files (`README.md`, `backend/README.md`, `deploy/README.md`)
are more compact — this guide is the long version, meant to be read once,
start to finish, the first time you set the hub up.

## Table of contents

1. [What Agent Hub actually is](#1-what-agent-hub-actually-is)
2. [What you'll need](#2-what-youll-need)
3. [Installing it](#3-installing-it)
4. [Your first login](#4-your-first-login)
5. [Hub-wide setup (Settings page)](#5-hub-wide-setup-settings-page)
6. [Understanding flows](#6-understanding-flows)
7. [Building your first flow](#7-building-your-first-flow)
8. [The five ways to run a flow](#8-the-five-ways-to-run-a-flow)
9. [Connecting your tools (Connections page)](#9-connecting-your-tools-connections-page)
10. [The node reference](#10-the-node-reference)
11. [Template tour](#11-template-tour)
12. [Team management](#12-team-management)
13. [Your personal settings (Account page)](#13-your-personal-settings-account-page)
14. [Keeping the hub healthy](#14-keeping-the-hub-healthy)
15. [If something goes wrong](#15-if-something-goes-wrong)
16. [Reference tables](#16-reference-tables)

---

## 1. What Agent Hub actually is

Agent Hub is a self-hosted platform for building AI agents as visual flows —
drag nodes onto a canvas, wire them together, and run them. It's built to
run on a Raspberry Pi 5 (or a Windows machine for development), not in
someone else's cloud, so your data and your credentials stay on hardware
you control.

A **flow** is a small directed graph: an Input node, maybe a Knowledge base
or Web search node for context, an LLM node to reason about it, a tool node
(Email, Drive, Sheets, Calendar, Telegram) to act on the result, and an
Output node. Flows can be run by hand, chatted with like a normal
assistant, put on a schedule, wired to answer Telegram messages
automatically, or published as an API another app can call.

The whole thing is one FastAPI backend (SQLite for data, Chroma for
document embeddings) and one React frontend, served together from a single
process. Nothing phones home except the specific external services you
choose to connect (your LLM provider, Google, Telegram, etc.).

## 2. What you'll need

**Hardware** — a Raspberry Pi 5 (4GB+ RAM recommended) is the intended
target, running Raspberry Pi OS. A Windows machine works too, for
development or a smaller-scale personal setup — see
[`deploy/windows-run.ps1`](deploy/windows-run.ps1).

**An LLM provider** — pick one:
- [OpenRouter](https://openrouter.ai) — a hosted API in front of dozens of
  models (Claude, GPT, Llama, etc.). Free tier available, pay-as-you-go
  beyond that. This is the simpler path to start with.
- [Ollama](https://ollama.com) — runs a model locally, no API key, no
  per-token cost, but needs enough RAM/CPU to actually run a model
  reasonably (a Pi 5 can run small models; anything serious wants a
  beefier machine).

**Optional, add these as you need the features they unlock:**
- A Google account, if you want Gmail, Drive, Calendar, or Sheets nodes —
  needs 10 minutes in Google Cloud Console (walked through in
  [Section 9](#9-connecting-your-tools-connections-page)).
- A [Tavily](https://tavily.com) account (free tier, no card) for the Web
  search node.
- A [YouTube Data API](https://console.cloud.google.com) key (free, same
  Google Cloud project as above works) for the YouTube node.
- A Telegram account, if you want a bot you can message directly.
- Any SMTP server/account (even a personal Gmail with an
  [app password](https://support.google.com/accounts/answer/185833)), for
  self-service "Forgot password?" to work.

None of the optional items block you from getting started — the hub runs
fine with just an LLM provider connected, and everything else can be added
later exactly when you need it.

## 3. Installing it

### On a Raspberry Pi (the intended path)

```bash
git clone <your-repo-url> agent-hub   # or copy the project folder over some other way
cd agent-hub
chmod +x deploy/install.sh
./deploy/install.sh
```

This one script does everything: installs Node if it's missing, builds the
frontend, creates a Python virtual environment, installs the backend's
dependencies, installs a systemd service, and starts it. It's safe to
re-run any time — re-running after pulling new code is exactly how you
update by hand (though see [Section 14](#14-keeping-the-hub-healthy) for
the in-browser way).

When it finishes, it prints the address to open — normally:

```
http://agenthub.local:8811
```

If `.local` name resolution doesn't work on your network (some routers or
"isolated" Wi-Fi networks block this), use the Pi's IP address directly:
`hostname -I` on the Pi shows it, then browse to `http://<that-ip>:8811`.

The service is registered with systemd and set to `Restart=always`, so it
comes back up automatically after a reboot or crash. Useful commands:

```bash
sudo systemctl status agent-hub     # is it running?
sudo systemctl restart agent-hub    # restart it
journalctl -u agent-hub -n 50       # see recent logs
```

### On Windows (development / smaller personal setup)

```powershell
cd agent-hub
.\deploy\windows-run.ps1
```

This installs dependencies and starts the server in the foreground (close
the window or press Ctrl+C to stop it — there's no background service on
this path). It prints both `http://localhost:8811` for this machine and
the LAN IP other devices on the same Wi-Fi can use to reach it.

**One thing worth knowing**: the first time it starts listening on a
network port, Windows may show a "Windows Defender Firewall has blocked
some features of this app" popup. Check **both** Private and Public
networks and click "Allow access" — if you miss this, the hub works fine
from this machine but silently isn't reachable from anyone else's.

## 4. Your first login

Open the address from Section 3. You'll see a name and password field —
that's it, no separate "sign up" flow:

- **Typing a name nobody's used yet** creates a new account with that name
  and the password you entered.
- **Typing an existing name** logs you in if the password matches.

**The first person to ever register becomes the hub's admin.** Everyone
after that joins as a regular team member. There's no separate "make me
admin" step — whoever gets there first on a fresh install is it, so do
this yourself before handing the address to your team.

Passwords need to be at least 8 characters. Sessions last 30 days. Five
wrong password attempts on the same name locks that name out for 5
minutes (a simple brute-force throttle, not something you'll normally
notice).

## 5. Hub-wide setup (Settings page)

Log in as the admin and open **Settings** in the sidebar. Everything here
is hub-wide — the whole team uses whatever's configured, unless someone
sets up their own override on their **Account** page (more in
[Section 13](#13-your-personal-settings-account-page)). A non-admin can
see this page but most fields are read-only for them — the one exception
is **software updates**, which any team member can check for and apply.

Work through these cards top to bottom:

### LLM provider

Pick **OpenRouter** or **Ollama**.

- **OpenRouter**: get an API key at
  [openrouter.ai/keys](https://openrouter.ai/keys), paste it in, and set a
  model — `anthropic/claude-3.5-haiku` or `openai/gpt-4o-mini` are
  reasonable, inexpensive defaults for a Pi-hosted hub. See
  [openrouter.ai/models](https://openrouter.ai/models) for the full list
  and current pricing.
- **Ollama**: install it separately, `ollama pull` whatever model you
  want, then set the base URL (`http://localhost:11434` if Ollama runs on
  the same machine) and the model name here.

### Google integration (Gmail + Drive + Calendar + Sheets)

Only needed if you want any of those four nodes to work. Not an OAuth
client this time — a service account key, which sidesteps the fiddliest
part entirely (no consent screen, no redirect address to get right).
Full walkthrough in [Section 9](#9-connecting-your-tools-connections-page);
once you've created the key in Google Cloud Console, paste its entire
JSON contents into this card.

### Web search

A [Tavily](https://tavily.com) API key powers the Web search node — free
tier, no credit card, generous for personal or small-team use.

### YouTube search

A YouTube Data API key (from the same Google Cloud project as above, or a
separate one) powers the YouTube node. Enable "YouTube Data API v3" in
Google Cloud Console, then Credentials → Create Credentials → **API key**
(not an OAuth client — this one's simpler, just a key). Free tier covers
roughly 100 searches a day.

### Outgoing email (SMTP)

Powers "Forgot password?" on the login screen. Any SMTP server works,
including a personal Gmail account with an
[app password](https://support.google.com/accounts/answer/185833) (not
your normal Gmail password — Google blocks plain-password SMTP login):
host `smtp.gmail.com`, port `587`, STARTTLS on. Once saved, use "Send a
test email" right there on the card to confirm it actually works —
genuinely worth doing now, not during an actual lockout later.

### Software updates

Defaults to pulling from the project's own repository. If you're running
your own fork, change the repo/branch here (admin-only). "Check for
updates" and "Update now" are open to the whole team — see
[Section 14](#14-keeping-the-hub-healthy).

## 6. Understanding flows

A flow is a small graph. Every node takes in one thing (whatever the
previous node produced, or the original input if it's first) and produces
one thing for whatever comes next. That's the entire mental model — no
branching, no loops, just a straight line (or a short tree) from Input to
Output.

**Node categories**, color-coded on the canvas:
- **Input / Output** (gray) — where a run starts and ends.
- **LLM** (copper/orange) — asks a language model something.
- **Tools** (green) — everything else: search, email, files, spreadsheets,
  calendar, messaging, calculation.

**A genuinely important detail**: if a tool node runs right before an LLM
node, the LLM sees *both* the tool's output *and* whatever the original
message was — not one or the other. So a Knowledge base node's search
results don't silently replace the question that was actually asked; the
model gets to reason about both together.

**Building a flow**: open **Flows** in the sidebar, either start from a
template or click "New blank flow." Drag node types from the left panel
onto the canvas, or click one to drop it in. Click a node to configure it
in the right-hand panel. Drag from one node's edge to another's to
connect them. Hit **Save** in the toolbar when you're happy — nothing
persists until you do.

## 7. Building your first flow

The fastest way to see the whole loop working: open **Flows**, click
**"Your first agent"** under "Start from a template." This is the
simplest possible flow — three nodes:

```
Input → LLM ("You are a friendly, concise assistant.") → Output
```

Scroll down and click **"Run this flow"**, type something, and watch the
reply come back — plus a step-by-step trace showing exactly what each
node did, which is worth looking at even here: it's the same trace every
flow produces, and it's how you debug a more complicated one later.

Once that works, you've proven the LLM provider you set up in Section 5
is actually working end to end. Everything else in this guide builds on
top of that same loop.

## 8. The five ways to run a flow

A flow you've built can be invoked in five different ways, each suited to
a different situation:

| Way | Where | Good for |
|---|---|---|
| **Run** | Flow editor toolbar, bottom panel | Testing while you build — always a fresh one-shot, no memory between runs |
| **Chat** | "Chat" button in the flow editor toolbar | Talking to it like a normal assistant — remembers the conversation, back-and-forth |
| **Schedule** | "Schedule" button | Runs on its own on an interval or daily at a set time — no one has to be there |
| **Telegram trigger** | "Telegram" button | Message a connected bot from your phone and get an automatic reply — checked every few seconds in the background, same conversation memory as Chat |
| **Publish** | "Publish" button | Generates an API key so an external website, script, or MCP client can call this one flow — as a plain REST endpoint (`X-API-Key`), or as an MCP server (same key, as a Bearer token) |

**Chat and Telegram triggers share the same underlying memory system** —
a conversation started one way can be viewed from the other (the Telegram
trigger's status modal has a direct link to view its conversation in
Chat).

A flow meant to be used with Chat or a Telegram trigger should just be
**Input → (tools) → LLM → Output** — don't add an explicit "send" node for
Telegram or email inside it, since the trigger/Chat interface already
handles delivering the reply. Adding your own send step on top would
deliver the answer twice.

## 9. Connecting your tools (Connections page)

**Gmail, Drive, Calendar, and Sheets are hub-wide, not per-person** — one
Google service account, set up once by an admin, that every flow uses.
A node's **Impersonate** field decides what it acts as for that one
call: left blank, the service account's own identity; set to a real
address, that specific person (needs a Workspace admin's one-time
sign-off — Section 9 below covers exactly when that's needed).

**Telegram bots are a shared resource, working the same way** — a bot
belongs to whichever flow it's wired into, regardless of who runs that
flow. This is what lets a Customer Support flow and a completely separate
Sales flow message through two different bots even if the same person
built both.

### Setting up Google (Gmail / Drive / Calendar / Sheets)

One hub-wide service account, not a per-person "Connect" flow — no
consent screen, no redirect address to get right, nothing that depends
on how you're reaching the hub. Do this once, as the admin:

1. In [Google Cloud Console](https://console.cloud.google.com), create a
   project (or use an existing one).
2. **Enable whichever APIs you actually need**: APIs & Services →
   Library → search for and enable **Gmail API**, **Google Drive API**,
   **Google Calendar API**, and/or **Google Sheets API**.
3. **IAM & Admin → Service Accounts → Create Service Account.** Name it
   whatever's clear (e.g. "agent-hub"). No roles need to be granted here.
4. Open the new service account → **Keys → Add Key → Create new key →
   JSON**. This downloads the only copy of the private key.
5. Back on the hub's **Settings** page, find the **Google (Gmail / Drive
   / Calendar / Sheets)** card → paste the entire contents of that JSON
   file → Save. It should show "Configured" with the service account's
   own email.
6. On any Email/Drive/Calendar/Sheets node in a flow, there's now an
   **Impersonate** field. Leave it blank and the node acts as the
   service account's own identity — this works immediately for
   Drive/Sheets/Calendar (its own space, or anything explicitly shared
   with its email address, the same way you'd share a folder with a
   colleague). Gmail specifically has no real inbox for a plain service
   account, so an Email node needs step 7 below.
7. **To act as a specific real person** (needed for Gmail, optional for
   the others): a Google Workspace super admin authorizes this exact
   service account, once, in the **Workspace Admin Console**
   (admin.google.com — a different site from Cloud Console, needing
   different, higher access) → Security → Access and data control → API
   controls → Domain-wide delegation → Add new. Paste the service
   account's **Client ID** (on its detail page in Cloud Console, labeled
   "Unique ID"), and the specific scopes needed (the Settings card lists
   the exact scope string per service) → Authorize.
8. Back on the Settings card, use **Test** to confirm it actually works
   — with an email address to test impersonation, or blank to test the
   service account's own identity — before wiring it into a real flow.

This is a bigger trust decision than the old "everyone connects their
own account" model would have been: whoever controls this one key can
make it act as anyone a Workspace admin has authorized it for, not just
themselves. That's exactly why it's admin-only to set up.

### Setting up Telegram bots

No Google Cloud project needed — anyone can create as many bots as they
want:

1. In Telegram, message **@BotFather**, send `/newbot`, follow the
   prompts. It replies with a token.
2. On Connections, click **"Add a bot"** — give it a name (shown in a
   Telegram node's picker later), paste the token, choose whether it's
   shared with the team or private to you.
3. Message that bot on Telegram (search for its username) — send it
   anything.
4. Back on Connections, click **"Finish linking"** on that bot.

Repeat for as many bots as you want. To make a bot answer messages
automatically instead of only being usable *by* a flow, see the Telegram
trigger row in [Section 8](#8-the-five-ways-to-run-a-flow).

## 10. The node reference

| Node | What it does |
|---|---|
| **Input** | Where a run starts — whatever's typed (Run/Chat) or arrives (Telegram, a schedule's fixed input) |
| **LLM** | Asks a language model something, with an optional system prompt |
| **Knowledge base** | Searches documents you've uploaded (PDF/DOCX/CSV/TXT/MD), returns matching chunks |
| **Web search** | Live web search via Tavily |
| **YouTube** | Searches YouTube, returns titles/channels/descriptions/view counts |
| **Email** | Send or search Gmail |
| **Drive** | List, read, or create files in Google Drive |
| **Sheets** | Create a spreadsheet, read it, or **update a row in place** (find by a key in the first column, update that row, or append if it's new) |
| **Calendar** | List upcoming events, or create a new one |
| **Telegram** | Send a message or read recent ones, through a specific bot |
| **Call Flow** | Runs a different flow as a step and uses its output — one agent calling another |
| **MCP** | Calls one tool on an external MCP server — the same kind of server Claude Desktop connects to |
| **Calculator** | Evaluates a math expression safely |
| **Output** | The final result of the run |

The Sheets node deserves a special note since it's easy to miss: unlike
Drive (which can only create or fully overwrite a file), Sheets can edit
one row of an existing spreadsheet without touching anything else — this
is what makes an ongoing tracker possible (see the SIRIM CoC Progress
Tracker template below). A Sheets node references a fixed spreadsheet ID,
the same way a Knowledge base node references a fixed `kb_id` — there's no
"create if missing" magic. Create the spreadsheet once (temporarily switch
the node to "Create," run it, copy the ID it returns), then point every
node that updates it at that same ID.

**Call Flow is how one agent uses another** — pick this over building
everything into one giant flow when a piece of logic is genuinely its own
agent (a specialized flow other flows want to reuse, or a router flow
that delegates to whichever specialist fits the request). The called
flow always starts fresh — no memory of the calling flow's conversation
— and its final output becomes this node's output, the same as any other
tool node. A flow can't be made to call itself, directly or through a
chain of other flows — the hub catches that and gives a clear error
rather than hanging or crashing.

**MCP is how a flow reaches tools outside Agent Hub entirely** — point a
node at any MCP server's URL (the same kind of external tool server
Claude Desktop or Claude.ai connects to), click **List tools** to see
what it offers, and pick one. The node's input needs to be JSON matching
that tool's expected arguments — the config panel shows the exact schema
once you've picked a tool, so an LLM node just before it can be prompted
to produce the right shape. A tool that only takes one plain argument
doesn't need JSON at all — plain text gets wrapped automatically.

**Publishing a flow also makes it an MCP server, automatically — no
separate step.** Click Publish, and alongside the usual REST curl
example, the same modal shows an MCP server URL using the same API key.
Any MCP client can call it — including this hub's own MCP node, pointed
at another flow's published MCP URL, which is the second way "one agent
uses another" can work here: Call Flow for same-hub composition (no
network, no key needed), MCP for reaching a flow published from anywhere
— this hub or a different one — the same way any external MCP tool would
be reached.

## 11. Template tour

Every template below is available from Flows → "Start from a template."
They're a starting point, not a fixed recipe — open one, look at how it's
wired, and adjust the system prompt or config to fit what you actually
need.

**Learning the basics:**
- **Your first agent** — Input → LLM → Output. The simplest possible flow.
- **Ask your documents** — adds a Knowledge base node before the LLM, so
  answers are grounded in files you've uploaded instead of the model's
  general knowledge.
- **Quick calculator** — no model at all, just a deterministic expression
  evaluator.

**Notifications and simple automation:**
- **Inbox digest** — searches your inbox, asks a model to summarize what
  it finds.
- **Save notes to Drive** — turns typed notes into a file in Drive.
- **Notify me on Telegram** — tidies up whatever you type and sends it to
  your phone. Good one to put on a Schedule.

**The nine named agents:**
- **Customer Support Assistant** / **HR Policy Assistant** / **Technical
  Support Agent** — all the same shape (Knowledge base → LLM), pointed at
  different documents. Best used through Chat, not Run, since a real
  support conversation needs to remember earlier messages.
- **Product Recommendation Agent** — same shape, tuned to ask clarifying
  questions before recommending.
- **Meeting Summarizer** — paste a transcript, get a structured summary
  with decisions and action items.
- **Research Assistant** / **Restaurant Recommendation Agent** — Web
  search → LLM, for anything needing current information a static
  knowledge base can't provide.
- **Student Learning Assistant** — a tutor that checks understanding
  rather than just handing over answers. Genuinely needs Chat, not Run.
- **Personal Productivity Coach** — pulls your next few Calendar events as
  context for every check-in. Needs the Calendar node's Impersonate field
  set to your address (Section 9).

**Content research:**
- **YouTube Video Idea Generator** — searches a topic on YouTube, proposes
  concrete new video ideas based on what's covered well versus what's
  thin or missing. Needs a YouTube API key.

**A complete worked example — SIRIM CoC Progress Tracker:**
- Reads certification-related emails, extracts what changed for each
  application, and keeps a Google Sheet current — updating the existing
  row for an application already being tracked instead of creating a
  duplicate. Needs the Google service account set up (Section 9), plus
  the one-time spreadsheet-setup step described in
  [Section 10](#10-the-node-reference). Put it on a Schedule once it's
  working, for a tracker that keeps itself current with no one touching
  it.

## 12. Team management

The **Team** page (visible to everyone, most actions admin-only) shows
everyone registered on the hub, their role, and lets an admin:

- **Reset a teammate's password** — useful since there's no requirement
  that everyone set up a recovery email.
- **Promote or demote a team member** — "Make admin" / "Remove admin" next
  to anyone but yourself, if you're an admin. The API also refuses to
  demote the only remaining admin, so you can't accidentally leave the
  hub without one.
- **Remove someone** — blocked if they're the last admin, or if you try to
  remove yourself. Anything they owned (flows, knowledge bases,
  documents, schedules, Telegram bots) transfers to the admin doing the
  removal rather than vanishing; their personal connections (Gmail,
  Drive, etc.) are deleted outright, since handing someone else's OAuth
  token to another person wouldn't make sense.

Both actions are admin-only, and neither is available to use on your own
account (you can't demote or remove yourself from here).

## 13. Your personal settings (Account page)

Personal to you — nobody else, including admins, can see what's here.
Everything is optional; the hub works fine using hub-wide defaults for
all of it.

- **Recovery email** — needed for "Forgot password?" to work for your
  account specifically.
- **Password** — change it any time; this signs you out of every other
  active session.
- **Your own OpenRouter key and model** — takes over for flows *you*
  personally run, so your usage bills to your own account rather than a
  shared one. Other people running the same flow are unaffected.
- **Your own Tavily / YouTube keys** — same idea: if the hub-wide default
  isn't set (or you'd rather not share your quota), add your own so Web
  search / YouTube nodes work in flows you personally run.

## 14. Keeping the hub healthy

### Updating

Settings → Software updates → **"Check for updates"** compares what's
installed against the configured repo/branch; **"Update now"** downloads,
rebuilds, and restarts — entirely from the browser, no SSH needed. Any
team member can do both (choosing *which* repo to pull from stays
admin-only). Since this restarts the hub for everyone currently using it,
you'll be asked to confirm first.

User data lives entirely outside the code directory an update touches
(`~/.agent-hub` by default), so an update can't accidentally wipe your
flows, knowledge bases, or accounts.

### Backups

Everything that matters is one folder: `~/.agent-hub` (or wherever
`AGENT_HUB_DATA_DIR` points). Back that up and you've backed up every
flow, account, uploaded document, and connection. The code itself is
disposable — it's just whatever's in the git repo.

### Password recovery — three tiers

1. **Self-service** ("Forgot password?" on the login screen) — needs a
   recovery email set on that account, and SMTP configured hub-wide
   (Section 5). Sends a single-use link, valid for an hour.
2. **An admin resets it** — Team page, works regardless of whether SMTP
   or a recovery email is set up.
3. **The only admin is locked out, with no recovery email and no SMTP
   configured** — from a terminal on the machine the hub runs on:
   ```bash
   cd agent-hub/backend
   python3 reset_password.py
   ```
   Lists every account, asks which one, asks for a new password twice,
   sets it exactly the way a normal reset would. This is a local-shell
   tool on purpose, not a web endpoint — anyone who can run it already has
   full access to the database file itself.

## 15. If something goes wrong

**Can't reach the hub from another device on the same Wi-Fi, even by IP
address:**
1. Confirm it's running: `sudo systemctl status agent-hub` on the Pi.
2. Confirm the IP hasn't changed: `hostname -I` on the Pi (DHCP can hand
   out a new one after a reboot if it's not reserved/static).
3. Check for a Pi-side firewall: `sudo ufw status` — if active and 8811
   isn't allowed, `sudo ufw allow 8811`.
4. Router/Wi-Fi client isolation — some routers (especially guest
   networks) block devices on the same Wi-Fi from reaching each other
   entirely. A router setting, not fixable from the Pi.
5. On Windows specifically: check Windows Defender Firewall → "Allow an
   app through firewall" → make sure Python/uvicorn is checked for both
   Private and Public networks.

**`agenthub.local` doesn't resolve, but the IP address works fine:** some
networks block mDNS specifically — just use the IP going forward.

**"Not configured yet" on a Google node even after saving a service
account key:** double check the entire JSON file was pasted (not just
part of it) and that the Settings card actually shows "Configured" with
an email address after saving — if it doesn't, the key was rejected;
the error message on save says why.

**An Email/Drive/Calendar/Sheets node fails with a Google error
mentioning "domain-wide delegation" or "unauthorized_client":** the
Impersonate field is set to a real address, but a Workspace super admin
hasn't authorized this exact service account for that scope yet in the
Workspace Admin Console — see Section 9, step 7. Use the "Test" button
on the Settings card to confirm this specific combination works before
trusting it in a real flow.

**An Email node fails even with Impersonate left blank:** expected — a
plain service account has no real inbox of its own for Gmail. Set
Impersonate to a real Workspace address (needs step 7 above) rather than
leaving it blank, which only really works for Drive/Sheets/Calendar.

**Checking for updates gives an error:** if it mentions GitHub — a 404
usually means the configured repo/branch is wrong or private (this check
is anonymous, so it can only see public repos); a 403 usually means
GitHub's anonymous rate limit (60 requests/hour, shared by everyone
checking from your network) — wait a bit and try again.

**A Knowledge base upload sits at "processing" forever:** the local
embedding model downloads on its first real use (roughly 130MB) — it
needs internet the first time, then works offline. Check the logs
(`journalctl -u agent-hub`) to see if that download is stuck.

**A flow fails immediately with a clear error naming a specific node:**
that's intentional — every node validates its own configuration and
raises a specific, readable message (missing spreadsheet ID, no bot
selected, API key not configured, etc.) rather than a generic failure.
Read the node it names; the fix is almost always right there.

## 16. Reference tables

### Default ports and paths

| What | Value |
|---|---|
| Web address | `http://agenthub.local:8811` or `http://<pi-ip>:8811` |
| Data directory | `~/.agent-hub` (override with `AGENT_HUB_DATA_DIR`) |
| Database | `~/.agent-hub/agent_hub.db` (SQLite) |
| systemd service name | `agent-hub` |
| Default update repo | the project's own repository/`main` branch |

### Settings page fields (admin-only to change)

| Card | Fields |
|---|---|
| LLM provider | OpenRouter API key + model, or Ollama base URL + model |
| Google integration | Service account JSON key |
| Web search | Tavily API key |
| YouTube search | YouTube API key |
| Outgoing email | SMTP host, port, username, password, from address, TLS |
| Software updates | GitHub repo, branch |

### Account page fields (personal, no admin needed)

| Field | Overrides |
|---|---|
| Recovery email | — (used for password reset only) |
| Password | — |
| Your own OpenRouter key/model | the hub-wide LLM provider |
| Your own Tavily key | the hub-wide Web search key |
| Your own YouTube key | the hub-wide YouTube key |

### Every node type

`input` · `llm` · `knowledge_base` · `web_search` · `youtube` · `email` ·
`drive` · `sheets` · `calendar` · `telegram` · `calculator` · `output`

### Every template

`first-agent` · `ask-your-documents` · `quick-calculator` ·
`inbox-digest` · `save-notes-to-drive` · `notify-me-on-telegram` ·
`customer-support-assistant` · `product-recommendation-agent` ·
`meeting-summarizer` · `hr-policy-assistant` · `research-assistant` ·
`technical-support-agent` · `student-learning-assistant` ·
`restaurant-recommendation-agent` · `personal-productivity-coach` ·
`youtube-video-idea-generator` · `sirim-coc-progress-tracker`

---

That's the whole path. From here, `README.md` (project overview),
`backend/README.md` (everything technical — API routes, design
rationale, the full test suite), and `deploy/README.md` (deployment
detail and troubleshooting) are the places to go deeper on any one piece.
