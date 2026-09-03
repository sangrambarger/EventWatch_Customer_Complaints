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
- Complaint Tracker visible/full CSV downloads
- Controlled manual complaint/inquiry entry with required fields, validation, Save staged entry, confirmation, and downloadable staged CSV row

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
