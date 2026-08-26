# Setting up the SIRIM CoC Progress Tracker — reading hairil@cytron.io's inbox

## Two ways to do this — read this before picking one

Gmail access in Agent Hub normally works as a **personal connection**:
whoever runs a flow, it acts as their own Google account. There's no
"connect Gmail for hairil" button anyone else can click *for* him under
this model — Google's OAuth consent screen requires **hairil personally**
to log in and click Allow. Nobody else can do that step, including a hub
admin — a deliberate, good security property.

Since you've since confirmed `cytron.io` is Google Workspace, there's now
a **second, completely different way** that avoids needing hairil to
personally do anything at all: **domain-wide delegation**. A Workspace
super admin authorizes one service account, once, in the Workspace Admin
Console, to act as anyone in the organization for chosen Google scopes.
From then on, a flow's Email/Sheets node can target `hairil@cytron.io`
directly via an "Impersonate" field - no consent screen, no redirect URI,
and no OAuth involved at all for that node.

**Given what you've already run into** (the `.local` redirect rejection,
then the private-IP "device_id" error) **domain-wide delegation is
probably the smoother path forward from here** - it sidesteps both of
those entirely, since there's no browser redirect for Google to reject in
the first place. It needs one thing the personal-OAuth path doesn't:
**Workspace super admin access** to `cytron.io`'s Admin Console (not just
a Google Cloud Console project) to actually authorize the delegation. If
you have that, skip to **Path B** below. If you don't (and can't easily
get someone who does to spend five minutes on it), **Path A** - the
personal OAuth walkthrough - still works fine, and is genuinely easy now:
Settings has a built-in **DuckDNS** card that gets you a working domain
in about two minutes, with nothing to maintain afterward (see the callout
in Part 2 below).

---

# Path A — personal OAuth (hairil connects his own account)

This has one direct, unavoidable consequence for your setup: **the flow
has to run *as hairil* for it to search hairil's inbox.** And since a
Sheets node and an Email node in the same flow run always act as the same
person (a single flow run has one identity, not a different one per
node), the tracker spreadsheet will also end up living in **hairil's**
Google Drive, created under his own connection — not yours.

So the work splits like this:

| Step | Who does it |
|---|---|
| Google Cloud Console setup | You (or whoever manages `sirim-coc-agent`) |
| Agent Hub hub-wide Settings | An admin (might be you) |
| Building the flow from the template | Either of you — flows are shared by default |
| Connecting Gmail + Sheets | **Hairil, personally** |
| Creating the tracker spreadsheet (one-time) | **Hairil**, since it runs as him |
| Setting up the Schedule | **Hairil**, since a schedule runs as whoever created it |

If hairil would rather not personally touch the hub at all, **Path B**
below (domain-wide delegation) is exactly that alternative - built and
ready to use, not a hypothetical.

---

## Part 1 — Google Cloud Console (your `sirim-coc-agent` project)

You already have the project, so skip straight to configuring it.

### 1.1 Enable the two APIs this agent needs

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and
   make sure **sirim-coc-agent** is the selected project (top-left project
   picker).
2. Left sidebar → **APIs & Services → Library**.
3. Search for **Gmail API** → click it → **Enable**.
4. Search for **Google Sheets API** → click it → **Enable**.

(If you also want Calendar or Drive nodes for other agents later, enable
those two APIs the same way now — costs nothing to leave enabled. Not
needed for this specific tracker.)

### 1.2 Configure the OAuth consent screen

