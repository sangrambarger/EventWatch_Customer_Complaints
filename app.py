from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="EventWatch Executive Dashboard", layout="wide")

APP_TITLE = "EventWatch Executive Dashboard"
DEFAULT_WORKBOOK = "EventWatch_Customer_Complaints_2026.xlsx"

# Production data mode
# --------------------
# The intended production setup is:
# 1. Agent scans Outlook and prepares approval packages for new complaint/inquiry candidates.
# 2. After approval, the agent updates a live CSV file in GitHub, with user confirmation.
# 3. This Streamlit app is deployed once and refreshes from that GitHub CSV URL on page load.
# 4. The Excel workbook remains the visual/reference baseline and setup fallback, not the primary live database.
#
# Configure in Streamlit Community Cloud secrets when the CSV exists:
# GITHUB_CSV_URL = "https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/customer_tracker.csv"

PAGE_OPTIONS = [
    "Executive Summary",
    "SOURCE 01 · Monthly trend",
    "SOURCE 02 · Fix status",
    "SOURCE 03 · Severity",
    "SOURCE 04 · Root cause",
    "SOURCE 05 · Top customers",
    "SOURCE 06 · Automation focus",
    "DETAIL · Event workload",
    "Automation urgency",
    "Dynamic Source Discovery",
    "Definitions",
    "Complaint Tracker",
]

DARK_CSS = """
<style>
:root {
  --bg: #161a20;
  --panel: #222832;
  --panel-2: #2b333f;
  --panel-3: #323b48;
  --line: #465263;
  --text: #edf2f7;
  --muted: #aeb8c5;
  --blue: #7fa6d8;
  --blue-soft: rgba(127,166,216,.32);
  --gold: #d5ad69;
  --green: #85b69b;
  --red: #ce8585;
}
html, body, [data-testid="stAppViewContainer"] {
  background: var(--bg);
  color: var(--text);
}
.main .block-container {
  padding-top: 1rem;
  padding-bottom: 2rem;
  max-width: 1500px;
}
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #202936, #1a2029);
  border-right: 1px solid var(--line);
}
[data-testid="stSidebar"] * { color: var(--text); }
[data-testid="stSidebar"] label { color: var(--muted) !important; }
h1, h2, h3, h4, h5, h6, p, span, div { color: var(--text); }
.excel-card {
  background: var(--panel);
  border: 1px solid var(--line);
  border-left: 4px solid var(--blue);
  padding: 18px 20px;
  margin-bottom: 16px;
  box-shadow: 0 10px 30px rgba(0,0,0,.20);
}
.kpi {
  background: linear-gradient(180deg, var(--panel-2), var(--panel));
  border: 1px solid var(--line);
  padding: 16px;
  min-height: 118px;
  box-shadow: 0 10px 26px rgba(0,0,0,.18);
}
.kpi-label {
  font-size: 12px;
  color: var(--muted);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: .02em;
}
.kpi-num {
  font-size: 32px;
  font-weight: 900;
  color: var(--text);
  margin-top: 6px;
}
.note { font-size: 12px; color: var(--muted); }
.stTabs [data-baseweb="tab-list"] {
  gap: 6px;
  background: var(--panel);
  border: 1px solid var(--line);
  padding: 6px;
  border-radius: 0;
  position: sticky;
  top: 0;
  z-index: 20;
}
.stTabs [data-baseweb="tab"] {
  background: var(--panel-2);
  border: 1px solid transparent;
  border-radius: 0;
  color: var(--muted);
  padding: 10px 14px;
  font-weight: 800;
}
.stTabs [aria-selected="true"] {
  background: #344156 !important;
  border-color: var(--blue) !important;
  color: var(--text) !important;
}
[data-testid="stDataFrame"], [data-testid="stTable"] {
  background: var(--panel);
  border: 1px solid var(--line);
}
.excel-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--panel);
  color: var(--text);
  font-size: 13px;
  table-layout: fixed;
}
.excel-table th {
  background: #3b536d;
  color: #ffffff;
  border: 1px solid #53667a;
  padding: 9px 10px;
  text-align: center;
  font-weight: 850;
}
.excel-table td {
  border: 1px solid var(--line);
  padding: 8px 10px;
  vertical-align: middle;
  color: var(--text);
}
.excel-table td:first-child { text-align: left; }
.excel-table td:not(:first-child) { text-align: center; }
.bar-cell { padding: 0 !important; }
.bar-box {
  position: relative;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--panel);
  overflow: hidden;
}
.bar-box::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: var(--w);
  background: linear-gradient(90deg, rgba(127,166,216,.68), rgba(127,166,216,.22));
}
.bar-box span {
  position: relative;
  z-index: 1;
  color: var(--text);
  font-weight: 900;
}
.definition-box, .insight-box {
  background: var(--panel);
  border: 1px solid var(--line);
  border-left: 4px solid var(--blue);
  padding: 12px 14px;
  margin-bottom: 10px;
}
.stDownloadButton button, .stButton button {
  background: #3b536d;
  color: white;
  border: 1px solid var(--blue);
  border-radius: 0;
  font-weight: 800;
}
</style>
"""
st.markdown(DARK_CSS, unsafe_allow_html=True)


