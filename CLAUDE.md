# EventWatch Customer Complaints

Streamlit dashboard over a complaint tracker that exists in two synced forms:
`customer_tracker.csv` (preferred source) and `EventWatch_Customer_Complaints_2026.xlsx`
(Data sheet + a live Dashboard).

`app.py` hardcodes no owner, repo or branch. `data_sources()` resolves, in order:
`GITHUB_CSV_URL`/`GITHUB_WORKBOOK_URL` (secret or env), then the data files sitting
next to `app.py` (the zero-config path a Streamlit Cloud deploy takes), then a raw URL
built from `GITHUB_REPO` + `GITHUB_BRANCH`. `scripts/smoke_app.py` deliberately writes
no secrets so it exercises that middle path.

## Run these before exploring by hand

```bash
python3 scripts/validate.py                 # data + workbook integrity, exits non-zero on failure
python3 scripts/smoke_app.py                # loads all 14 pages, flags exceptions/empty charts
python3 scripts/jira_sync.py                # EAO tickets vs tracker, prints only the delta
python3 scripts/jira_sync.py --describe EAO-7 EAO-9   # bodies, when prose judgement is needed
python3 scripts/refresh_caches.py --dry-run # what in the workbook has drifted from the CSV
python3 scripts/refresh_caches.py           # rewrite the drifted caches
python3 scripts/sort_tracker.py Jul Aug     # put those months back in date order, both files
python3 scripts/sort_tracker.py --all       # ...or the whole tracker
python3 scripts/selftest.py                 # prove each validate.py rule still fires
python3 scripts/audit_pages.py              # every rendered figure vs the tracker, page by page
python3 scripts/export_definitions.py       # regenerate definitions.json from the workbook sheet
python3 scripts/append_row.py --json r.json # add one record to the CSV and the Data sheet together
```

