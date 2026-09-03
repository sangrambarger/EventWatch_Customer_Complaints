from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="EventWatch Executive Dashboard", layout="wide")

APP_TITLE = "EventWatch Executive Dashboard"
DEFAULT_WORKBOOK = "EventWatch_Customer_Complaints_2026.xlsx"

# Production data mode
# --------------------
# Intended production setup:
# 1. Agent scans Outlook and prepares approval packages for new complaint/inquiry candidates.
# 2. After approval, the agent updates a live CSV file in GitHub, with user confirmation.
# 3. This Streamlit app is deployed once and refreshes from that GitHub CSV URL on page load.
# 4. The Excel workbook remains the visual/reference baseline and setup fallback, not the primary live database.
#
# Configure in Streamlit Community Cloud secrets:
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

PAGE_DESCRIPTIONS = {
    "Executive Summary": "A leadership-level view of total complaint and inquiry volume, RCA exposure, severity, customer concentration, and the highest-priority automation opportunities.",
    "SOURCE 01 · Monthly trend": "Shows complaint and inquiry movement by reporting month so leaders can see whether EventWatch quality signals are improving, worsening, or shifting over time.",
    "SOURCE 02 · Fix status": "Summarizes the current resolution posture across tracked records, including items fixed, clarified, or RCA-shared.",
    "SOURCE 03 · Severity": "Breaks records by severity to highlight the operational weight of the complaint and inquiry backlog.",
    "SOURCE 04 · Root cause": "Groups records by People, Process, and Product root-cause themes to show where corrective action should focus.",
    "SOURCE 05 · Top customers": "Identifies customers most frequently represented in the tracker so account and leadership teams can prioritize follow-up.",
    "SOURCE 06 · Automation focus": "Connects complaint evidence to standard automation-control categories and highlights the largest improvement opportunities.",
    "DETAIL · Event workload": "Shows the event-type workload behind complaints, helping teams identify event categories that create repeated service risk.",
    "Automation urgency": "Ranks automation focus areas by complaint volume so the team can decide which controls to improve first.",
    "Dynamic Source Discovery": "Displays records tied to source coverage, feed ingestion, keyword detection, vendor monitoring, and event discovery gaps.",
    "Definitions": "Documents the operating definitions used to classify complaints, inquiries, and automation focus areas consistently.",
    "Complaint Tracker": "Provides the detailed tracker view used for review, filtering, export, and validation against the live source data.",
}

