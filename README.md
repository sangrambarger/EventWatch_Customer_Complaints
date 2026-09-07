# EventWatch Complaint Dashboard

Streamlit dashboard for EventWatch customer complaints and inquiries.

## Production data behavior

The dashboard must not show an upload workbook option. Users should not upload the workbook from the dashboard UI.

No repository, owner or branch is hardcoded in `app.py`. It resolves its data source at
runtime, most explicit first:

1. **`GITHUB_CSV_URL` / `GITHUB_WORKBOOK_URL`** (Streamlit secret or environment
   variable) — an explicit path or URL. Wins outright when set.
2. **The data files sitting next to `app.py`** — Streamlit Cloud deploys the whole
   repository, so committing `customer_tracker.csv` (and the workbook) is all that is
   needed. This also makes a local checkout run with no configuration at all.
3. **A raw URL derived from `GITHUB_REPO`** (`owner/name`, plus optional
   `GITHUB_BRANCH`, default `main`) — only for the case where the data lives in a
   different repository than the app.

Preferred format is `customer_tracker.csv`. If it is unavailable, invalid, or
accidentally contains workbook bytes, the app falls back to the `Data` sheet of
`EventWatch_Customer_Complaints_2026.xlsx`. This is not a user upload fallback; it is
approved repository source support.

`customer_tracker.csv` must stay valid UTF-8. It previously contained two Windows-1252 ellipsis bytes that are invalid UTF-8, which silently broke `pd.read_csv` and forced every load onto the Excel-workbook fallback instead of the preferred CSV; this has been fixed by re-saving the file as UTF-8. Save future edits as UTF-8 (not "CSV" from Excel, which defaults to a Windows codepage) to avoid reintroducing this.

## Current app behavior

The app supports:

- Complete dark grey dashboard theme across background, navigation, cards, tables, charts, and controls
- No dashboard workbook upload option
- GitHub CSV support plus approved GitHub-hosted Excel workbook support
- Equal-length grey navigation boxes with hidden radio controls and strong text contrast
- Single clean page heading card; no extra empty bordered strip below the heading
- Compact horizontal KPI cards on Executive Summary
- Event Summary Intelligence section for customer pain, complaint nature, missed events, root causes, severity, and automation opportunities
- Chronological monthly ordering from January onward on monthly tables and charts
- Clear descriptive titles and explanatory sentences below major table/chart section titles
- Root Cause page keeps the existing summary table/chart and adds Product, People, and Process drill-downs below it
- Customer and reason analysis uses readable long-form tables with Customer and Reason as separate columns, rather than only wide cross-tabs
- Excel-inspired source tables with enhanced faded in-cell data bars
- Defensive chart rendering so missing columns show a readable message instead of causing a Streamlit crash
- Dark Plotly charts with high-contrast labels, hover details, and zoom/pan toolbar controls
- Download buttons for tables and chart HTML where feasible
- Dynamic Source Discovery tables by event type, customer, reason, and readable pairwise views
- Automation Urgency scoring with recommended control/automation actions
- Complete structured Definitions page grouped by tracker fields, issue types, root cause, severity/status, automation focus, evidence, and deduplication
- Complaint Tracker visible/full CSV downloads, now including the Jira Key column
- Controlled manual complaint/inquiry entry with required fields, validation, Save staged entry, confirmation, and downloadable staged CSV row, including a Jira Key field
- Jira Lookup page: live Jira issue lookup by key, and a list of filtered complaint rows still missing a Jira Key
- Outlook Lookup page: live Microsoft Graph mailbox search by subject/sender/customer keyword

Dashboard metrics and charts are calculated from the loaded GitHub source. They should not use stub or hard-coded metric values.

## Repository

GitHub repo:

`https://github.com/sangrambarger/EventWatch_Customer_Complaints`

Preferred CSV source:

`https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/customer_tracker.csv`

Approved workbook source:

`https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/EventWatch_Customer_Complaints_2026.xlsx`

## Streamlit secrets

Preferred:

```toml
GITHUB_CSV_URL = "https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/customer_tracker.csv"
GITHUB_WORKBOOK_URL = "https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/EventWatch_Customer_Complaints_2026.xlsx"
```

If the repo is public, no token is needed for Streamlit read access. If the repo is private, Streamlit Community needs an approved access method.

Optional, to enable the Jira Lookup page:

```toml
JIRA_BASE_URL = "https://resilinc.atlassian.net"
JIRA_EMAIL = "you@resilinc.com"
JIRA_API_TOKEN = "..."
```

Generate the API token from the Jira account that will run lookups (Atlassian account settings → Security → API tokens). Without these three secrets set, the Jira Lookup page still loads but tells you lookup isn't configured instead of failing.

Optional, to enable the Outlook Lookup page:

```toml
GRAPH_TENANT_ID = "..."
GRAPH_CLIENT_ID = "..."
GRAPH_CLIENT_SECRET = "..."
GRAPH_MAILBOX = "eventwatch@resilinc.com"
```