def load_from_github_csv():
    """Load live tracker rows from a GitHub raw CSV URL when configured."""
    url = st.secrets.get("GITHUB_CSV_URL", "") if hasattr(st, "secrets") else ""
    if not url:
        return None
    try:
        return pd.read_csv(url)
    except Exception as exc:
        st.sidebar.error(f"GitHub CSV live load failed: {exc}")
        return None


def load_data(uploaded_file=None):
    live_df = load_from_github_csv()
    if live_df is not None and not live_df.empty:
        st.sidebar.success("Live GitHub CSV data")
        df = live_df.copy()
    else:
        source = uploaded_file if uploaded_file is not None else Path(DEFAULT_WORKBOOK)
        if uploaded_file is None and not Path(DEFAULT_WORKBOOK).exists():
            st.warning("GitHub CSV live source is not configured yet. Upload the EventWatch workbook in the sidebar, or add the workbook to the repo as a setup fallback.")
            return pd.DataFrame()
        st.sidebar.warning("Workbook fallback mode")
        df = pd.read_excel(source, sheet_name="Data")
    if str(df.columns[0]).startswith("Unnamed"):
        df = df.drop(columns=df.columns[0])
    for col in ["Month", "Email/JIRA Date", "Reporting Month"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    if "Month" in df.columns:
        df["Month Label"] = df["Month"].dt.strftime("%b %Y")
    return df


def metric_card(label, value, foot=""):
    st.markdown(
        f"<div class='kpi'><div class='kpi-label'>{label}</div><div class='kpi-num'>{value}</div><div class='note'>{foot}</div></div>",
        unsafe_allow_html=True,
    )


def count_table(df, col, issue_type=None, pct_base=None):
    work = df.copy()
    if issue_type and "Issue Type" in work.columns:
        work = work[work["Issue Type"].eq(issue_type)]
    out = work[col].fillna("Blank").astype(str).value_counts().reset_index()
    out.columns = [col, "Records"]
    base = pct_base or max(out["Records"].sum(), 1)
    out["% of Total"] = (out["Records"] / base * 100).round(0).astype(int).astype(str) + "%"
    return out


def excel_bar_table(df, label_col, value_col="Records"):
    if df.empty:
        st.info("No data available for this view.")
        return
    max_v = max(float(df[value_col].max()), 1)
    rows = []
    for _, r in df.iterrows():
        width = float(r[value_col]) / max_v * 100
        rows.append(
            f"<tr>"
            f"<td>{r[label_col]}</td>"
            f"<td class='bar-cell'><div class='bar-box' style='--w:{width:.1f}%'><span>{r[value_col]}</span></div></td>"
            f"<td>{r.get('% of Total','')}</td>"
            f"</tr>"
        )
    st.markdown(
        "<table class='excel-table'><thead><tr><th>Category</th><th>Records</th><th>% of Total</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>",
        unsafe_allow_html=True,
    )


def dark_bar_chart(df, label_col, value_col="Records", title=""):
    fig = px.bar(df, x=value_col, y=label_col, orientation="h", text=value_col, title=title)
    fig.update_layout(
        template="plotly_dark",
        plot_bgcolor="#222832",
        paper_bgcolor="#222832",
        font=dict(color="#edf2f7"),
        margin=dict(l=10, r=18, t=38, b=10),
        height=max(340, len(df) * 34),
        yaxis={"categoryorder": "total ascending", "gridcolor": "#465263"},
        xaxis={"gridcolor": "#465263"},
        showlegend=False,
    )
    fig.update_traces(marker_color="#7fa6d8", opacity=.86, textposition="outside", cliponaxis=False)
    st.plotly_chart(fig, use_container_width=True)


def apply_filters(df):
    st.sidebar.markdown("## Filters")
    out = df.copy()
    for col in ["Month Label", "Customer", "Event type", "Issue Type", "Severity", "Root Cause", "Short Term Fix Status", "RCA Requested", "Standard Automation Focus"]:
        if col in out.columns:
            vals = sorted([x for x in out[col].dropna().astype(str).unique()])
            chosen = st.sidebar.multiselect(col.replace(" Label", ""), vals)
            if chosen:
                out = out[out[col].astype(str).isin(chosen)]
    q = st.sidebar.text_input("Search tracker")
    if q:
        out = out[out.astype(str).apply(lambda r: r.str.contains(q, case=False, na=False).any(), axis=1)]
    return out


def add_entry_form():
    with st.expander("Add new complaint / inquiry candidate"):
        with st.form("new_entry"):
            c1, c2, c3 = st.columns(3)
            customer = c1.text_input("Customer")
            event_type = c2.text_input("Event type")
            issue_type = c3.selectbox("Issue Type", ["Complaint", "Inquiry"])
            title = st.text_input("Event/Bulletin Title")
            reason = st.text_input("Reason")
            root = st.selectbox("Root Cause", ["", "People", "Process", "Product"])
            severity = st.selectbox("Severity", ["Medium", "High", "Low"])
            rca = st.selectbox("RCA Requested", ["No", "Yes"])
            focus = st.text_input("Standard Automation Focus")
            comments = st.text_area("Comments / evidence summary")
            submitted = st.form_submit_button("Prepare row for approval/export")
        if submitted:
            st.success("Candidate row prepared. Review before adding to the source tracker.")
            st.json({
                "Customer": customer,
                "Event type": event_type,
                "Issue Type": issue_type,
                "Event/Bulletin Title": title,
                "Reason": reason,
                "Root Cause": root,
                "Severity": severity,
                "RCA Requested": rca,
                "Standard Automation Focus": focus,
                "Comments": comments,
            })

uploaded = st.sidebar.file_uploader("Fallback: upload EventWatch workbook", type=["xlsx"])
df = load_data(uploaded)

st.sidebar.title(APP_TITLE)
if df.empty:
    st.stop()

filtered = apply_filters(df)
complaints = filtered[filtered["Issue Type"].eq("Complaint")] if "Issue Type" in filtered.columns else filtered
inquiries = filtered[filtered["Issue Type"].eq("Inquiry")] if "Issue Type" in filtered.columns else filtered.iloc[0:0]

tabs = st.tabs(PAGE_OPTIONS)

with tabs[0]:
    st.markdown("<div class='excel-card'><h1>Executive Summary</h1><p>Dark executive dashboard view. Production mode refreshes from a live GitHub CSV; workbook upload is the setup fallback.</p></div>", unsafe_allow_html=True)
    c = st.columns(5)
    with c[0]: metric_card("Total records", len(filtered), f"{len(complaints)} complaints · {len(inquiries)} inquiries")
    with c[1]: metric_card("RCA requested", int((filtered.get("RCA Requested") == "Yes").sum()) if "RCA Requested" in filtered else 0)
    with c[2]: metric_card("High severity", int((filtered.get("Severity") == "High").sum()) if "Severity" in filtered else 0)
    with c[3]: metric_card("Customers", filtered["Customer"].nunique() if "Customer" in filtered else 0)
    with c[4]: metric_card("Automation categories", filtered["Standard Automation Focus"].nunique() if "Standard Automation Focus" in filtered else 0)
    if not complaints.empty and "Event type" in complaints:
        st.markdown(f"<div class='insight-box'><b>Top complaint event type:</b> {complaints['Event type'].value_counts().idxmax()} ({complaints['Event type'].value_counts().max()} complaints).</div>", unsafe_allow_html=True)
    if not complaints.empty and "Standard Automation Focus" in complaints:
        st.markdown(f"<div class='insight-box'><b>Top automation focus:</b> {complaints['Standard Automation Focus'].value_counts().idxmax()} ({complaints['Standard Automation Focus'].value_counts().max()} complaints).</div>", unsafe_allow_html=True)

with tabs[1]:
    st.header("SOURCE 01 · Monthly trend")
    monthly = filtered.groupby("Month Label", dropna=False)["Issue Type"].value_counts().unstack(fill_value=0).reset_index()
    st.dataframe(monthly, use_container_width=True, hide_index=True)
    y_cols = [c for c in ["Complaint", "Inquiry"] if c in monthly.columns]
    if y_cols:
        fig = px.bar(monthly, x="Month Label", y=y_cols, barmode="group", text_auto=True)
        fig.update_layout(template="plotly_dark", plot_bgcolor="#222832", paper_bgcolor="#222832", font_color="#edf2f7", margin=dict(l=10, r=10, t=25, b=10))
        fig.update_traces(marker_line_width=0, opacity=.88)
        st.plotly_chart(fig, use_container_width=True)

views = [
    (2, "SOURCE 02 · Fix status", "Short Term Fix Status", filtered, None),
    (3, "SOURCE 03 · Severity", "Severity", filtered, None),
    (4, "SOURCE 04 · Root cause", "Root Cause", filtered, None),
    (5, "SOURCE 05 · Top customers", "Customer", filtered, None),
    (6, "SOURCE 06 · Automation focus", "Standard Automation Focus", complaints, len(complaints)),
    (7, "DETAIL · Event workload", "Event type", complaints, len(complaints)),
]
for tab_idx, title, col, data, pct_base in views:
    with tabs[tab_idx]:
        st.header(title)
        if col in data.columns:
            t = count_table(data, col, pct_base=max(pct_base or len(data), 1))
            excel_bar_table(t, col)
            dark_bar_chart(t, col)

with tabs[8]:
    st.header("Automation urgency")
    t = count_table(complaints, "Standard Automation Focus", pct_base=max(len(complaints), 1))
    t.insert(0, "Priority", range(1, len(t) + 1))
    st.dataframe(t, use_container_width=True, hide_index=True)

with tabs[9]:
    st.header("Dynamic Source Discovery")
    st.markdown("<div class='definition-box'>Dynamic Source Discovery covers misses caused by source coverage, feed ingestion, keyword detection, vendor monitoring, or article discovery gaps.</div>", unsafe_allow_html=True)
    if "Standard Automation Focus" in filtered.columns:
        st.dataframe(filtered[filtered["Standard Automation Focus"].eq("Dynamic Source Discovery")], use_container_width=True, hide_index=True)

with tabs[10]:
    st.header("Definitions")
    st.table(pd.DataFrame([
        ["Complaint", "Confirmed EventWatch service miss, delay, missing/duplicate WarRoom, visibility failure, incorrect handling, or RCA-driven service concern."],
        ["Inquiry", "Customer asks for clarification, methodology, coverage check, or supplier/site reasoning without confirmed service failure."],
        ["Dynamic Source Discovery", "Misses caused by source coverage, ingestion, keyword, vendor feed, or discovery gaps."],
    ], columns=["Term", "Definition"]))

with tabs[11]:
    st.header("Complaint Tracker")
    concise_cols = [c for c in ["Month Label", "Email/JIRA Date", "Customer", "Event type", "Event/Bulletin Title", "Issue Type", "Reason", "Root Cause", "Short Term Fix Status", "RCA Requested", "Severity", "Standard Automation Focus", "Comments"] if c in filtered.columns]
    st.download_button("Download customer tracker CSV", filtered.to_csv(index=False).encode(), "customer_tracker_filtered.csv", "text/csv")
    st.dataframe(filtered[concise_cols], use_container_width=True, hide_index=True, height=560)
    add_entry_form()