DARK_CSS = """
<style>
:root {
  --bg: #eef2f6;
  --surface: #ffffff;
  --surface-2: #f7f9fc;
  --sidebar: #162235;
  --sidebar-2: #20324d;
  --line: #d5dde8;
  --line-strong: #9fb0c5;
  --text: #1f2a37;
  --muted: #64748b;
  --blue: #2f6fae;
  --blue-2: #d9e8f7;
  --teal: #157f7f;
  --teal-2: #d9f0ee;
  --amber: #b7791f;
  --amber-2: #f7ead2;
  --rose: #b64747;
  --rose-2: #f5dddd;
  --green: #2f7d52;
  --green-2: #ddf0e5;
}
html, body, [data-testid="stAppViewContainer"] {
  background: var(--bg);
  color: var(--text);
}
.main .block-container {
  padding-top: 1.2rem;
  padding-bottom: 2.5rem;
  max-width: 1500px;
}
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, var(--sidebar), var(--sidebar-2));
  border-right: 1px solid #33455f;
}
[data-testid="stSidebar"] * { color: #eaf1f8; }
[data-testid="stSidebar"] label { color: #c7d2df !important; }
[data-testid="stSidebar"] .stRadio label { font-weight: 750; }
h1, h2, h3, h4, h5, h6, p, span, div { color: var(--text); }
.page-hero {
  background: linear-gradient(135deg, #ffffff 0%, #f3f7fb 55%, #e4edf7 100%);
  border: 1px solid var(--line);
  border-left: 6px solid var(--blue);
  padding: 18px 22px;
  margin-bottom: 16px;
  box-shadow: 0 8px 20px rgba(31, 42, 55, .08);
}
.page-hero h1 {
  margin: 0 0 8px 0;
  color: #172033;
  font-size: 30px;
}
.page-hero p {
  margin: 0;
  color: #405169;
  font-size: 15px;
  line-height: 1.45;
}
.filter-panel {
  background: var(--surface);
  border: 1px solid var(--line);
  padding: 14px 16px 8px 16px;
  margin-bottom: 16px;
  box-shadow: 0 6px 16px rgba(31, 42, 55, .05);
}
.kpi-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(150px, 1fr));
  gap: 14px;
  margin: 12px 0 18px 0;
}
.kpi {
  min-height: 128px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  background: var(--surface);
  border: 1px solid var(--line);
  border-top: 5px solid var(--accent);
  padding: 16px 16px 14px 16px;
  box-shadow: 0 8px 18px rgba(31, 42, 55, .08);
}
.kpi-label {
  font-size: 12px;
  color: var(--muted);
  font-weight: 850;
  text-transform: uppercase;
  letter-spacing: .04em;
}
.kpi-num {
  font-size: 34px;
  font-weight: 900;
  color: var(--text);
  line-height: 1.1;
  margin: 8px 0;
}
.kpi-foot { font-size: 12px; color: var(--muted); line-height: 1.25; }
.insight-row {
  display: grid;
  grid-template-columns: repeat(2, minmax(220px, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}
.insight-box, .section-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 5px solid var(--accent, var(--blue));
  padding: 15px 16px;
  box-shadow: 0 8px 18px rgba(31, 42, 55, .06);
}
.insight-box b { color: #172033; }
.section-card { margin-bottom: 16px; }
.section-card h3 { margin-top: 0; color: #172033; }
.excel-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--surface);
  color: var(--text);
  font-size: 13px;
  table-layout: fixed;
}
.excel-table th {
  background: #315c86;
  color: #ffffff;
  border: 1px solid #7694b4;
  padding: 9px 10px;
  text-align: center;
  font-weight: 850;
}
.excel-table td {
  border: 1px solid var(--line);
  padding: 8px 10px;
  vertical-align: middle;
  color: var(--text);
  background: #ffffff;
}
.excel-table tr:nth-child(even) td { background: #f7f9fc; }
.excel-table td:first-child { text-align: left; word-wrap: break-word; }
.excel-table td:not(:first-child) { text-align: center; }
.bar-cell { padding: 0 !important; }
.bar-box {
  position: relative;
  min-height: 34px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  overflow: hidden;
}
.bar-box::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: var(--w);
  background: linear-gradient(90deg, rgba(47,111,174,.45), rgba(47,111,174,.10));
}
.bar-box span {
  position: relative;
  z-index: 1;
  color: var(--text);
  font-weight: 900;
}
.definition-box {
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 5px solid var(--teal);
  padding: 12px 14px;
  margin-bottom: 10px;
}
.stDownloadButton button, .stButton button {
  background: #315c86;
  color: white;
  border: 1px solid #315c86;
  border-radius: 2px;
  font-weight: 800;
}
[data-testid="stDataFrame"], [data-testid="stTable"] {
  background: var(--surface);
  border: 1px solid var(--line);
}
@media (max-width: 1200px) {
  .kpi-grid { grid-template-columns: repeat(2, minmax(180px, 1fr)); }
  .insight-row { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .kpi-grid { grid-template-columns: 1fr; }
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
            st.warning(
                "GitHub CSV live source is not configured yet. Upload the EventWatch workbook on this page, "
                "or add the workbook/CSV to the repo as the setup fallback."
            )
            return pd.DataFrame()
        st.sidebar.warning("Workbook fallback mode")
        df = pd.read_excel(source, sheet_name="Data")

    if not df.empty and str(df.columns[0]).startswith("Unnamed"):
        df = df.drop(columns=df.columns[0])

    for col in ["Month", "Email/JIRA Date", "Reporting Month"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")

    if "Month" in df.columns:
        df["Month Label"] = df["Month"].dt.strftime("%b %Y")

    return df


def page_header(title):
    st.markdown(
        f"<div class='page-hero'><h1>{title}</h1><p>{PAGE_DESCRIPTIONS.get(title, '')}</p></div>",
        unsafe_allow_html=True,
    )


def page_date_filter(df, key_prefix):
    if df.empty:
        return df

    date_col = "Reporting Month" if "Reporting Month" in df.columns else "Month" if "Month" in df.columns else "Email/JIRA Date" if "Email/JIRA Date" in df.columns else None
    if not date_col:
        return df

    valid_dates = df[date_col].dropna()
    if valid_dates.empty:
        return df

    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()

    st.markdown("<div class='filter-panel'>", unsafe_allow_html=True)
    left, right, note = st.columns([1, 1, 2])
    start_date = left.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date, key=f"{key_prefix}_start")
    end_date = right.date_input("End date", value=max_date, min_value=min_date, max_value=max_date, key=f"{key_prefix}_end")
    note.caption(f"Date filter uses **{date_col}** and applies only to this page.")
    st.markdown("</div>", unsafe_allow_html=True)

    if start_date > end_date:
        st.warning("Start date is after end date. Showing the full available range.")
        return df

    mask = (df[date_col].dt.date >= start_date) & (df[date_col].dt.date <= end_date)
    return df[mask].copy()


def metric_card(label, value, foot="", accent="#2f6fae"):
    st.markdown(
        f"""
        <div class='kpi' style='--accent:{accent}'>
          <div class='kpi-label'>{label}</div>
          <div class='kpi-num'>{value}</div>
          <div class='kpi-foot'>{foot}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def kpi_grid(metrics):
    st.markdown("<div class='kpi-grid'>", unsafe_allow_html=True)
    for label, value, foot, accent in metrics:
        metric_card(label, value, foot, accent)
    st.markdown("</div>", unsafe_allow_html=True)


