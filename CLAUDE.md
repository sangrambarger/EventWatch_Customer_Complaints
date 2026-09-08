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
```

`validate.py` covers every bug class that has actually shipped here: characters
decayed to `?`, rows appended out of date order, a status value the Dashboard's fixed
tables don't list (so it silently drops from a chart total), a month with records but
no row in the monthly trend block, CSV/workbook drift, and stripped dynamic-array
metadata. Verified against the commit where several of those were live — it catches
all of them. Read its output instead of re-deriving the checks.

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

`smoke_app.py` covers what `validate.py` cannot: the app itself. It starts Streamlit
against the local CSV, clicks every page, and fails on Streamlit exceptions, in-app
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

- Multi-customer rows use a slash: `Ford/GM`, `Penske/Ford`, with `Number of Customers` set.
- `Jira Key` links to the `EAO` project (EventWatch_AI_Ops); older strays live in
  DATA/TS/BI/TENAR.
- `Short Term Fix Status` is `Fixed` / `RCA Shared` / `Clarification Provided`, plus
  `Pending` for tickets still open in Jira. Adding a new value means adding it to the
  Dashboard's Fix Status table too.
- Jira and Outlook lookups are credential-gated and degrade to a "not configured"
  message; neither has live credentials in this repo.
