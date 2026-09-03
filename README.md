# EventWatch Complaint Dashboard

Streamlit dashboard for EventWatch customer complaints and inquiries.

## Target production design

Deploy the Streamlit app once. After that, dashboard data should refresh from a live GitHub CSV whenever the app loads or the user refreshes the page.

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

Current workbook reference:

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