`validate.py` covers every bug class that has actually shipped here: characters decayed
to `?` (both shapes — beside a letter, and standing alone between words where an arrow
was lost), records sitting in the wrong month, a status value the Dashboard's fixed
tables don't list (so it silently drops from a chart total), a month with records but no
row in the monthly trend block, CSV/workbook drift on **any** shared column, stripped
dynamic-array metadata, stale caches, a `ComplaintTracker` table ref left short after an
append (which silently undercounts every Dashboard COUNTIFS), Data rows appended in
a different font, the same complaint logged twice, a tracker column with no row in the
workbook's own data dictionary, an enumerated *value* in use with no row in that
dictionary (six event types, four reason labels and the `Pending` fix status were all
in circulation undefined), a `DefinitionsTable` ref left short after an append, and a
`ComplaintTracker[...]` reference on any sheet
naming a column that no longer exists (which turns the Management Readout -- twelve
formulas, no cached values -- into #REF! on next open). Read its output instead of re-deriving the checks.

`selftest.py` is why you can trust that list. It breaks the data on purpose, one fault
per failure mode (19 fixtures over 18 rules), and asserts the rule blocks — a validator nobody has watched fail is a
validator nobody should trust. Two checks here were silent no-ops when first written,
and the mojibake pattern passed clean for months over four corrupted cells because its
regex needed a letter beside the `?` and the real corruption had spaces both sides.
Add a rule to `validate.py`, add a case to `selftest.py`.

`refresh_caches.py` (with `dashboard_calc.py`) re-derives every cached value in the
workbook from the CSV, by reading each Dashboard cell's own formula -- COUNTIFS, the
`LET`/`TAKE` arrays, the `ANCHORARRAY` columns -- and evaluating it. It rewrites the
six chart `<numCache>`/`<strCache>` blocks and the three dynamic-array spill regions,
including an array's `ref` and its Total-row styling when the array has grown. Nothing
about the layout is hardcoded; move a block or add a row and the values still come from
the formula that row carries. `validate.py` calls its `audit()` and fails if anything
is stale, so this is a gate, not a habit. It is idempotent -- a second run reports
nothing.

Why it matters even though `fullCalcOnLoad` is set: Excel recalculates on open, so the
caches are not what *Excel* reads. They are what everything else reads -- GitHub's xlsx
preview, a Google Sheets or LibreOffice import, `openpyxl(data_only=True)`, a file
manager's preview pane. Four of six charts and all three Top Customers columns were
showing the pre-EAO 80-row figures against a 93-row tracker before this landed.

`sort_tracker.py` is the fix for `validate.py`'s `row_order` warning. Rows get appended
in triage order, not event order, so the tracker drifts; this re-sorts a chosen set of
records by date across the CSV and the Data sheet together. Records are sorted among
the positions they already occupy, so naming two months never disturbs the rest. It
moves whole rows, so a highlight fill (`fillId=2` -- rows a human has flagged, e.g.
Data row 55) travels with its record, and it rewrites the CSV line-by-line rather than
re-serialising it, so quoting stays byte-identical and the diff shows only what moved.
It also restyles cells appended in the wrong font: sorting scatters them, turning a
tidy odd-looking block at the bottom into odd-looking rows throughout.

`append_row.py` is the only supported way to add a record. Appending by hand is the
most error-prone edit here and has gone wrong before: the workbook's column order is
not the CSV's -- `Jira Key` is the third CSV column and column W on the sheet -- so a
positional write lands one column off and only the full-width `parity` check notices.
`ComplaintTracker`'s ref must grow with the row or every Dashboard COUNTIFS silently
undercounts. `Month` is `Sep 2026` in the CSV and a first-of-month serial on the sheet,
while `Reporting Month` is an inline string in both. The script reads the sheet's own
header row for column order, derives Month / Reporting Month / Month_Sort / Number of
Customers / Routed To, refuses to write unless all ten required fields are present, and
writes both files or neither. It deliberately does not refresh caches: run
`refresh_caches.py` then `validate.py` after.

## The Jira scheduler

A Routine (scheduled Claude session) runs daily with the Atlassian connector attached.
It searches the EAO project, diffs the keys against the tracker, classifies each new
ticket, appends it with `append_row.py`, refreshes the caches, runs the full gate and
pushes. **No API credentials exist anywhere in this repo or in Streamlit** -- the
connector belongs to the scheduled session, not to the app, which is why `app.py` still
makes no network calls. Appended rows follow the house convention for pre-triage
records: `Comments` opens with `Staged from Jira EAO-NN (<status>).` so a row a human
has not yet reviewed is identifiable at a glance. If any gate fails the run opens a PR
instead of pushing, so a bad row cannot reach the dashboard silently.

`audit_pages.py` covers what `smoke_app.py` cannot: whether the numbers are *right*.
It scrapes every `excel-table` off every page and reconciles each label against counts
computed independently from the CSV. A page bound to a stale frame, a filter quietly
dropping rows, or a chart truncating a category all look identical to `smoke_app.py`;
this names the label and both numbers. It found the app showing Ford as 41, 37 and 32
on three pages at once.

Every page counts **all records — complaints and inquiries together** — and every count
table carries explicit `Complaints` and `Inquiries` columns beside the total, with the
charts stacked to match. The Excel Dashboard still counts complaints only, so its Top
Customers figures differ from the app on two axes; SOURCE 05 shows the workbook's basis
in its own table so the two reconcile.

The Complaint Tracker page's entry form writes into `st.session_state`, and
`apply_staged()` appends those rows to the frame **before** `sidebar_filters()`. Every
page derives from that one frame, so an entry added there is counted immediately on all
fourteen -- Executive Summary's total goes 103 to 104, SOURCE 05's Ford tally 37 to 38.
The form's pickers are built from the tracker's own distinct values, so a staged row can
only carry terms the Definitions sheet already defines, and `derive_row()` fills Month,
Reporting Month, Month_Sort, Number of Customers and Routed To -- a staged row pasted
into the tracker passes `validate.py` unedited. Staging is **per browser session and not
persisted**: Streamlit Cloud's filesystem is ephemeral and `app.py` makes no network
calls, so the entry lives until the tab is closed. The "Download tracker CSV including
staged entries" button is the path to making it permanent. Durable in-app writes would
need a GitHub token or a database, and neither exists here.

`smoke_app.py` covers what `validate.py` cannot: the app itself. It starts Streamlit
against the local CSV, clicks every page (14 of them), and fails on Streamlit exceptions, in-app
error text, or a page rendering fewer charts/tables than it should. Run against the
commit before the `chart()` argument fix it flags 8 pages with "required fields are
missing" and zero charts — the bug that previously only a screenshot caught. Prefer
it over screenshots; it costs a fraction of the tokens.

## Python's job vs. the model's job

Deterministic work belongs in a script; it is cheaper, repeatable, and reviewable.

| Do in Python | Needs a model |
| --- | --- |
| Fetch and condense Jira; diff keys against the tracker | Deciding which customer a prose ticket body is about — Micron, Honeywell, GM and Liberty Blume were each named only in body text, never in a field |
| Every integrity check in `validate.py` | Matching a ticket to a row when the strings differ ("Dana Holding Corporation" vs "Dana Incorporated"; "Event title change request" → the Isselguss naming clarification) |
| Structural workbook audits (table refs, chart ranges, `cm=` markers) | Judging whether two rows are one complaint from two customers or two independent misses |
| Mechanical, idempotent edits (append rows, extend a chart range) | Classifying a new row's Root Cause / Reason / Severity / Automation Focus |

On that last row: the workbook computes those fields by formula, but ~20 of the
original 80 rows disagree with a literal recomputation of their own formula. The
humans override it. Treat the formula as a draft, not the rule, and match the
thematic precedent of comparable rows instead.

## Token traps specific to this repo

- **Jira through a conversational tool costs ~2600 chars/ticket where ~110 are
  useful** — self links, four avatar URLs per user, statusCategory objects. One
  `getVisibleJiraProjects` call returned 316KB and blew the context window. Prefer
  `scripts/jira_sync.py`. If you must use the MCP tools, pass `fields`, use one paged
  JQL search rather than per-issue calls, and never list all projects.
- **`app.py` is ~480 lines** — grep for the symbol, then read with `offset`/`limit`.
  Reading it whole costs ~13K tokens and is rarely needed.
- **Screenshots cost real tokens.** Run `scripts/smoke_app.py` first — it catches
  exceptions and empty charts from the DOM for ~1K tokens, where screenshotting all
  14 pages costs ~25K. Reserve screenshots for judging *appearance* (layout, colour,
  spacing) on pages you actually changed.

## Editing the workbook: do not use openpyxl load/save

`openpyxl.load_workbook(...)` then `.save()` on this file **silently destroys** the
Dashboard's dynamic arrays: it drops `xl/metadata.xml` and the `cm=` attributes that
make the `LET`/`UNIQUE`/`FILTER`/`SORTBY`/`TAKE` formulas in `Dashboard!A64`, `B64`,
`C64` and `I64` spill, and it strips chart style sidecars. It also converts shared
strings to inline strings, so you cannot swap one sheet's XML back in isolation.

Edit the zip members directly instead — unzip, patch `xl/worksheets/sheetN.xml` or
`xl/charts/chartN.xml` as text, rezip — then run `scripts/validate.py`. Sheet order:
`sheet1` Data, `sheet2` Dashboard, `sheet3` Definitions, `sheet4` Management Readout.

If a resave already happened, restore the four `cm="1"` attributes and
`xl/metadata.xml` from git history and re-register the part in `[Content_Types].xml`.

## Dashboard structure worth knowing

- Source tables sit under row 46. **The four bands share rows**: row 53 carries April's
  month serial in column A, the Root Cause Total in E, a Fix Status value in I and a
  Severity value in M. Inserting a row to grow one block therefore rewrites cells
  belonging to the others — an attempt at automating that replaced May's month serial
  with a duplicate of April's. Grow a block by writing its own two columns, never by
  cloning a row.
- The monthly trend block is pre-extended to all twelve months of 2026 (rows 50-61,
  Total at 62), so October, November and December land in rows that already exist and
  `chart1` already covers. Nothing needs doing when the month rolls over.
- Fixed enumerations (Root Cause, Fix Status, Severity, Automation Focus) are still
  hand-listed and still go stale when a new value appears; `validate.py`'s
  `enum_coverage` reports it and the row is added by hand. A new value costs **two**
  hand-edits, not one: the Dashboard's enum block (`enum_coverage`) and a row on the
  Definitions sheet (`enum_definitions`). Definitions rows append at the bottom, out
  of section order -- rows 138-150 already do -- so nothing shifts; extend
  `DefinitionsTable`'s `ref` and the sheet `dimension` to the new last row.
- Top Customers (`A64`) and Event Type workload (`I64`) are dynamic arrays; they
  resize themselves and need no maintenance.
- Charts bind to those source tables by fixed range (`chart1` monthly trend,
  `chart2` fix status, …), so extending a table means extending the chart's `<f>`
  range and its cached points too. Charts are not row-anchored in `drawing1.xml`, so
  shifting source rows does not move them on screen.
- Shifting rows also means rewriting A1-style references **inside** formulas
  (`ANCHORARRAY(A64)`, `SUM(F64:F72)`) and the `ref=` on each `<f t="array">`, plus
  `mergeCell`, `conditionalFormatting sqref` and the frozen `pane`. Renumbering only
  the `<c r="...">` attributes leaves the sheet loading but computing nonsense.

## Conventions

- Multi-customer rows use a slash: `Ford/GM`, `Penske/Ford`, `Eaton/Ford`, with `Number of
  Customers` set. One incident reported by two customers is **one row**, not two.
  A merged incident may also carry slash-separated Jira keys (`EAO-35/EAO-36`).
- **The app and the workbook count customers differently, on purpose.** `app.py`'s
  `customer_exposure()` splits on the slash so a row naming two accounts is counted for
  each -- that is the tally on SOURCE 05 and the Executive Summary. The workbook's
  `COUNTIFS` matches the whole string, so `Eaton/Ford` is its own category there. SOURCE
  05 shows the exact-match table too, labelled, so the two can be reconciled. Making
  Excel agree means rewriting `Dashboard!A64`, `B64` and the `B74` "Other customers"
  formula to be token-aware -- not done.
- `Jira Key` links to the `EAO` project (EventWatch_AI_Ops); older strays live in
  DATA/TS/BI/TENAR.
- `Short Term Fix Status` is `Fixed` / `RCA Shared` / `Clarification Provided`, plus
  `Pending` for tickets still open in Jira. Adding a new value means adding it to the
  Dashboard's Fix Status table too.
- The app has **no live Jira or Outlook lookup**. Both pages were removed: the tracker's
  earlier months predate the EAO project, so a per-row lookup was empty for most records
  and the credential-gated "not configured" placeholder was all most viewers ever saw.
  Jira reconciliation lives in `scripts/jira_sync.py` and in the Atlassian MCP connector,
  which works for a model in-session and does nothing for the deployed app. Do not
  reintroduce `requests` or a network call into `app.py`.
- `Routed To` says which team a record is directed to, derived from `Root Cause`:
  People/Process go to `EventWatch Ops - Nitin Rindhe`, Product goes to
  `Product & Platform`. EventWatch Ops still owns the customer-facing RCA on
  Product-routed records — routing is who investigates, not who replies. It is a
  derived default; a human override is expected and nothing recomputes it.
- `RCA Details` holds the root cause summary from the linked ticket. Most RCAs went out
  as PDF attachments whose text is not in Jira, so those entries say so rather than
  paraphrasing a document nobody can read back. Do not invent RCA narrative.
- The app's Definitions page renders `definitions.json`, generated from the workbook's
  Definitions sheet by `scripts/export_definitions.py` and **pruned to terms in use**
  (a field definition survives if the tracker has that column, a taxonomy value if some
  record carries it, an operational term if it appears in the tracker's own text). Edit
  the sheet, re-run the script; never edit the JSON. `validate.py`'s
  `definitions_export` rebuilds it in memory and fails if what is committed is stale.
  It is a committed file rather than a runtime read of the workbook because the
  CSV-only deploy path has no workbook, and a JSON that ships with the app cannot fail
  to load. It replaced a hardcoded dict that had drifted badly -- no Event type or
  Sub-type section at all, and a `Confidence` term the tracker never had.
