# Setting up a SIRIM CoC Progress Tracker

A complete, from-scratch walkthrough for building an agent that reads
certification-related emails from someone's inbox, extracts what changed
for each application, and keeps a Google Sheet current automatically —
using Agent Hub's **SIRIM CoC Progress Tracker** template.

## Two ways to read someone's inbox — pick based on what access you have

Agent Hub talks to Google through one hub-wide **service account** — no
per-person login, no browser consent screen. But reading an *existing
person's* Gmail (not your own — someone else's, like a colleague's) needs
one of two things, because Google requires it:

| | Needs | Who does the ongoing setup |
|---|---|---|
| **A: Domain-wide delegation** | A Google Workspace **super admin** to authorize it, once | You, entirely alone, forever after |
| **B: A personal script bridge** | Nothing beyond the inbox owner's own Google account | The inbox owner does a one-time setup; nothing further after that |

**If you don't have Workspace super admin access** (and can't easily get
five minutes from someone who does), **use Path B** — it needs zero admin
involvement, ever. This guide covers Path B as the main walkthrough,
since it's the one that works regardless of what access you have. Path A
is documented afterward for anyone who does have admin access and would
rather not involve a second script.

---

# Path B — a personal script bridge (no admin access needed at all)

**How this works, in one sentence**: the inbox owner runs a small script
under their own Google account (completely normal, no admin approval
needed for this — it's a standard feature every Google user has) that
finds matching emails and writes them to a spreadsheet; they share that
spreadsheet with the service account the same way they'd share it with a
colleague; Agent Hub reads from there instead of Gmail directly.

This exact mechanism isn't SIRIM-specific — it's documented generally in
[`GETTING_STARTED.md`, "Connecting your own Gmail, without a Workspace
admin"](GETTING_STARTED.md#connecting-your-own-gmail-without-a-workspace-admin),
since anyone on the hub might want their own inbox reachable this way for
any reason, not just this tracker. **Do that walkthrough first** (service
account setup, the spreadsheet, the script, the trigger) — the steps
below only cover what's specific to wiring it into this particular
tracker.

## Part 1 — Follow the general walkthrough, with two SIRIM-specific tweaks

1. Do steps 1–8 of GETTING_STARTED.md's walkthrough above, with these two
   changes as you go:
   - When sharing the spreadsheet with the service account (step 4
     there), set its role to **Editor**, not Viewer — this tracker also
     needs to *write* the processed results back, not just read the raw
     emails.
   - After renaming the "Sheet1" tab to `RawEmails` (step 2 there), add a
     **second tab** called `Tracker` — leave it empty; the flow fills it
     in.
2. In the script, set `SEARCH_QUERY` to:
   ```javascript
   const SEARCH_QUERY = 'SIRIM OR "CoC" OR "certificate of conformance" OR "certificate of conformity"';
   ```
   and rename the function from `checkMyInbox` to `checkForCoCEmails`
   (matters only if you're following along literally — any name works,
   just use the same one when setting up the trigger).

That's the entire bridge setup. From here, the inbox owner never has to
touch this again.

## Part 2 — Build the flow (you do this)

1. Open **Flows** → **"SIRIM CoC Progress Tracker"** template.
2. Click the **Email** node → delete it.
3. Drag a **Sheets** node into its place, wire it between Input and the
   LLM node the same way the Email node was connected. Configure it:
   - Action: **Read**
   - Spreadsheet ID: the ID copied when the inbox owner created the
     spreadsheet (GETTING_STARTED.md's walkthrough, step 3)
   - Sheet name: `RawEmails`
   - Impersonate: **leave blank** — the service account reads this via
     the sharing set up in that same walkthrough, no impersonation
     needed
4. Click the final **Sheets** node (the upsert step) → same spreadsheet
   ID, Sheet name: `Tracker`, Impersonate also blank. **Save.**

## Part 3 — Tune the search query

The default in the script (Part 4) is:

```
SIRIM OR "CoC" OR "certificate of conformance" OR "certificate of conformity"
```

Once real emails start flowing in, check the `RawEmails` tab and see
what's actually showing up — tighten the query in the script if it's
too broad or missing things, using normal Gmail search syntax, e.g.:

```
from:sirim-qas.com.my OR from:compliance-partners.com
```

Edit the `SEARCH_QUERY` line in the Apps Script and save — it takes
effect on the next scheduled run.

## Part 4 — Schedule the Agent Hub flow

1. With the flow open, click **Schedule** → **Add schedule**.
2. **Runs**: "Every N minutes" for every few hours, or "Once a day" —
   matching or slightly slower than the script's own trigger interval
   from Part 4 is reasonable, so Agent Hub reliably has new rows to read
   each time it checks.
3. **Input**: doesn't matter for this flow — type anything.
4. **Create schedule**.

## Part 5 — Test end to end before trusting it

1. Manually run the Apps Script once (Part 4) to populate some rows.
2. In Agent Hub, click **Run this flow** — check the trace: does the
   Sheets(read) node show the rows? Does the LLM output lines like
   `SIRIM-xxxx | status | note`? Does the final Sheets node say "appended"
   or "updated"?
3. Open the `Tracker` tab and confirm the row looks right.
4. Run again with nothing new in `RawEmails` — should say
   `(nothing to update)`, not create a duplicate row.

---

# Path A — domain-wide delegation (if you do have a Workspace super admin)

Simpler if you have the access: one Google login for the inbox owner is
replaced by an admin's one-time authorization instead of a second
script. Parts 1 and 2 below are identical to Path B above — Google Cloud
Console setup and pasting the key into Agent Hub Settings don't change.

## Part 1 — Google Cloud Console

Same as Path B, Part 1 — except also enable **Gmail API** in step 2
(needed here, since this path reads Gmail directly), and note the
service account's **Unique ID** (sometimes labeled "OAuth2 Client ID,"
on its detail page) instead of its email — needed for Part 2 below.

## Part 2 — Workspace Admin Console (needs a super admin)

A **different website** from Cloud Console —
[admin.google.com](https://admin.google.com) — needing someone with
Workspace super admin rights specifically.

1. **Security → Access and data control → API controls → Domain-wide
   delegation → Add new.**
2. **Client ID**: the Unique ID from Part 1.
3. **OAuth scopes**, comma-separated:
   ```
   https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/spreadsheets
   ```
4. **Authorize.**

## Part 3 — Agent Hub Settings

Same as Path B's Part 2: Settings → **Google (Gmail / Drive / Calendar /
Sheets)** → paste the JSON key → Save. Then use the **Test** button:
enter the inbox owner's address, scope "Gmail," click Test — confirm it
succeeds before moving on.

## Part 4 — Build the flow

1. Open **Flows** → **"SIRIM CoC Progress Tracker"** template as-is (the
   Email node stays — no need to swap it for a Sheets node on this path).
2. Click the **Email** node → set **Impersonate** to the inbox owner's
   address.
3. Click the final **Sheets** node → set **Impersonate** to the same
   address (each node's field is independent).

## Part 5 — One-time: create the tracker spreadsheet

The sheet lands in the **inbox owner's** Drive, since the node is
impersonating them.

1. Click the Sheets node, switch Action to "Create a new spreadsheet"
   (keep Impersonate set).
2. Title: "SIRIM CoC Tracker". Headers: `Application ID, Status, Notes`.
3. Run the flow once, copy the returned spreadsheet ID from the trace.
4. Switch back to "Update a row," paste the ID into **Spreadsheet ID**,
   keep Impersonate set. **Save.**

## Part 6 — Tune the search query, set up the Schedule

Same idea as Path B, but the query lives on the **Email node** directly
(Action: Search, the Query field) rather than in a script — default is
the same `SIRIM OR "CoC" OR ...` string, tighten it the same way once you
see what's actually arriving. Schedule setup is identical to Path B's
Part 7 — nothing here needs the inbox owner involved.

## Part 7 — Test end to end

Same as Path B's Part 8: run manually, check the trace and the actual
spreadsheet, then run again with nothing new and confirm a graceful
`(nothing to update)`.

---

## If something doesn't work

**Path B specifically:**
- **The script's authorization prompt looks scary and the inbox owner
  isn't sure it's safe**: it's completely standard for any personal Apps
  Script — they're approving their own code to touch their own account,
  the same as installing any app that needs Gmail access. Nothing here
  reaches outside their own Google account.
- **`RawEmails` tab stays empty after running the script**: check the
  tab name is spelled exactly `RawEmails` (case-sensitive), and that the
  search query actually matches real subject lines — loosen it and
  re-run.
- **Agent Hub's Sheets node fails with "Access denied" or "not found"**:
  the spreadsheet ID is wrong, or it wasn't actually shared with the
  service account's exact email address — reshare it and confirm the
  role is Editor (this tracker writes results back, so Viewer alone
  isn't enough, unlike the general walkthrough's default).

**Path A specifically:**
- **"unauthorized_client" or "access_denied" when testing on Settings**:
  domain-wide delegation wasn't actually authorized (Part 2), the scopes
  don't match, or the Client ID doesn't match this exact service
  account — the single most common failure point on this path.
- **The Settings test succeeds but the real flow still fails**: check
  *both* the Email node's and Sheets node's Impersonate fields are set —
  they're independent per node, not a flow-wide setting.

**Either path:**
- **Rows keep duplicating instead of updating**: the LLM's output isn't
  reusing a *consistent* key (the value before the first `|`) for the
  same application across different emails — check the trace's LLM
  output for whether it's inventing a new identifier each time instead
  of reusing the exact SIRIM reference number. Tightening the system
  prompt to insist on reusing exact reference numbers usually fixes this.
- **The schedule doesn't seem to be running**: open the Schedule modal,
  confirm it's toggled on, and check its run history for errors.
