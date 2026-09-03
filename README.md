# EventWatch Complaint Dashboard

Streamlit dashboard for EventWatch customer complaints and inquiries.

## Production data behavior

The dashboard must not show an upload workbook option. Users should not upload the workbook from the dashboard UI.

The dashboard supports both production source formats from GitHub:

1. Preferred live CSV:

   `https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/customer_tracker.csv`

2. Approved Excel workbook, read directly from GitHub using the `Data` sheet:

   `https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/EventWatch_Customer_Complaints_2026.xlsx`

If `customer_tracker.csv` is unavailable, invalid, or accidentally points to workbook bytes, the app falls back to reading the approved GitHub-hosted Excel workbook directly. This is not a user upload fallback; it is a production source fallback between approved GitHub files.

## Target production design

The dashboard is designed as a full dark grey executive tool:

- Dark grey page background
- Dark grey content cards
- Dark grey navigation
- High-contrast white/light grey text
- Muted blue, teal, amber, green, and red accents only for meaning
- Equal-length navigation boxes
- Compact header cards
- Compact KPI cards
- No dashboard upload workbook option
- No mixed white/black table surfaces

## Current app behavior

The app supports:

- No dashboard upload workbook option
- Live data from the GitHub CSV, with approved GitHub Excel workbook support when CSV is unavailable or invalid
- Spaced equal-length sidebar navigation without radio-button visual clutter
- Complete dark grey dashboard theme across background, cards, tables, charts, and controls
- Compact headers, compact KPI cards, and reduced whitespace
- Start Date and End Date filters on all analytical pages
- Sidebar filters for Customer, Event type, Issue Type, Severity, Root Cause, Reason, Fix Status, RCA Requested, and Automation Focus where fields are available
- Executive Summary cockpit with small KPI cards for total records, complaint percentage, missed events, people misses, process/product split, high severity, RCA requested, fixed, RCA shared, and clarified records
- Event Summary Intelligence section covering customer pain, complaint nature, missed-event patterns, root causes, severity, and automation opportunities
- Excel-inspired source tables with enhanced faded in-cell data bars
- Defensive chart rendering so missing columns show a readable message instead of causing a Streamlit crash
- Readable dark Plotly charts with high-contrast labels, hover details, and zoom/pan toolbar controls
- Download buttons for tables and chart HTML where feasible
- Dynamic Source Discovery tables and charts by event type, customer, reason, and cross-tab views
- Automation Urgency scoring with recommended control/automation actions
- Complete structured Definitions page grouped by tracker fields, issue types, root cause, severity/status, automation focus, evidence, and deduplication
- Complaint Tracker visible/full CSV downloads
- Controlled manual complaint/inquiry entry with required fields, validation, a Save staged entry button, confirmation, and downloadable staged CSV row

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

1. Push these files to the GitHub repository.
2. Keep `customer_tracker.csv` valid when using CSV mode.
3. Keep `EventWatch_Customer_Complaints_2026.xlsx` available when using workbook mode.
4. Add the `GITHUB_CSV_URL` and `GITHUB_WORKBOOK_URL` secrets in Streamlit Cloud.
5. Deploy or reboot the app once.
6. Approved GitHub source updates should appear on dashboard refresh without redeploying code.

Important: use Streamlit Community only if your company approves hosting this tracker data there.
