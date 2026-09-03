from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="EventWatch Executive Dashboard", layout="wide")

APP_TITLE = "EventWatch Executive Dashboard"
CSV_URL = "https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/customer_tracker.csv"
WORKBOOK_URL = "https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/EventWatch_Customer_Complaints_2026.xlsx"

PAGES = [
    "Executive Summary", "SOURCE 01 · Monthly trend", "SOURCE 02 · Fix status",
    "SOURCE 03 · Severity", "SOURCE 04 · Root cause", "SOURCE 05 · Top customers",
    "SOURCE 06 · Automation focus", "DETAIL · Event workload", "Automation urgency",
    "Dynamic Source Discovery", "Definitions", "Complaint Tracker",
]

DESCRIPTIONS = {
    "Executive Summary": "Leadership cockpit for complaint volume, customer pain, missed events, RCA exposure, root causes, and automation opportunities.",
    "SOURCE 01 · Monthly trend": "Month-by-month complaint and inquiry trend, sorted chronologically from January onward.",
    "SOURCE 02 · Fix status": "Resolution posture across fixed, RCA-shared, and clarification-provided records.",
    "SOURCE 03 · Severity": "Severity distribution for leadership prioritization.",
    "SOURCE 04 · Root cause": "People, Process, and Product themes with deeper drill-downs below the current summary.",
    "SOURCE 05 · Top customers": "Customers with the highest complaint or inquiry volume and the reasons behind those records.",
    "SOURCE 06 · Automation focus": "Automation/control categories linked to tracker evidence.",
    "DETAIL · Event workload": "Event types that repeatedly drive complaints, inquiries, or operational workload.",
    "Automation urgency": "Ranked automation priorities using volume, severity, RCA pressure, misses, and customer concentration.",
    "Dynamic Source Discovery": "Source coverage, feed, keyword, vendor monitoring, and event-discovery gaps.",
    "Definitions": "Structured glossary for tracker fields, classification, statuses, root causes, and automation terms.",
    "Complaint Tracker": "Filtered tracker records with download and controlled manual-entry staging.",
}