def count_table(df, col, issue_type=None, pct_base=None):
    if df.empty or col not in df.columns:
        return pd.DataFrame(columns=[col, "Records", "% of Total"])
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
    if df.empty:
        return
    fig = px.bar(
        df,
        x=value_col,
        y=label_col,
        orientation="h",
        text=value_col,
        title=title,
        color_discrete_sequence=["#2f6fae"],
    )
    fig.update_layout(
        template="plotly_white",
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        font=dict(color="#1f2a37"),
        margin=dict(l=10, r=20, t=42, b=10),
        height=max(340, len(df) * 34),
        yaxis={"categoryorder": "total ascending", "gridcolor": "#e5eaf1"},
        xaxis={"gridcolor": "#e5eaf1"},
        showlegend=False,
    )
    fig.update_traces(marker_color="#2f6fae", opacity=.88, textposition="outside", cliponaxis=False)
    st.plotly_chart(fig, use_container_width=True)


def apply_global_filters(df):
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Optional filters")
    out = df.copy()
    for col in ["Customer", "Event type", "Issue Type", "Severity", "Root Cause", "Short Term Fix Status", "RCA Requested", "Standard Automation Focus"]:
        if col in out.columns:
            vals = sorted([x for x in out[col].dropna().astype(str).unique()])
            chosen = st.sidebar.multiselect(col, vals, key=f"side_{col}")
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


def render_source_page(title, source_df, col, data=None, pct_base=None):
    page_header(title)
    page_df = page_date_filter(source_df, title.replace(" ", "_").replace("·", "_"))
    work = data if data is not None else page_df
    if data is None:
        work = page_df
    elif "Issue Type" in data.columns and len(data) != len(source_df):
        # Reapply the complaint-only or subset condition after the date filter.
        work = page_df[page_df["Issue Type"].eq("Complaint")] if "Issue Type" in page_df.columns else page_df

    if col not in work.columns:
        st.info(f"Column '{col}' is not available in the current source data.")
        return

    t = count_table(work, col, pct_base=max(pct_base or len(work), 1))
    st.markdown("<div class='section-card' style='--accent:#2f6fae'><h3>Source table</h3>", unsafe_allow_html=True)
    excel_bar_table(t, col)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-card' style='--accent:#157f7f'><h3>Chart view</h3>", unsafe_allow_html=True)
    dark_bar_chart(t, col, title=title)
    st.markdown("</div>", unsafe_allow_html=True)


