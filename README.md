# EventWatch Complaint Dashboard

Streamlit dashboard for EventWatch customer complaints and inquiries.

## Target production design

Deploy the Streamlit app once. After that, dashboard data refreshes from the live GitHub CSV whenever the app loads or the user refreshes the page.

The agent workflow is:

1. Agent scans Outlook.
2. Agent finds potential new complaint/inquiry trails.
3. Agent prepares a full approval package with email-trail evidence.
4. User approves, edits, rejects, or holds the candidate.
5. Once GitHub write access is configured, approved rows are appended/updated in the GitHub CSV.
6. Streamlit reads the GitHub CSV and updates charts/tables without redeploying the app.

## Repository

GitHub repo:

`https://github.com/sangrambarger/EventWatch_Customer_Complaints`

Workbook reference:

`https://github.com/sangrambarger/EventWatch_Customer_Complaints/blob/main/EventWatch_Customer_Complaints_2026.xlsx`

Live CSV source:

`customer_tracker.csv`

Browser URL:

`https://github.com/sangrambarger/EventWatch_Customer_Complaints/blob/main/customer_tracker.csv`

Raw CSV URL for Streamlit:

`https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/customer_tracker.csv`

## Streamlit secrets

In Streamlit Community Cloud, add:

```toml
GITHUB_CSV_URL = "https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/customer_tracker.csv"
```

If the CSV is public, no token is needed for Streamlit read access. If the repo is private, Streamlit Community needs an approved access method.

## Current app behavior

The app supports:

- Spaced sidebar navigation without radio-button visual clutter
- Google-style flat grey executive palette
- Compact headers, compact KPI cards, and reduced whitespace
- Start Date and End Date filters on all analytical pages
- Sidebar filters for Customer, Event type, Issue Type, Severity, Root Cause, Reason, Fix Status, RCA Requested, and Automation Focus where fields are available
- Executive Summary cockpit with complaint percentage, missed events, people/process/product split, customer complaints, issue nature, and automation opportunities
- Excel-inspired source tables with enhanced faded in-cell data bars
- Readable Plotly charts with stronger label contrast, hover details, and zoom/pan toolbar controls
- Download buttons for tables and chart data/HTML where feasible
- Dynamic Source Discovery tables and charts by event type, customer, reason, and cross-tab views
- Automation Urgency scoring with recommended control/automation actions
- Complete structured Definitions page grouped by tracker fields, issue types, root cause, severity/status, automation focus, evidence, and deduplication
- Complaint Tracker visible/full CSV downloads
- Controlled manual complaint/inquiry entry with required fields, validation, a Save staged entry button, confirmation, and downloadable staged CSV row
- Live GitHub CSV read mode using `GITHUB_CSV_URL`

The production dashboard does not support workbook upload or workbook fallback mode. If the live CSV cannot be loaded, the app shows a clear blocker instead of asking the user to upload a workbook.

Dashboard metrics and charts are calculated from the loaded live CSV. They should not use stub or hard-coded metric values.

## Files

- `app.py` - Streamlit dashboard app
- `requirements.txt` - Python dependencies
- `customer_tracker.csv` - required live data source
- `EventWatch_Customer_Complaints_2026.xlsx` - approved workbook reference only

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy/update on Streamlit Community Cloud

1. Push these files to the GitHub repository.
2. Create or update `customer_tracker.csv` from the approved workbook `Data` sheet.
3. Add the `GITHUB_CSV_URL` secret in Streamlit Cloud.
4. Deploy or reboot the app once.
5. After that, approved CSV row updates should appear on dashboard refresh without redeploying code.

Important: use Streamlit Community only if your company approves hosting this tracker data there.