CSS = """
<style>
:root{--bg:#0f1115;--panel:#1b1f26;--panel2:#202631;--ink:#f3f4f6;--muted:#b6beca;--line:#3a414d;--line2:#515a68;--blue:#8ab4f8;--teal:#80cbc4;--amber:#f6c177;--red:#f28b82;--green:#a8dab5}
html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--bg)!important;color:var(--ink)!important}.main .block-container{padding-top:.75rem;max-width:1450px;background:var(--bg)!important}[data-testid="stHeader"],[data-testid="stToolbar"]{background:#0c0e12!important}[data-testid="stSidebar"]{background:#171b22!important;border-right:1px solid var(--line)}[data-testid="stSidebar"] *{color:var(--ink)!important}[data-testid="stSidebar"] label{color:var(--muted)!important}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"]>label{height:42px;width:100%;box-sizing:border-box;background:var(--panel2)!important;border:1px solid var(--line)!important;border-radius:8px!important;padding:9px 12px!important;margin:7px 0!important;display:flex!important;align-items:center!important;box-shadow:none!important}[data-testid="stSidebar"] .stRadio div[role="radiogroup"]>label:hover{background:#2a313d!important}[data-testid="stSidebar"] .stRadio div[role="radiogroup"]>label:has(input:checked){background:#374151!important;border-color:var(--blue)!important}[data-testid="stSidebar"] .stRadio input{display:none!important}
h1,h2,h3,h4,h5,h6,p,span,div,label{color:var(--ink)!important}.page-hero,.section-card,.kpi,.insight-box,.definition-group{background:var(--panel)!important;border:1px solid var(--line);box-shadow:0 2px 8px rgba(0,0,0,.28)}.page-hero{border-left:5px solid var(--blue);padding:12px 16px;margin-bottom:16px}.page-hero h1{margin:0 0 4px 0;font-size:25px}.page-hero p,.section-card p{margin:0;color:var(--muted)!important;font-size:14px;line-height:1.35}.section-card{border-left:4px solid var(--accent,var(--blue));border-radius:8px;padding:12px 14px;margin:16px 0 10px}.section-card h3{margin:0 0 6px 0;font-size:21px}.kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(145px,1fr));gap:10px;margin:10px 0 14px}.kpi{min-height:88px;border-top:4px solid var(--accent);border-radius:8px;padding:10px 12px}.kpi-label{font-size:11px;color:var(--muted)!important;font-weight:800;text-transform:uppercase;letter-spacing:.035em}.kpi-num{font-size:28px;font-weight:900;line-height:1.05;margin:5px 0}.kpi-foot{font-size:12px;color:var(--muted)!important}.insight-row{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:10px}.insight-box{border-left:4px solid var(--accent);border-radius:8px;padding:11px 12px;font-size:14px}
.excel-table{width:100%;border-collapse:collapse;background:var(--panel)!important;font-size:13px;table-layout:fixed}.excel-table th{background:#303846!important;color:#fff!important;border:1px solid var(--line2);padding:8px 9px;text-align:center;font-weight:850}.excel-table td{border:1px solid var(--line);padding:7px 9px;background:#1f242d!important;color:var(--ink)!important}.excel-table tr:nth-child(even) td{background:#252b35!important}.excel-table td:first-child{text-align:left;overflow-wrap:anywhere}.excel-table td:not(:first-child){text-align:center}.bar-cell{padding:0!important}.bar-box{position:relative;min-height:32px;display:flex;align-items:center;justify-content:center;overflow:hidden}.bar-box:before{content:"";position:absolute;inset:0 auto 0 0;width:var(--w);background:linear-gradient(90deg,rgba(138,180,248,.65),rgba(138,180,248,.15))}.bar-box span{position:relative;z-index:1;font-weight:900;color:#fff!important;text-shadow:0 1px 2px #000}.definition-group{border-left:4px solid var(--teal);border-radius:8px;padding:12px 14px;margin:12px 0}.stDownloadButton button,.stButton button,.stFormSubmitButton button{background:#374151!important;color:#fff!important;border:1px solid var(--blue)!important;border-radius:7px!important;font-weight:800!important}[data-testid="stDataFrame"],[data-testid="stTable"]{background:var(--panel)!important;border:1px solid var(--line)!important}
@media(max-width:1200px){.kpi-grid{grid-template-columns:repeat(2,minmax(180px,1fr))}.insight-row{grid-template-columns:1fr}}@media(max-width:760px){.kpi-grid{grid-template-columns:1fr}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def read_csv_or_excel(url: str):
    if url.split("?")[0].lower().endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(url, sheet_name="Data"), "GitHub Excel workbook"
    return pd.read_csv(url), "GitHub CSV"


def load_data():
    csv_url = st.secrets.get("GITHUB_CSV_URL", CSV_URL) if hasattr(st, "secrets") else CSV_URL
    workbook_url = st.secrets.get("GITHUB_WORKBOOK_URL", WORKBOOK_URL) if hasattr(st, "secrets") else WORKBOOK_URL
    errors = []
    for url in [csv_url, workbook_url]:
        try:
            df, label = read_csv_or_excel(url)
            st.sidebar.success(f"Live {label} data")
            st.sidebar.caption("Workbook upload is disabled; data is read from GitHub.")
            break
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    else:
        st.error("Dashboard data could not be loaded from GitHub. Uploading a workbook in the dashboard is intentionally disabled.")
        for err in errors: st.caption(err)
        return pd.DataFrame()
    if not df.empty and str(df.columns[0]).startswith("Unnamed"):
        df = df.drop(columns=df.columns[0])
    for c in ["Month", "Email/JIRA Date", "Reporting Month"]:
        if c in df.columns: df[c] = pd.to_datetime(df[c], errors="coerce")
    source = next((c for c in ["Reporting Month", "Month", "Email/JIRA Date"] if c in df.columns), None)
    if source and "Month Label" not in df.columns:
        df["Month Label"] = df[source].dt.strftime("%b %Y")
    return df


def page_header(title):
    st.markdown(f"<div class='page-hero'><h1>{title}</h1><p>{DESCRIPTIONS.get(title,'')}</p></div>", unsafe_allow_html=True)


def add_section(title, desc="", accent="#8ab4f8"):
    st.markdown(f"<div class='section-card' style='--accent:{accent}'><h3>{title}</h3><p>{desc}</p></div>", unsafe_allow_html=True)


def date_filter(df, key):
    date_col = next((c for c in ["Reporting Month", "Month", "Email/JIRA Date"] if c in df.columns), None)
    if df.empty or not date_col or df[date_col].dropna().empty: return df
    mn, mx = df[date_col].dropna().min().date(), df[date_col].dropna().max().date()
    a, b, c = st.columns([1, 1, 2])
    start = a.date_input("Start date", mn, min_value=mn, max_value=mx, key=f"{key}_start")
    end = b.date_input("End date", mx, min_value=mn, max_value=mx, key=f"{key}_end")
    c.caption(f"Date filter uses **{date_col}** and applies to this page.")
    if start > end:
        st.warning("Start date is after end date. Showing the full available range.")
        return df
    return df[(df[date_col].dt.date >= start) & (df[date_col].dt.date <= end)].copy()


def sidebar_filters(df):
    st.sidebar.markdown("---"); st.sidebar.markdown("### Filters")
    out = df.copy()
    for col in ["Customer", "Event type", "Issue Type", "Severity", "Root Cause", "Reason", "Short Term Fix Status", "RCA Requested", "Standard Automation Focus"]:
        if col in out.columns:
            vals = sorted(out[col].dropna().astype(str).unique())
            chosen = st.sidebar.multiselect(col, vals, key=f"filter_{col}")
            if chosen: out = out[out[col].astype(str).isin(chosen)]
    q = st.sidebar.text_input("Search tracker")
    if q: out = out[out.astype(str).apply(lambda r: r.str.contains(q, case=False, na=False).any(), axis=1)]
    return out


def count_table(df, col, base=None):
    if df.empty or col not in df.columns: return pd.DataFrame(columns=[col, "Records", "% of Total"])
    t = df[col].fillna("Blank").astype(str).value_counts().reset_index()
    t.columns = [col, "Records"]
    denom = max(base or len(df), 1)
    t["% of Total"] = (t["Records"] / denom * 100).round(1).astype(str) + "%"
    return t


def long_pair_table(df, first, second, base=None):
    if df.empty or first not in df.columns or second not in df.columns: return pd.DataFrame(columns=[first, second, "Records", "% of Total"])
    out = df.groupby([first, second], dropna=False).size().reset_index(name="Records")
    out[first], out[second] = out[first].fillna("Blank").astype(str), out[second].fillna("Blank").astype(str)
    denom = max(base or int(out["Records"].sum()), 1)
    out["% of Total"] = (out["Records"] / denom * 100).round(1).astype(str) + "%"
    return out.sort_values(["Records", first, second], ascending=[False, True, True])


def kpis(items):
    cards = [f"<div class='kpi' style='--accent:{a}'><div class='kpi-label'>{l}</div><div class='kpi-num'>{v}</div><div class='kpi-foot'>{f}</div></div>" for l, v, f, a in items]
    st.markdown("<div class='kpi-grid'>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def excel_bar_table(df, label_col, value_col="Records"):
    if df.empty or label_col not in df.columns or value_col not in df.columns:
        st.info("No data available for this view."); return
    max_v = max(float(df[value_col].max()), 1)
    rows = []
    for _, r in df.iterrows():
        width = float(r[value_col]) / max_v * 100
        rows.append(f"<tr><td>{r[label_col]}</td><td class='bar-cell'><div class='bar-box' style='--w:{width:.1f}%'><span>{r[value_col]}</span></div></td><td>{r.get('% of Total','')}</td></tr>")
    st.markdown("<table class='excel-table'><thead><tr><th>Category</th><th>Records</th><th>% of Total</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>", unsafe_allow_html=True)


def chart(df, label_col, value_col="Records", title=""):
    if df.empty or label_col not in df.columns or value_col not in df.columns:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}, {value_col}."); return None
    data = df[[label_col, value_col]].dropna().head(20).copy()
    if data.empty: st.info("No chartable records available for this view."); return None
    data[label_col] = data[label_col].astype(str)
    fig = px.bar(data, x=value_col, y=label_col, orientation="h", text=value_col, title=title, color_discrete_sequence=["#8ab4f8"])
    fig.update_yaxes(categoryorder="total ascending", tickfont=dict(size=13, color="#f3f4f6"), gridcolor="#303846")
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846")
    fig.update_traces(opacity=.92, textposition="outside", cliponaxis=False, marker_line_width=0)
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26", font=dict(color="#f3f4f6", size=13), margin=dict(l=20, r=60, t=44, b=28), height=max(360, min(760, len(data) * 38 + 130)), showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
    return fig


def downloads(df, name, fig=None):
    c1, c2, c3 = st.columns([1, 1, 3])
    c1.download_button("Download table CSV", df.to_csv(index=False).encode(), f"{name}.csv", "text/csv", key=f"csv_{name}")
    if fig is not None: c2.download_button("Download chart HTML", fig.to_html().encode(), f"{name}_chart.html", "text/html", key=f"chart_{name}")
    c3.caption("Use the chart toolbar to zoom, pan, reset, or inspect values on hover.")


def source_page(title, df, col, key):
    page_header(title); page = date_filter(df, key); t = count_table(page, col); label = col.replace("Standard Automation Focus", "Automation focus")
    add_section(f"{label} summary table", f"Shows selected tracker records by {label.lower()}, with record count and share of the filtered total.")
    excel_bar_table(t, col); downloads(t, key)
    add_section(f"{label} chart", f"Visual ranking of {label.lower()} categories so leaders can quickly see the biggest drivers.", "#80cbc4")
    fig = chart(t, col, f"{label} distribution"); downloads(t, f"{key}_chart_data", fig)
    if col == "Customer":
        for first, second, name, desc in [("Customer", "Reason", "Customer complaint reasons", "Shows each customer and the specific reasons tied to that customer."), ("Customer", "Event type", "Customer event-type patterns", "Shows which event types are driving records for each customer."), ("Customer", "Root Cause", "Customer root-cause patterns", "Shows whether each customer’s records are People, Process, or Product related.")]:
            lt = long_pair_table(page, first, second)
            if not lt.empty: add_section(name, desc, "#a8dab5"); st.dataframe(lt, use_container_width=True, hide_index=True, height=420); downloads(lt, name.lower().replace(" ", "_"))
    if col == "Root Cause":
        for root in ["Product", "People", "Process"]:
            root_df = page[page["Root Cause"].astype(str).eq(root)] if "Root Cause" in page.columns else page.iloc[0:0]
            if root_df.empty: continue
            add_section(f"{root} drill-down", f"Breaks {root.lower()} root-cause records into reasons, event types, customers, and automation focus areas for action planning.", "#f6c177" if root == "Process" else "#8ab4f8" if root == "Product" else "#b6beca")
            c1, c2 = st.columns(2)
            with c1: st.markdown(f"**{root} reasons**"); st.dataframe(count_table(root_df, "Reason") if "Reason" in root_df.columns else pd.DataFrame(), use_container_width=True, hide_index=True)
            with c2: st.markdown(f"**{root} event types**"); st.dataframe(count_table(root_df, "Event type") if "Event type" in root_df.columns else pd.DataFrame(), use_container_width=True, hide_index=True)
            pair = long_pair_table(root_df, "Customer", "Reason")
            if not pair.empty: st.markdown(f"**{root} customer and reason detail**"); st.dataframe(pair, use_container_width=True, hide_index=True, height=320); downloads(pair, f"{root.lower()}_customer_reason_detail")


def recommendation_for_focus(focus):
    text = str(focus).lower()
    if "source" in text: return "Expand monitored sources, vendor feeds, multilingual discovery terms, and source-miss QA checks."
    if "warroom" in text or "decision" in text: return "Automate WarRoom validation, notification checks, and late/missing WarRoom alerts."
    if "geofenc" in text: return "Improve geofence validation and affected-site proximity checks before publishing."
    if "entity" in text or "supplier" in text: return "Strengthen supplier/entity resolution and customer mapping validation."
    if "cluster" in text or "duplicate" in text: return "Add duplicate-cluster detection and split/merge review controls."
    if "industry" in text: return "Automate industry tagging QA with exception review for ambiguous events."
    if "keyword" in text: return "Maintain keyword expansion from misses, including multilingual variants."
    if "notification" in text: return "Add delivery and visibility monitoring for customer profiles and notification paths."
    return "Review recurring complaint evidence and implement targeted detection, workflow, or validation controls."


def urgency_table(df):
    if df.empty or "Standard Automation Focus" not in df.columns: return pd.DataFrame()
    g = df.groupby("Standard Automation Focus", dropna=False).agg(Records=("Standard Automation Focus", "size"), Customers=("Customer", "nunique") if "Customer" in df.columns else ("Standard Automation Focus", "size"), High_Severity=("Severity", lambda s: int((s.astype(str) == "High").sum())) if "Severity" in df.columns else ("Standard Automation Focus", "size"), RCA_Requested=("RCA Requested", lambda s: int((s.astype(str) == "Yes").sum())) if "RCA Requested" in df.columns else ("Standard Automation Focus", "size"), Misses=("Missed_Flag", lambda s: int((s.astype(str) == "Yes").sum())) if "Missed_Flag" in df.columns else ("Standard Automation Focus", "size")).reset_index()
    g["Urgency Score"] = g["Records"] * 2 + g["High_Severity"] * 3 + g["RCA_Requested"] * 2 + g["Misses"] * 2 + g["Customers"]
    g["Priority"] = g["Urgency Score"].rank(method="first", ascending=False).astype(int)
    g["Recommended control"] = g["Standard Automation Focus"].map(recommendation_for_focus)
    return g.sort_values(["Priority", "Records"])


def manual_entry_form(source_cols):
    with st.expander("Add complaint / inquiry entry manually"):
        st.caption("Use when a valid complaint/inquiry was missed. The entry is staged for review/export, not silently written to production.")
        with st.form("manual_entry_form"):
            c1, c2, c3 = st.columns(3); row = {"Email/JIRA Date": c1.date_input("Email/JIRA Date"), "Customer": c2.text_input("Customer *"), "Issue Type": c3.selectbox("Issue Type *", ["Complaint", "Inquiry"])}
            c4, c5, c6 = st.columns(3); row["Event type"] = c4.text_input("Event type *"); row["Reason"] = c5.text_input("Reason *"); row["Root Cause"] = c6.selectbox("Root Cause", ["", "People", "Process", "Product"])
            row["Event/Bulletin Title"] = st.text_input("Event/Bulletin Title *")
            c7, c8, c9 = st.columns(3); row["Severity"] = c7.selectbox("Severity", ["Medium", "High", "Low"]); row["RCA Requested"] = c8.selectbox("RCA Requested", ["No", "Yes"]); row["Short Term Fix Status"] = c9.selectbox("Short Term Fix Status", ["", "Fixed", "RCA Shared", "Clarification Provided"])
            row["Standard Automation Focus"] = st.text_input("Standard Automation Focus"); row["Comments"] = st.text_area("Comments / evidence summary *")
            save = st.form_submit_button("Save staged entry")
        if save:
            missing = [c for c in ["Customer", "Issue Type", "Event type", "Reason", "Event/Bulletin Title", "Comments"] if not str(row.get(c, "")).strip()]
            if missing: st.error("Missing required fields: " + ", ".join(missing))
            else:
                staged = pd.DataFrame([{**{c: row.get(c, "") for c in source_cols if c in row}, **row}])
                st.success("Manual entry saved for review/export. Download it and add it through the approved tracker update process.")
                st.dataframe(staged, use_container_width=True, hide_index=True)
                st.download_button("Download staged manual entry CSV", staged.to_csv(index=False).encode(), "manual_complaint_entry.csv", "text/csv")


st.sidebar.title(APP_TITLE); st.sidebar.caption("Executive navigation")
selected_page = st.sidebar.radio("Dashboard pages", PAGES, label_visibility="collapsed")
df = load_data()
if df.empty: st.stop()
filtered = sidebar_filters(df)

if selected_page == "Executive Summary":
    page_header(selected_page); page = date_filter(filtered, "executive")
    complaints = page[page["Issue Type"].astype(str).eq("Complaint")] if "Issue Type" in page.columns else page
    inquiries = page[page["Issue Type"].astype(str).eq("Inquiry")] if "Issue Type" in page.columns else page.iloc[0:0]
    total = max(len(page), 1); missed = int((page.get("Missed_Flag", pd.Series(dtype=str)).astype(str) == "Yes").sum()) if "Missed_Flag" in page.columns else 0
    people = int((page.get("Root Cause", pd.Series(dtype=str)).astype(str) == "People").sum()) if "Root Cause" in page.columns else 0; process = int((page.get("Root Cause", pd.Series(dtype=str)).astype(str) == "Process").sum()) if "Root Cause" in page.columns else 0; product = int((page.get("Root Cause", pd.Series(dtype=str)).astype(str) == "Product").sum()) if "Root Cause" in page.columns else 0
    kpis([("Total records", len(page), f"{len(complaints)} complaints · {len(inquiries)} inquiries", "#8ab4f8"), ("Complaints %", f"{len(complaints)/total*100:.1f}%", "Share of selected records", "#f28b82"), ("Missed events", missed, f"{missed/total*100:.1f}% of selected records", "#f6c177"), ("People misses", people, "People-rooted records", "#b6beca"), ("Process/Product", f"{process}/{product}", "Process vs Product root causes", "#80cbc4")])
    kpis([("High severity", int((page.get("Severity", pd.Series(dtype=str)).astype(str) == "High").sum()) if "Severity" in page.columns else 0, "Records needing leadership attention", "#f28b82"), ("RCA requested", int((page.get("RCA Requested", pd.Series(dtype=str)).astype(str) == "Yes").sum()) if "RCA Requested" in page.columns else 0, "Customer/Product/CS RCA asks", "#f6c177"), ("Fixed", int((page.get("Short Term Fix Status", pd.Series(dtype=str)).astype(str) == "Fixed").sum()) if "Short Term Fix Status" in page.columns else 0, "Completed short-term fixes", "#a8dab5"), ("RCA shared", int((page.get("Short Term Fix Status", pd.Series(dtype=str)).astype(str) == "RCA Shared").sum()) if "Short Term Fix Status" in page.columns else 0, "RCA shared or approved", "#80cbc4"), ("Clarified", int((page.get("Short Term Fix Status", pd.Series(dtype=str)).astype(str) == "Clarification Provided").sum()) if "Short Term Fix Status" in page.columns else 0, "Clarifications completed", "#8ab4f8")])
    add_section("Event Summary Intelligence", "Customer pain, complaint nature, missed-event patterns, root causes, severity, and automation opportunities for the selected date range.")
    for title, col in [("Top complaints by customer", "Customer"), ("Nature of complaints", "Reason"), ("Missed event types", "Event type"), ("Root cause split", "Root Cause"), ("Severity split", "Severity"), ("Automation opportunities", "Standard Automation Focus")]:
        if col in complaints.columns:
            t = count_table(complaints, col).head(10); add_section(title, f"Shows the leading {col.lower()} values for complaint records, with count and percentage of total complaints."); excel_bar_table(t, col); fig = chart(t, col, title); downloads(t, title.lower().replace(" ", "_"), fig)
elif selected_page == "SOURCE 01 · Monthly trend":
    page_header(selected_page); page = date_filter(filtered, "monthly")
    if "Month Label" in page.columns and "Issue Type" in page.columns:
        monthly = page.groupby("Month Label", dropna=False)["Issue Type"].value_counts().unstack(fill_value=0).reset_index()
        monthly["Month Date"] = pd.to_datetime(monthly["Month Label"], format="%b %Y", errors="coerce")
        monthly = monthly.sort_values("Month Date"); monthly["Total"] = monthly.drop(columns=["Month Label", "Month Date"]).sum(axis=1)
        display_monthly = monthly.drop(columns=["Month Date"], errors="ignore")
        add_section("Monthly trend source table", "Complaint and inquiry counts by reporting month, sorted chronologically from January onward."); st.dataframe(display_monthly, use_container_width=True, hide_index=True); downloads(display_monthly, "monthly_trend")
        y_cols = [c for c in ["Complaint", "Inquiry"] if c in monthly.columns]
        add_section("Monthly complaint vs inquiry chart", "Compares complaint and inquiry volume month by month in calendar order.", "#80cbc4")
        fig = px.bar(monthly, x="Month Label", y=y_cols, barmode="group", text_auto=True, color_discrete_sequence=["#8ab4f8", "#80cbc4"])
        fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26", font=dict(color="#f3f4f6", size=13), margin=dict(l=20, r=30, t=30, b=40), height=430)
        fig.update_xaxes(categoryorder="array", categoryarray=monthly["Month Label"].tolist(), tickfont=dict(color="#f3f4f6"), gridcolor="#303846"); fig.update_yaxes(tickfont=dict(color="#f3f4f6"), gridcolor="#303846")
        st.plotly_chart(fig, use_container_width=True); downloads(display_monthly, "monthly_trend_chart_data", fig)
    else: st.info("Monthly trend requires Month/Reporting Month and Issue Type fields.")
elif selected_page == "SOURCE 02 · Fix status": source_page(selected_page, filtered, "Short Term Fix Status", "fix_status")
elif selected_page == "SOURCE 03 · Severity": source_page(selected_page, filtered, "Severity", "severity")
elif selected_page == "SOURCE 04 · Root cause": source_page(selected_page, filtered, "Root Cause", "root_cause")
elif selected_page == "SOURCE 05 · Top customers": source_page(selected_page, filtered, "Customer", "top_customers")
elif selected_page == "SOURCE 06 · Automation focus": source_page(selected_page, filtered, "Standard Automation Focus", "automation_focus")
elif selected_page == "DETAIL · Event workload": source_page(selected_page, filtered, "Event type", "event_workload")
elif selected_page == "Automation urgency":
    page_header(selected_page); page = date_filter(filtered, "urgency"); complaints = page[page["Issue Type"].astype(str).eq("Complaint")] if "Issue Type" in page.columns else page; t = urgency_table(complaints)
    add_section("Automation urgency table", "Ranks pressing control areas by volume, severity, RCA pressure, missed flags, and customer concentration.", "#f6c177"); st.dataframe(t, use_container_width=True, hide_index=True); downloads(t, "automation_urgency")
    if not t.empty: add_section("Automation urgency score chart", "Visual ranking of the most urgent automation/control opportunities.", "#80cbc4"); fig = chart(t, "Standard Automation Focus", "Urgency Score", "Automation urgency score"); downloads(t, "automation_urgency_chart_data", fig)
elif selected_page == "Dynamic Source Discovery":
    page_header(selected_page); page = date_filter(filtered, "discovery"); disc = page[page["Standard Automation Focus"].astype(str).eq("Dynamic Source Discovery")] if "Standard Automation Focus" in page.columns else page.iloc[0:0]
    add_section("Source-miss meaning", "Dynamic Source Discovery identifies event types, customers, reasons, feeds, keywords, or source coverage patterns that current sources are missing or under-detecting.", "#80cbc4")
    for title, col in [("Event types missed by sources", "Event type"), ("Customers affected by source misses", "Customer"), ("Reasons linked to source misses", "Reason")]:
        if col in disc.columns: t = count_table(disc, col, base=max(len(page), 1)); add_section(title, f"Shows source-miss records by {col.lower()} with share of all selected records."); excel_bar_table(t, col); fig = chart(t, col, title); downloads(t, title.lower().replace(" ", "_"), fig)
    for first, second, name in [("Customer", "Event type", "Customer event-type source misses"), ("Event type", "Reason", "Event-type reason source misses"), ("Customer", "Reason", "Customer reason source misses")]:
        lt = long_pair_table(disc, first, second, base=max(len(page), 1))
        if not lt.empty: add_section(name, f"Readable detail table showing {first.lower()} and {second.lower()} as separate columns instead of a wide cross-tab.", "#a8dab5"); st.dataframe(lt, use_container_width=True, hide_index=True, height=420); downloads(lt, name.lower().replace(" ", "_"))
    add_section("Complete Dynamic Source Discovery records", "All filtered records classified under Dynamic Source Discovery for detailed review.", "#b6beca"); st.dataframe(disc, use_container_width=True, hide_index=True, height=420); downloads(disc, "dynamic_source_discovery_complete")
elif selected_page == "Definitions":
    page_header(selected_page)
    groups = {"Tracker fields":[("Month / Reporting Month","Month used for trend reporting and date filtering."),("Email/JIRA Date","Formal received/logged date for the complaint, inquiry, or Jira trail."),("Customer","Account that raised the concern, not the affected supplier."),("Event/Bulletin Title","Published EventWatch title or concise factual event title."),("Comments","Concise evidence-backed summary of complaint, finding, action, and status.")],"Issue and reason types":[("Complaint","Confirmed or alleged EventWatch service miss, delay, incorrect handling, visibility issue, duplicate/missing WarRoom, or RCA-driven concern."),("Inquiry","Coverage, methodology, supplier/site, or threshold clarification without confirmed service failure."),("Reason","Specific operational issue such as Missed Event, Missed WarRoom, Delayed Event, Duplicate WarRooms, Incorrect Action, or Mapping Clarification.")],"Root cause groups":[("People","Human review, prioritization, judgment, communication, or execution miss."),("Process","Workflow, policy, methodology, handoff, or procedural gap."),("Product","Ingestion, source coverage, keyword, clustering, mapping, visibility, platform, or automation defect/gap.")],"Severity and status":[("High","Material operational or customer-trust impact requiring elevated attention."),("Medium","Standard tracked complaint or quality issue."),("Low","Limited-impact inquiry or minor quality signal."),("Fixed","Corrective action completed."),("RCA Shared","RCA approved/shared for customer communication."),("Clarification Provided","Explanation provided where no fix/RCA is required.")],"Automation focus":[("Dynamic Source Discovery","Source, feed, keyword, vendor monitoring, or article discovery gap."),("WarRoom & Decision Validation","Missing, delayed, duplicate, or incorrect WarRoom/decision handling."),("Entity & Supplier Resolution","Supplier, customer, entity, or mapping quality issue."),("AI-Assisted Geofencing","Location/polygon/proximity validation opportunity."),("Notification Visibility Monitoring","Delivery, profile visibility, and notification path monitoring."),("Cluster Integrity & Duplicate Prevention","Duplicate/split clusters or inconsistent event grouping."),("Automated Industry Tagging","Industry tagging validation or automation."),("Multilingual Keyword Expansion","Language/keyword coverage expansion from observed misses."),("Other Control Automation","Targeted control not covered by the standard categories.")],"Evidence and deduplication":[("Missed_Flag","Yes when expected alerting, coverage, notification, escalation, or WarRoom creation was missed or materially delayed."),("Confidence","HIGH, MEDIUM, or LOW based on evidence quality and duplicate checks."),("Duplicate check","Match against Jira key, Outlook conversation, customer/event title, facility, date/type, and source message ID before adding a new row.")]}
    for group, rows in groups.items(): st.markdown(f"<div class='definition-group'><h3>{group}</h3>", unsafe_allow_html=True); st.table(pd.DataFrame(rows, columns=["Term", "Definition"])); st.markdown("</div>", unsafe_allow_html=True)
elif selected_page == "Complaint Tracker":
    page_header(selected_page); page = date_filter(filtered, "tracker"); concise = [c for c in ["Month Label", "Email/JIRA Date", "Customer", "Event type", "Event/Bulletin Title", "Issue Type", "Reason", "Root Cause", "Short Term Fix Status", "RCA Requested", "Severity", "Standard Automation Focus", "Comments"] if c in page.columns]
    c1, c2 = st.columns(2); c1.download_button("Download visible tracker CSV", page[concise].to_csv(index=False).encode(), "customer_tracker_visible.csv", "text/csv"); c2.download_button("Download full filtered source CSV", page.to_csv(index=False).encode(), "customer_tracker_full_filtered.csv", "text/csv")
    st.dataframe(page[concise], use_container_width=True, hide_index=True, height=560); manual_entry_form(list(df.columns))