st.sidebar.title(APP_TITLE)
st.sidebar.caption("Left navigation")
selected_page = st.sidebar.radio("Dashboard pages", PAGE_OPTIONS, label_visibility="collapsed")

uploaded = st.file_uploader("Optional setup fallback: upload EventWatch workbook", type=["xlsx"])
df = load_data(uploaded)

if df.empty:
    st.stop()

filtered_all = apply_global_filters(df)
page_df = page_date_filter(filtered_all, f"page_{PAGE_OPTIONS.index(selected_page)}") if False else filtered_all

if selected_page == "Executive Summary":
    page_header(selected_page)
    page_df = page_date_filter(filtered_all, "executive")
    complaints = page_df[page_df["Issue Type"].eq("Complaint")] if "Issue Type" in page_df.columns else page_df
    inquiries = page_df[page_df["Issue Type"].eq("Inquiry")] if "Issue Type" in page_df.columns else page_df.iloc[0:0]
    rca_count = int((page_df.get("RCA Requested") == "Yes").sum()) if "RCA Requested" in page_df else 0
    high_count = int((page_df.get("Severity") == "High").sum()) if "Severity" in page_df else 0
    customers = page_df["Customer"].nunique() if "Customer" in page_df else 0
    automation_focus = page_df["Standard Automation Focus"].nunique() if "Standard Automation Focus" in page_df else 0

    kpi_grid([
        ("Total records", len(page_df), f"{len(complaints)} complaints · {len(inquiries)} inquiries", "#2f6fae"),
        ("RCA requested", rca_count, "Records with explicit RCA request", "#b7791f"),
        ("High severity", high_count, "Highest operational attention", "#b64747"),
        ("Customers", customers, "Distinct customer accounts", "#157f7f"),
        ("Automation areas", automation_focus, "Standard focus categories", "#2f7d52"),
    ])

    insight_left = "No complaint event type is available in the selected range."
    if not complaints.empty and "Event type" in complaints:
        top = complaints["Event type"].value_counts()
        if not top.empty:
            insight_left = f"<b>Top complaint event type:</b> {top.idxmax()} ({top.max()} complaints)."

    insight_right = "No automation focus is available in the selected range."
    if not complaints.empty and "Standard Automation Focus" in complaints:
        top = complaints["Standard Automation Focus"].value_counts()
        if not top.empty:
            insight_right = f"<b>Top automation focus:</b> {top.idxmax()} ({top.max()} complaints)."

    st.markdown(
        f"""
        <div class='insight-row'>
          <div class='insight-box' style='--accent:#2f6fae'>{insight_left}</div>
          <div class='insight-box' style='--accent:#157f7f'>{insight_right}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "Issue Type" in page_df.columns:
        st.markdown("<div class='section-card' style='--accent:#2f6fae'><h3>Complaint vs inquiry mix</h3>", unsafe_allow_html=True)
        mix = count_table(page_df, "Issue Type")
        excel_bar_table(mix, "Issue Type")
        st.markdown("</div>", unsafe_allow_html=True)

elif selected_page == "SOURCE 01 · Monthly trend":
    page_header(selected_page)
    page_df = page_date_filter(filtered_all, "monthly")
    if "Month Label" in page_df.columns and "Issue Type" in page_df.columns:
        monthly = page_df.groupby("Month Label", dropna=False)["Issue Type"].value_counts().unstack(fill_value=0).reset_index()
        st.markdown("<div class='section-card' style='--accent:#2f6fae'><h3>Source table</h3>", unsafe_allow_html=True)
        st.dataframe(monthly, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
        y_cols = [c for c in ["Complaint", "Inquiry"] if c in monthly.columns]
        if y_cols:
            st.markdown("<div class='section-card' style='--accent:#157f7f'><h3>Grouped monthly chart</h3>", unsafe_allow_html=True)
            fig = px.bar(monthly, x="Month Label", y=y_cols, barmode="group", text_auto=True, color_discrete_sequence=["#2f6fae", "#157f7f"])
            fig.update_layout(template="plotly_white", plot_bgcolor="#ffffff", paper_bgcolor="#ffffff", font_color="#1f2a37", margin=dict(l=10, r=10, t=25, b=10))
            fig.update_traces(marker_line_width=0, opacity=.88)
            st.plotly_chart(fig, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("Monthly trend requires Month and Issue Type fields in the source data.")

elif selected_page == "SOURCE 02 · Fix status":
    render_source_page(selected_page, filtered_all, "Short Term Fix Status")
elif selected_page == "SOURCE 03 · Severity":
    render_source_page(selected_page, filtered_all, "Severity")
elif selected_page == "SOURCE 04 · Root cause":
    render_source_page(selected_page, filtered_all, "Root Cause")
elif selected_page == "SOURCE 05 · Top customers":
    render_source_page(selected_page, filtered_all, "Customer")
elif selected_page == "SOURCE 06 · Automation focus":
    render_source_page(selected_page, filtered_all, "Standard Automation Focus")
elif selected_page == "DETAIL · Event workload":
    render_source_page(selected_page, filtered_all, "Event type")

elif selected_page == "Automation urgency":
    page_header(selected_page)
    page_df = page_date_filter(filtered_all, "urgency")
    complaints = page_df[page_df["Issue Type"].eq("Complaint")] if "Issue Type" in page_df.columns else page_df
    if "Standard Automation Focus" in complaints.columns:
        t = count_table(complaints, "Standard Automation Focus", pct_base=max(len(complaints), 1))
        t.insert(0, "Priority", range(1, len(t) + 1))
        st.markdown("<div class='section-card' style='--accent:#b7791f'><h3>Prioritized automation table</h3>", unsafe_allow_html=True)
        st.dataframe(t, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("Automation urgency requires Standard Automation Focus in the source data.")

elif selected_page == "Dynamic Source Discovery":
    page_header(selected_page)
    page_df = page_date_filter(filtered_all, "discovery")
    st.markdown("<div class='definition-box'>Dynamic Source Discovery covers misses caused by source coverage, feed ingestion, keyword detection, vendor monitoring, or article discovery gaps.</div>", unsafe_allow_html=True)
    if "Standard Automation Focus" in page_df.columns:
        discovery = page_df[page_df["Standard Automation Focus"].eq("Dynamic Source Discovery")]
        st.dataframe(discovery, use_container_width=True, hide_index=True)
    else:
        st.info("Standard Automation Focus is not available in the current source data.")

elif selected_page == "Definitions":
    page_header(selected_page)
    st.markdown("<div class='section-card' style='--accent:#157f7f'><h3>Classification definitions</h3>", unsafe_allow_html=True)
    st.table(pd.DataFrame([
        ["Complaint", "Confirmed EventWatch service miss, delay, missing/duplicate WarRoom, visibility failure, incorrect handling, or RCA-driven service concern."],
        ["Inquiry", "Customer asks for clarification, methodology, coverage check, or supplier/site reasoning without confirmed service failure."],
        ["Dynamic Source Discovery", "Misses caused by source coverage, ingestion, keyword, vendor feed, or discovery gaps."],
    ], columns=["Term", "Definition"]))
    st.markdown("</div>", unsafe_allow_html=True)

elif selected_page == "Complaint Tracker":
    page_header(selected_page)
    page_df = page_date_filter(filtered_all, "tracker")
    concise_cols = [
        c for c in [
            "Month Label", "Email/JIRA Date", "Customer", "Event type", "Event/Bulletin Title",
            "Issue Type", "Reason", "Root Cause", "Short Term Fix Status", "RCA Requested",
            "Severity", "Standard Automation Focus", "Comments"
        ] if c in page_df.columns
    ]
    st.download_button("Download dashboard tracker CSV", page_df[concise_cols].to_csv(index=False).encode(), "customer_tracker_filtered.csv", "text/csv")
    st.download_button("Download full source CSV", page_df.to_csv(index=False).encode(), "customer_tracker_full_source.csv", "text/csv")
    st.dataframe(page_df[concise_cols], use_container_width=True, hide_index=True, height=560)
    add_entry_form()