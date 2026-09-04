# EventWatch Complaint Dashboard

Streamlit dashboard for EventWatch customer complaints and inquiries.

## Production data behavior

The dashboard must not show an upload workbook option. Users should not upload the workbook from the dashboard UI.

The dashboard supports both production source formats from GitHub:

1. Preferred live CSV:

   `https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/customer_tracker.csv`

2. Approved Excel workbook, read directly from GitHub using the `Data` sheet:

   `https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/EventWatch_Customer_Complaints_2026.xlsx`

If `customer_tracker.csv` is unavailable, invalid, or accidentally points to workbook bytes, the app falls back to reading the approved GitHub-hosted Excel workbook directly. This is not a user upload fallback; it is approved GitHub source support.

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

## Jira complaint search

Previously the "Duplicate check" definition referenced a Jira key and Outlook conversation match with no supporting column or tooling — it described a manual step a person had to remember, not a real check. This is now partly closed:

- The tracker has a **Jira Key** column (next to `Email/JIRA Date`). Fill it in with the linked Jira issue key (e.g. `EAO-33`) for every complaint row, including through the manual-entry form.
- The **Jira Lookup** dashboard page looks up a Jira key live (summary, status, assignee, labels) so a complaint can be confirmed against Jira before it's called a duplicate, and lists filtered complaint rows that still have no Jira Key on file.
- The primary place to search is the **`EAO`** project (`EventWatch_AI_Ops`) — that's where EventWatch missed-alert/investigation/RCA-request tickets are actually filed today (e.g. `project = EAO ORDER BY created DESC`). A smaller number of older or misrouted tickets also turn up in DATA, TS, BI, TENAR, and others; for those, apply the label `eventwatch-complaint` going forward so `labels = "eventwatch-complaint"` catches them in the same query. This repo does not bulk-relabel existing tickets.
- Outlook search is still a manual step performed in the mailbox — there is no Outlook/Graph API integration in this app. An `Outlook Conversation ID` column and a Graph API lookup (mirroring the Jira one) is the natural next step if that manual step is still a bottleneck, but it requires an Azure AD app registration with mailbox read permission, which needs IT/security sign-off before it can be built.

## Files

- `app.py` - Streamlit dashboard app
- `requirements.txt` - Python dependencies
- `customer_tracker.csv` - preferred live data source
- `EventWatch_Customer_Complaints_2026.xlsx` - approved workbook source/reference

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy/update on Streamlit Community Cloud

1. Commit the updated `app.py` and `README.md` into the GitHub repository.
2. Keep `customer_tracker.csv` valid when using CSV mode.
3. Keep `EventWatch_Customer_Complaints_2026.xlsx` available when using workbook mode.
4. Add or confirm `GITHUB_CSV_URL` and `GITHUB_WORKBOOK_URL` secrets in Streamlit Cloud.
5. Reboot or redeploy the Streamlit app if Cloud does not auto-reload.
6. Approved GitHub source updates should appear on dashboard refresh without redeploying code.

Important: use Streamlit Community only if your company approves hosting this tracker data there.
