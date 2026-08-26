# Setting up the SIRIM CoC Progress Tracker — reading hairil@cytron.io's inbox

## Read this part first — it changes who does what

Gmail access in Agent Hub is a personal connection, not something an admin
can set up on someone else's behalf. When a flow's Email node runs, it
acts as whoever is actually running the flow at that moment — there is no
"connect Gmail for hairil" button you can click yourself, because Google's
OAuth consent screen requires **hairil to personally log in and click
Allow**. Nobody else can do that step for him, including a hub admin —
that's a deliberate, good security property, not a missing feature.

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

If hairil would rather not personally touch the hub at all, the only way
around this is for him to forward or share access to those emails with an
account you *do* control — genuinely his call to make, not a setting to
work around.

Since `cytron.io` is confirmed to be on Google Workspace, everything below
works normally — and there's one extra option worth reading about before
you start (see the callout after Part 1.2): Workspace supports a
completely different mechanism than what's below, and it may or may not
be what you actually want here.

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

### A genuinely different option, since you're on Workspace: domain-wide delegation

Everything above (and everything Agent Hub currently supports) uses
**per-person OAuth** — hairil personally consents, once, for his own
inbox. Google Workspace also supports a completely different mechanism
called **domain-wide delegation**: a Workspace super admin authorizes a
*service account* in the Admin console to act on behalf of *any* user in
the domain, for specific scopes, with no per-user consent screen at all.

If that sounds like what you actually want (e.g. hairil would rather not
personally touch the hub, or you want this to work for whoever holds a
role in the future without re-doing the OAuth dance each time someone
changes), it's technically possible — but **Agent Hub doesn't support it
today**. The current integration is built entirely around the per-user
consent flow described above; domain-wide delegation is a different
credential type (a service account JWT, not a client ID/secret + user
consent) and would be new work, not a setting to flip.

It's also a meaningfully bigger trust decision than what's on this page
so far: a service account with domain-wide delegation for the Gmail scope
can read *any* mailbox in your Workspace, not just hairil's — worth
being deliberate about who'd control that, not something to set up
casually. If this is genuinely what you want instead of the per-person
path above, say so and I'll look at what it'd take to add.

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
   Google requirement. Two fixes, either is fine:
   - Get a free [DuckDNS](https://www.duckdns.org) name pointed at the
     hub's LAN IP, and do the rest of this setup through that address
     instead of the `.local` name or IP.
   - Do this one step (and the Connect steps in Part 4) from a browser on
     the same machine the hub runs on, using `http://localhost:8811`
     instead — Google's real exception, no domain needed. An SSH local
     port-forward (`ssh -L 8811:localhost:8811 you@pi`) lets you do this
     from your own laptop.

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
