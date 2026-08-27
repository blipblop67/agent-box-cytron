# Setting up the SIRIM CoC Progress Tracker — reading hairil@cytron.io's inbox

## Read this first

Google access in Agent Hub is one hub-wide **service account**, not a
per-person login — no browser consent screen for anyone to click through,
no redirect address that has to be exactly right. One person (you) sets
this up, and every flow uses it from then on.

There's one hard requirement specific to this scenario, though: reading
**hairil's existing Gmail inbox** means the service account has to act
*as him*, and Google only allows that if a **Workspace super admin**
explicitly authorizes it — a one-time step in the Workspace Admin
Console, separate from anything you can configure in Agent Hub or in
Google Cloud Console. If you have super admin rights on `cytron.io`
yourself, or can get five minutes from whoever does, everything below is
straightforward. If genuinely nobody with that access is available, this
specific goal (reading someone else's existing mailbox) can't happen any
other way — that's a Google-side rule about impersonating a real person's
account, not a limitation of this setup guide.

**Once it's set up, hairil never has to do anything.** He doesn't log
into the hub, doesn't see a consent screen, doesn't need an account.
You do the entire setup alone, including the Schedule that keeps the
tracker running.

---

## Part 1 — Google Cloud Console (your `sirim-coc-agent` project)

1. Make sure **Gmail API** and **Google Sheets API** are enabled
   (APIs & Services → Library → search each → Enable).
2. **IAM & Admin → Service Accounts → Create Service Account.** Call it
   something clear, e.g. `sirim-coc-tracker`. No roles needed on this
   screen — skip that step.
3. Open the new service account → **Keys → Add Key → Create new key →
   JSON**. This downloads a file — it's the only copy of the private key,
   keep it safe until Part 3.
4. On the same service account page, copy its **Unique ID** (a long
   number, sometimes labeled "OAuth2 Client ID") — needed for the next
   step.

## Part 2 — Google Workspace Admin Console (needs a super admin)

This is a **different website** from Cloud Console —
[admin.google.com](https://admin.google.com) — and needs someone with
Workspace super admin rights specifically, not just any `@cytron.io`
account.

1. **Security → Access and data control → API controls → Domain-wide
   delegation → Add new.**
2. **Client ID**: paste the Unique ID from Part 1, step 4.
3. **OAuth scopes**, comma-separated — only what this tracker actually
   needs:
   ```
   https://www.googleapis.com/auth/gmail.send,https://www.googleapis.com/auth/gmail.modify,https://www.googleapis.com/auth/spreadsheets
   ```
4. **Authorize.** This is the step that actually grants it — skipping it
   is the most common reason impersonation fails later with an
   "unauthorized_client" error.

## Part 3 — Agent Hub Settings page (admin)

1. Open **Settings** → **Google (Gmail / Drive / Calendar / Sheets)**.
2. Paste the entire contents of the JSON file from Part 1, step 3 →
   **Save**. The card should now show "Configured" with the service
   account's own email address.
3. Use the **Test** button right there: enter `hairil@cytron.io`, scope
   "Gmail", click **Test**. Confirm it succeeds before moving on — if it
   fails, the error names the likely cause (scopes not authorized in
   Part 2, wrong Client ID, or `hairil@cytron.io` not actually part of
   this Workspace).

## Part 4 — Build the flow

1. Open **Flows** → **"SIRIM CoC Progress Tracker"** template.
2. Click the **Email** node → set **Impersonate** to `hairil@cytron.io`.
3. Click the **Sheets** node → set **Impersonate** to `hairil@cytron.io`
   as well (each node's Impersonate field is independent — both need it
   set).

## Part 5 — One-time: create the tracker spreadsheet

The sheet ends up in **hairil's** Drive, because the node is
impersonating him, regardless of who clicks Run.

1. Click the Sheets node, switch **Action** to "Create a new
   spreadsheet." Confirm **Impersonate** is still set to
   `hairil@cytron.io`.
2. Title: "SIRIM CoC Tracker". Headers: `Application ID, Status, Notes`.
3. Run the flow once, copy the returned spreadsheet ID from the trace.
4. Switch the Sheets node back to "Update a row," paste the ID into
   **Spreadsheet ID**, keep **Impersonate** set. **Save.**

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

Run the flow a couple of times with **Run**, look at the trace to see
what the Email node actually pulled back, and narrow the query until
it's picking up the right messages without too much noise.

## Part 7 — Set up the Schedule

Nothing about this step needs to involve hairil — the flow's Google
access comes from the Impersonate field on each node, not from whoever
owns the schedule.

1. With the flow open, click **Schedule** in the toolbar.
2. Click **"Add schedule."**
3. **Runs**: pick "Every N minutes" for something like every few hours
   (e.g. `240` for every 4 hours), or "Once a day" at a specific time —
   there's no need for anything faster than hourly for a certification
   process that moves over days/weeks.
4. **Input**: doesn't matter for this flow — the Email node's search
   query is fixed in its own config, not driven by this field. Type
   anything, e.g. "Check CoC emails."
5. Click **Create schedule**.

## Part 8 — Test it end to end before trusting the schedule

1. Click **"Run this flow"** manually once.
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

- **"unauthorized_client" or "access_denied" when testing on the
  Settings page**: domain-wide delegation wasn't actually authorized in
  Part 2, or the scopes there don't match what's being requested, or the
  Client ID doesn't match this exact service account. Re-check Part 2 —
  this is the single most common failure point.
- **The test on the Settings page succeeds but the real flow still
  fails**: check that *both* the Email node's and Sheets node's
  Impersonate fields are set to `hairil@cytron.io` — they're independent
  per node, not a flow-wide setting.
- **The tracker spreadsheet appears in the wrong Drive, or under the
  wrong account**: whichever address is in the Sheets node's Impersonate
  field at the moment you run the "Create" action is whose Drive it
  lands in — double check it says `hairil@cytron.io`, not your own
  address, before running Create.
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