This requires an Azure AD app registration with **application-type** `Mail.Read` permission (admin consent) against the shared mailbox used for EventWatch complaints — an IT/security decision that has to happen before these secrets exist, not something this repo can do on its own. Once registered, put the tenant ID, client ID, client secret, and the target mailbox address into Streamlit secrets as above. Without them, the Outlook Lookup page still loads but tells you lookup isn't configured instead of failing — same pattern as Jira.

## Jira and Outlook complaint search

Previously the "Duplicate check" definition referenced a Jira key and Outlook conversation match with no supporting column or tooling — it described a manual step a person had to remember, not a real check. This is now closed on both sides:

- The tracker has a **Jira Key** column (next to `Email/JIRA Date`). Fill it in with the linked Jira issue key (e.g. `EAO-33`) for every complaint row, including through the manual-entry form.
- The **Jira Lookup** dashboard page looks up a Jira key live (summary, status, assignee, labels) so a complaint can be confirmed against Jira before it's called a duplicate, and lists filtered complaint rows that still have no Jira Key on file.
- The primary place to search is the **`EAO`** project (`EventWatch_AI_Ops`) — that's where EventWatch missed-alert/investigation/RCA-request tickets are actually filed today (e.g. `project = EAO ORDER BY created DESC`). A smaller number of older or misrouted tickets also turn up in DATA, TS, BI, TENAR, and others; for those, apply the label `eventwatch-complaint` going forward so `labels = "eventwatch-complaint"` catches them in the same query. This repo does not bulk-relabel existing tickets.
- The **Outlook Lookup** dashboard page searches a shared mailbox by subject/sender/customer keyword via Microsoft Graph (`GET /users/{mailbox}/messages?$search=...`), once the secrets above are set. There is no `Outlook Conversation ID` column in the tracker yet — a confirmed match's conversation ID or thread link goes in that row's Comments field until a dedicated column is actually requested, to avoid adding an empty column nobody uses.

## Maintenance scripts

```bash
python3 scripts/validate.py     # data + workbook integrity; exits non-zero on failure
python3 scripts/smoke_app.py    # loads all 14 dashboard pages, flags exceptions/empty charts
python3 scripts/jira_sync.py    # EAO tickets vs tracker, prints only what needs a decision
```

`validate.py` mechanizes the checks that used to be done by eye, and covers each bug
class that has actually shipped here: a character decayed to `?`, rows appended out of
date order, a status value missing from the Dashboard's fixed tables (so it drops out
of that chart's total), a month with records but no monthly-trend row, CSV/workbook
drift, and dynamic-array metadata stripped by an `openpyxl` resave. Run it before
committing any data or workbook change — it is fast and needs no credentials.

`smoke_app.py` covers what `validate.py` cannot — the app itself. It starts Streamlit
against the local CSV, visits every page, and fails on exceptions, in-app error text,
or a page drawing fewer charts/tables than expected. Against the commit before the
`chart()` argument fix it flags 8 pages with "required fields are missing" and no
charts, so it catches that class of silent breakage without screenshots.

`jira_sync.py` needs the same `JIRA_*` secrets as the Jira Lookup page. It fetches
only the fields it uses (roughly a 24x reduction over a full API payload) and reports
the delta rather than the whole ticket list, leaving only the genuinely ambiguous
matches for a person to judge.

See `CLAUDE.md` for the Python-vs-model split and, importantly, why the workbook must
never be edited via an `openpyxl` load/save round-trip.

## Files

- `app.py` - Streamlit dashboard app
- `scripts/` - validation and Jira sync utilities
- `CLAUDE.md` - working notes for automated agents and maintainers
- `requirements.txt` - Python dependencies
- `customer_tracker.csv` - preferred live data source
- `EventWatch_Customer_Complaints_2026.xlsx` - approved workbook source/reference

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy/update on Streamlit Community Cloud

These four files must be in the repository — they are all the app needs:

| File | Why |
| --- | --- |
| `app.py` | the dashboard itself |
| `requirements.txt` | `streamlit`, `pandas`, `openpyxl`, `plotly`, `requests` |
| `customer_tracker.csv` | preferred data source, read from beside `app.py` |
| `EventWatch_Customer_Complaints_2026.xlsx` | fallback data source, and the Excel dashboard |

Then, in Streamlit Community Cloud, point the app at `app.py` on the default branch.

**No secrets are required.** The app finds the data files next to itself, so a plain
deploy works with an empty secrets box. Set secrets only to change that default:
`GITHUB_CSV_URL`/`GITHUB_WORKBOOK_URL` to read from elsewhere, `GITHUB_REPO`
(+`GITHUB_BRANCH`) to read from another repository, and the `JIRA_*` / `GRAPH_*`
values to switch on the Jira and Outlook lookup pages.

`CLAUDE.md` and `scripts/` are optional for running the dashboard — they are
maintenance tooling. Committing them is recommended but not required.

Updating data means committing a new `customer_tracker.csv`; Cloud redeploys on push.
Run `python3 scripts/validate.py` before that commit.

Important: use Streamlit Community only if your company approves hosting this tracker data there.
