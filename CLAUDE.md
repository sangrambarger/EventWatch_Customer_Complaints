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
```

`validate.py` covers every bug class that has actually shipped here: characters decayed
to `?` (both shapes — beside a letter, and standing alone between words where an arrow
was lost), records sitting in the wrong month, a status value the Dashboard's fixed
tables don't list (so it silently drops from a chart total), a month with records but no
row in the monthly trend block, CSV/workbook drift on **any** shared column, stripped
dynamic-array metadata, stale caches, a `ComplaintTracker` table ref left short after an
append (which silently undercounts every Dashboard COUNTIFS), Data rows appended in
a different font, the same complaint logged twice, a tracker column with no row in the
workbook's own data dictionary, and a `ComplaintTracker[...]` reference on any sheet
naming a column that no longer exists (which turns the Management Readout -- twelve
formulas, no cached values -- into #REF! on next open). Read its output instead of re-deriving the checks.

`selftest.py` is why you can trust that list. It breaks the data on purpose, one fault
per rule, and asserts the rule blocks — a validator nobody has watched fail is a
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

`smoke_app.py` covers what `validate.py` cannot: the app itself. It starts Streamlit
against the local CSV, clicks every page (16 of them), and fails on Streamlit exceptions, in-app
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

- Source tables sit under row 46. Fixed enumerations (Root Cause, Fix Status,
  Severity, Automation Focus, monthly trend) are hand-listed and go stale when a new
  value appears — this is what `validate.py`'s coverage checks watch.
- Top Customers (`A64`) and Event Type workload (`I64`) are dynamic arrays; they
  resize themselves and need no maintenance.
- Charts bind to those source tables by fixed range (`chart1` monthly trend,
  `chart2` fix status, …), so extending a table means extending the chart's `<f>`
  range and its cached points too.

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
- Jira and Outlook lookups are credential-gated and degrade to a "not configured"
  message; neither has live credentials in this repo. The Atlassian MCP connector is a
  separate path that works for a model in-session but does nothing for the deployed app.
- `Routed To` says which team a record is directed to, derived from `Root Cause`:
  People/Process go to `EventWatch Ops - Nitin Rindhe`, Product goes to
  `Product & Platform`. EventWatch Ops still owns the customer-facing RCA on
  Product-routed records — routing is who investigates, not who replies. It is a
  derived default; a human override is expected and nothing recomputes it.
- `RCA Details` holds the root cause summary from the linked ticket. Most RCAs went out
  as PDF attachments whose text is not in Jira, so those entries say so rather than
  paraphrasing a document nobody can read back. Do not invent RCA narrative.
- The app's Definitions page is a hardcoded dict in `app.py`, *not* a render of the
  workbook's Definitions sheet. Adding a tracker column means updating both, and
  `validate.py`'s `definitions` check only watches the workbook side.