1. **APIs & Services → OAuth consent screen**.
2. **User type — check what's actually offered here**: since `cytron.io`
   is on Google Workspace, you may see **Internal** as an option, not just
   External. This depends on whether `sirim-coc-agent` was created under
   an `@cytron.io` account that belongs to the organization (not a
   personal Gmail account) — if so, Google shows Internal as a choice.
   - **If Internal is available, use it.** It skips the Test Users list
     entirely (anyone in your Workspace org can connect without being
     added by name) and skips the scary "unverified app" warning during
     consent — since an internal app is implicitly trusted within your
     own organization. If you pick this, **skip step 4 below** — there's
     no Test Users section for an Internal app.
   - **If you only see External** (the project isn't tied to the
     org, or the console doesn't offer Internal for some other reason),
     that's fine too — follow step 4 below, it works the same as any
     non-Workspace setup.
3. Fill in the required fields (app name, support email, developer
   contact) — these are just labels shown on the consent screen, they
   don't need to be anything special.
4. **Only if you're on External** — this step is easy to miss and breaks
   everything if skipped: while the app is in **Testing** mode (the
   default), Google silently refuses to let anyone sign in who isn't
   explicitly listed. Scroll to **Test users** → **Add users** → add
   **both**:
   - `hairil@cytron.io`
   - your own Google account, if you also want to connect anything
     personally later

   If hairil isn't on this list, his "Connect Gmail" attempt will fail on
   Google's side, before it even gets back to the hub.

### A note on domain-wide delegation, since you're on Workspace

Since `cytron.io` is Google Workspace, there's a second way to do all of
this that skips OAuth (and everything below about Test Users/Internal
apps/redirect URIs) entirely: **domain-wide delegation** — see **Path B**
at the end of this document. It needs Workspace super admin access to set
up, but once it's done, hairil never has to personally connect anything.
Worth reading before continuing further down this OAuth path, especially
if you've already hit friction with redirect URIs.

### 1.3 Create the OAuth client

1. **APIs & Services → Credentials → Create Credentials → OAuth client
   ID**.
2. Application type: **Web application**.
3. Name it whatever you like (e.g. "Agent Hub").
4. **Leave this tab open** — the next part tells you exactly what to paste
   into "Authorized redirect URIs" here.

## Part 2 — Agent Hub Settings page (admin)

1. Log into the hub as an admin, open **Settings**.
2. Find the **Google integration** card. It shows four redirect URIs
   (Gmail, Drive, Calendar, Sheets) with a Copy button next to each —
   these are computed from however you're currently reaching the hub, so
   they're always correct, nothing to type by hand.
3. **If there's a red warning above those URIs, stop and read it before
   continuing to step 4.** It means the address you're currently using to
   reach the hub — almost always a `.local` name or a raw LAN IP — will
   be rejected by Google's OAuth client with a confusing error ("must use
   a domain that is a valid top private domain") no matter how carefully
   you copy it in. This isn't specific to the SIRIM setup; it's a hard
   Google requirement.

   **The fix**: scroll down to the **Free remote domain (DuckDNS)** card
   on this same Settings page. Get a free token at
   [duckdns.org](https://www.duckdns.org) (sign in with an existing
   Google/GitHub account), pick a subdomain (e.g. `sirim-agenthub`),
   paste both in, and save. The hub then keeps that domain pointed at
   itself automatically from here on - checking every few minutes in the
   background, so it keeps working even after a reboot changes the Pi's
   IP. Once it's set, reload this Settings page: the warning above
   switches to telling you the exact new address (something like
   `http://sirim-agenthub.duckdns.org:8811`) - use *that* address for the
   rest of this setup, including hairil's Connect steps in Part 4.

   If you genuinely can't use DuckDNS, a one-time-only fallback still
   works: do this step (and the Connect steps in Part 4) from a browser
   on the same machine the hub runs on, using `http://localhost:8811`
   instead — Google's other real exception, no domain needed. An SSH
   local port-forward (`ssh -L 8811:localhost:8811 you@pi`) lets you do
   this from your own laptop. This only covers the Connect step though,
   not day-to-day use of the hub.

   If there's no warning, you're already reaching the hub through
   something Google will accept — carry on to step 4.
4. Copy **all four** into the OAuth client's "Authorized redirect URIs"
   list back in the Google Cloud Console tab, then **Save** on the Google
   side.
5. Back in Google Cloud Console, open the OAuth client you just created
   and copy its **Client ID** and **Client secret**.
6. Paste both into the Google integration card on the Settings page and
   hit **Save**. Takes effect immediately, no restart needed.

This part is a one-time, hub-wide setup — hairil doesn't need to do
anything for this section.

## Part 3 — Build the flow

Do this part yourself; it doesn't need to be done by hairil, since a
shared flow is visible and editable by anyone on the hub with access to
it (that includes him once he's registered).

1. Open **Flows** → under "Start from a template," click **"SIRIM CoC
   Progress Tracker."**
2. This creates a new flow: **Input → Email → LLM → Sheets → Output**,
   visibility "shared" by default — leave it shared so hairil can see and
   finish configuring it himself.
3. That's it for this part — don't try to connect anything or fill in the
   spreadsheet ID yourself; those specifically need to happen as hairil
   (see Part 5), since they'll be tied to his account and his Drive.

If hairil doesn't have a hub account yet, get him one now — either he
registers himself at the hub's address (name + password), or you create
one and hand him the password. Either way, he doesn't need to be an
admin for any of this.

## Part 4 — Hairil connects his own accounts

**Hairil does this part, logged in as himself.**

1. Log into the hub, open **Connections**.
2. Next to **Gmail**, click **Connect**. This sends him to Google's real
   consent screen — since he's listed as a Test User, it'll show an
   "unverified app" warning (expected, since this app hasn't gone through
   Google's formal review) — click **Advanced → Go to (app name)**, then
   **Allow**.
3. Next to **Google Sheets**, click **Connect** the same way.

Both should now show "Connected" with his email address next to them.

## Part 5 — One-time: create the tracker spreadsheet

**Hairil does this part too** — the spreadsheet needs to be created while
running as him, so it lands in his Drive under his own connection.

1. Open the SIRIM CoC Progress Tracker flow (from Flows — it's shared, so
   it'll show up for him).
2. Click the **Sheets** node on the canvas.
3. Change **Action** from "Update a row" to **"Create a new spreadsheet."**
4. Fill in:
   - **Title**: something like "SIRIM CoC Tracker"
   - **Column headers**: `Application ID, Status, Notes`
   - **Tab name**: leave as `Sheet1`
5. Scroll down, click **"Run this flow"** (any text in the input box is
   fine — it's not used by the Create action). Check the run's output/trace
   for a line like `Created spreadsheet '...' - id: 1BxiMV...`
6. Copy that spreadsheet ID.
7. Click the Sheets node again, switch **Action** back to **"Update a row
   (or add if new)."**
8. Paste the copied ID into **Spreadsheet ID**. Leave Tab name as
   `Sheet1`.
9. Click **Save** in the toolbar (top right) — this step matters, the
   config isn't kept otherwise.

You (or hairil) can open that spreadsheet directly at
`https://docs.google.com/spreadsheets/d/<the-id>` to watch it fill in as
the tracker runs.

## Part 6 — Adjust the search query to match his actual inbox

Click the **Email** node. The default search query is:

```
SIRIM OR "CoC" OR "certificate of conformance" OR "certificate of conformity"
```

This is a reasonable starting point but almost certainly needs narrowing
once you see what actually shows up — Gmail search syntax works here, so
you can tighten it once you know the real senders, for example:

```
from:sirim-qas.com.my OR from:compliance-partners.com
```

or add a label if hairil files these emails somewhere specific:

```
label:sirim-coc
```

Whoever's better positioned to look at what's actually landing in the
inbox (probably hairil) should be the one to tune this — run the flow a
couple of times with **Run**, look at the trace to see what the Email
node actually pulled back, and narrow the query until it's picking up the
right messages without too much noise.

## Part 7 — Set up the Schedule

**Hairil does this part** — a schedule runs as whoever created it, so if
you create it, it'll try to run as you (and fail to find his emails, or
worse, search yours instead if you happen to have Gmail connected too).

1. With the flow open, click **Schedule** in the toolbar.
2. Click **"Add schedule."**
3. **Runs**: pick "Every N minutes" for something like every few hours
   (e.g. `240` for every 4 hours), or "Once a day" at a specific time
   (e.g. `09:00`) if a daily check is often enough for how quickly SIRIM
   applications actually move. Either is reasonable for this — there's no
   need for anything faster than hourly for a certification process that
   moves over days/weeks.
4. **Input**: this field doesn't matter for this particular flow — the
   Email node's search query is fixed in its own config, not driven by
   this input. Type anything, e.g. "Check CoC emails."
5. Click **Create schedule**.

The schedule modal shows a run history once it's fired at least once —
worth checking back after the first scheduled run to confirm it actually
found and processed what you expected.

## Part 8 — Test it end to end before trusting the schedule

Before walking away and letting the schedule run unattended:

1. As hairil, click **"Run this flow"** manually once.
2. Check the trace — does the Email node show real messages? Does the LLM
   step output lines that look like `SIRIM-xxxx | status | note`? Does the
   Sheets node say "appended" or "updated"?
3. Open the actual spreadsheet and confirm the row looks right.
4. Run it again with no new relevant emails in the meantime — the output
   should say `(nothing to update)`, and the spreadsheet should be
   unchanged. This confirms it won't create duplicate or garbage rows on
   a routine check that finds nothing new.

Once both of those look right, the schedule from Part 7 can run
unattended with reasonable confidence.

---

## If something doesn't work

- **"Connect Gmail" fails immediately for hairil**: if you're on
  **External**, almost always means he isn't listed under Test users on
  the OAuth consent screen (Part 1.2). If you're on **Internal**, check
  that hairil's account is genuinely part of the same Workspace
  organization as the project — an Internal app rejects anyone outside
  the org, with no Test Users list to fix it from. Either way, also
  double check the Gmail/Sheets APIs are actually enabled (Part 1.1).
- **Google Cloud Console rejected a redirect URI with "must use a domain
  that is a valid top private domain" or "must end with a public
  top-level domain"**: you were pasting in a `.local` address or a raw
  LAN IP — see the callout in Part 2, step 3.
- **The tracker runs but finds no emails**: the search query (Part 6) is
  probably too narrow, or too specific to wording that doesn't match how
  these emails are actually worded. Loosen it and check the trace.
- **Rows keep duplicating instead of updating**: means the LLM's output
  isn't using a *consistent* key (the first value before the first `|`)
  for the same application across different emails — check the trace's
  LLM step output and see if it's inventing a new identifier each time
  instead of reusing the SIRIM reference number. Tightening the system
  prompt to be stricter about reusing exact reference numbers usually
  fixes this.
- **The schedule doesn't seem to be running**: open the Schedule modal and
  check it's toggled on (enabled), and look at its run history for
  errors.

---

# Path B — domain-wide delegation (no OAuth, hairil does nothing)

The genuinely different part of this path: **one person (you, or whoever
has Workspace super admin rights) does the entire setup alone.** Hairil
never logs into the hub, never sees a consent screen, never does
anything. The flow acts as him through the service account, on every
node that has his address in its "Impersonate" field.

## B1 — Google Cloud Console (your `sirim-coc-agent` project)

1. Make sure **Gmail API** and **Google Sheets API** are enabled (APIs &
   Services → Library → search each → Enable) - same as Part 1.1 in Path
   A, if you already did that, nothing more to do here.
2. **IAM & Admin → Service Accounts → Create Service Account.** Call it
   something clear, e.g. `sirim-coc-tracker`. No roles needed on this
   screen - skip that step.
3. Open the new service account → **Keys → Add Key → Create new key →
   JSON**. This downloads a file - it's the only copy of the private key,
   keep it safe until step B3.
4. On the same service account page, copy its **Unique ID** (a long
   number, sometimes labeled "OAuth2 Client ID") - needed for the next
   step.

## B2 — Google Workspace Admin Console (needs a super admin)

This is a **different website** from Cloud Console -
[admin.google.com](https://admin.google.com), and needs someone with
Workspace super admin rights specifically, not just any `@cytron.io`
account.

1. **Security → Access and data control → API controls → Domain-wide
   delegation → Add new.**
2. **Client ID**: paste the Unique ID from B1.4.
3. **OAuth scopes**, comma-separated - only what this tracker actually
   needs:
   ```
   https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/spreadsheets
   ```
4. **Authorize.** This is the step that actually grants it - skipping it
   is the most common reason impersonation fails later with an
   "unauthorized_client" error.

## B3 — Agent Hub Settings page (admin)

1. Open **Settings** → **Google service account (domain-wide
   delegation)**.
2. Paste the entire contents of the JSON file from B1.3 → **Save**. The
   card should now show "Configured" with the service account's own
   email address.
3. Use **Test impersonation** right there: enter `hairil@cytron.io`,
   scope "Gmail", click **Test**. Confirm it succeeds before moving on -
   if it fails, the error names the likely cause (scopes not authorized
   in B2, wrong Client ID, or `hairil@cytron.io` not actually part of
   this Workspace).

## B4 — Build the flow (you do this whole part alone)

1. Open **Flows** → **"SIRIM CoC Progress Tracker"** template.
2. Click the **Email** node → set **Impersonate** to `hairil@cytron.io`.
3. Click the **Sheets** node → set **Impersonate** to `hairil@cytron.io`
   as well (the Sheets node's own auth is independent of the Email
   node's, so both need it set).

## B5 — One-time: create the tracker spreadsheet

Same idea as Path A, but you can do this step yourself now - the sheet
still ends up in **hairil's** Drive, because the node is impersonating
him, regardless of who clicks Run.

1. Click the Sheets node, switch **Action** to "Create a new
   spreadsheet." Confirm **Impersonate** is still set to
   `hairil@cytron.io`.
2. Title: "SIRIM CoC Tracker". Headers: `Application ID, Status, Notes`.
3. Run the flow once, copy the returned spreadsheet ID from the trace.
4. Switch the Sheets node back to "Update a row," paste the ID into
   **Spreadsheet ID**, keep **Impersonate** set. **Save.**

## B6 — Adjust the search query, set up the Schedule

Same as Path A's Part 6 and Part 7 - except **you** can do the Schedule
step too now, since the flow's Google access comes from impersonation on
the nodes, not from whoever owns the schedule. Click **Schedule** → **Add
schedule** → pick an interval → **Create schedule**. Nothing about this
step needs to involve hairil.

## B troubleshooting

- **"unauthorized_client" or "access_denied" when testing
  impersonation**: domain-wide delegation wasn't actually authorized in
  B2, or the scopes there don't match what's being requested, or the
  Client ID doesn't match this exact service account. Re-check B2 - this
  is the single most common failure point.
- **Impersonation test succeeds but the real flow still fails**: check
  that *both* the Email node's and Sheets node's Impersonate fields are
  set - they're independent per node, not a flow-wide setting.
- **Wrong tracker sheet, or one appears in the wrong Drive**: whichever
  address is in the Sheets node's Impersonate field at the moment you run
  the "Create" action is whose Drive it lands in - double check it says
  `hairil@cytron.io`, not your own address, before running Create.

