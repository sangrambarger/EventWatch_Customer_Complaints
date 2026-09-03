from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Iterable

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="EventWatch Executive Dashboard", layout="wide")

APP_TITLE = "EventWatch Executive Dashboard"
GITHUB_CSV_DEFAULT = "https://raw.githubusercontent.com/sangrambarger/EventWatch_Customer_Complaints/main/customer_tracker.csv"

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
    "Executive Summary": "Leadership cockpit covering volume, customer concentration, misses, RCA exposure, source gaps, and automation priorities.",
    "SOURCE 01 · Monthly trend": "Complaint and inquiry movement by reporting month.",
    "SOURCE 02 · Fix status": "Current resolution posture across fixed, clarified, and RCA-shared records.",
    "SOURCE 03 · Severity": "Operational weight of complaints and inquiries by severity.",
    "SOURCE 04 · Root cause": "People, Process, and Product themes behind customer pain.",
    "SOURCE 05 · Top customers": "Customers most frequently represented in the tracker and their complaint patterns.",
    "SOURCE 06 · Automation focus": "Standard automation-control categories linked to complaint evidence.",
    "DETAIL · Event workload": "Event types generating repeated service risk.",
    "Automation urgency": "Prioritized controls ranked by volume, severity, misses, RCA pressure, and customer concentration.",
    "Dynamic Source Discovery": "Event types, customers, and reasons tied to source coverage or discovery gaps.",
    "Definitions": "Structured glossary for tracker fields, classification rules, statuses, and automation categories.",
    "Complaint Tracker": "Filtered operational tracker with export and controlled manual-entry staging.",
}

CSS = """
<style>
:root {
  --bg:#eef1f4; --panel:#ffffff; --panel2:#f8fafc; --ink:#202124; --muted:#5f6368;
  --line:#d7dde4; --line2:#aeb8c4; --blue:#3b6f9f; --blue2:#d8e5f2;
  --green:#4f7d63; --amber:#a36b22; --red:#9f4b4b; --teal:#427f87;
}
html, body, [data-testid="stAppViewContainer"] { background:var(--bg); color:var(--ink); }
.main .block-container { padding-top:.8rem; padding-bottom:2rem; max-width:1440px; }
[data-testid="stSidebar"] { background:#172638; border-right:1px solid #2d4058; }
[data-testid="stSidebar"] * { color:#f1f5f9; }
[data-testid="stSidebar"] label { color:#cbd5e1 !important; }
[data-testid="stSidebar"] .stRadio > div { gap:10px; }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label {
  background:transparent; border:1px solid rgba(255,255,255,.12); border-radius:8px; padding:9px 12px;
  margin:5px 0; transition:all .15s ease; box-shadow:none;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:hover { background:rgba(255,255,255,.08); }
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:has(input:checked) {
  background:#f1f5f9; border-color:#f1f5f9;
}
[data-testid="stSidebar"] .stRadio div[role="radiogroup"] > label:has(input:checked) * { color:#172638 !important; font-weight:800; }
[data-testid="stSidebar"] .stRadio input { display:none; }
h1,h2,h3,h4,h5,h6,p,span,div { color:var(--ink); }
.page-hero { background:var(--panel); border:1px solid var(--line); border-left:5px solid var(--blue); padding:12px 16px; margin-bottom:12px; box-shadow:0 2px 8px rgba(32,33,36,.06); }
.page-hero h1 { margin:0 0 4px 0; font-size:26px; line-height:1.15; color:var(--ink); }
.page-hero p { margin:0; font-size:14px; color:var(--muted); }
.filter-panel { background:var(--panel); border:1px solid var(--line); padding:10px 12px 4px; margin-bottom:12px; box-shadow:0 1px 6px rgba(32,33,36,.05); }
.kpi-grid { display:grid; grid-template-columns:repeat(5,minmax(140px,1fr)); gap:10px; margin:10px 0 14px; }
.kpi { min-height:92px; background:var(--panel); border:1px solid var(--line); border-top:4px solid var(--accent); padding:11px 12px; box-shadow:0 2px 8px rgba(32,33,36,.06); }
.kpi-label { font-size:11px; color:var(--muted); font-weight:800; text-transform:uppercase; letter-spacing:.035em; }
.kpi-num { font-size:29px; font-weight:900; line-height:1.05; margin:6px 0; color:var(--ink); }
.kpi-foot { font-size:12px; color:var(--muted); line-height:1.25; }
.section-card { background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--accent,var(--blue)); padding:12px 14px; margin-bottom:12px; box-shadow:0 2px 8px rgba(32,33,36,.05); }
.section-card h3 { margin:0 0 10px 0; font-size:22px; color:var(--ink); }
.section-card h4 { margin:0 0 8px 0; color:var(--ink); }
.insight-row { display:grid; grid-template-columns:repeat(2,minmax(260px,1fr)); gap:10px; margin-bottom:12px; }
.insight-box { background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--accent,var(--blue)); padding:11px 12px; box-shadow:0 2px 8px rgba(32,33,36,.05); font-size:14px; }
.excel-table { width:100%; border-collapse:collapse; background:var(--panel); font-size:13px; table-layout:fixed; }
.excel-table th { background:#355f87; color:#fff; border:1px solid #7896b4; padding:8px 9px; text-align:center; font-weight:850; }
.excel-table td { border:1px solid var(--line); padding:7px 9px; vertical-align:middle; background:#fff; color:var(--ink); }
.excel-table tr:nth-child(even) td { background:#f7f9fb; }
.excel-table td:first-child { text-align:left; overflow-wrap:anywhere; }
.excel-table td:not(:first-child) { text-align:center; }
.bar-cell { padding:0!important; }
.bar-box { position:relative; min-height:32px; display:flex; align-items:center; justify-content:center; overflow:hidden; }
.bar-box::before { content:""; position:absolute; inset:0 auto 0 0; width:var(--w); background:linear-gradient(90deg,rgba(59,111,159,.55),rgba(59,111,159,.12)); }
.bar-box span { position:relative; z-index:1; color:var(--ink); font-weight:900; text-shadow:0 1px 0 rgba(255,255,255,.55); }
.toolbar { display:flex; gap:8px; flex-wrap:wrap; margin:.2rem 0 .5rem; }
.definition-group { background:var(--panel); border:1px solid var(--line); border-left:4px solid var(--teal); padding:12px 14px; margin-bottom:12px; }
[data-testid="stDataFrame"], [data-testid="stTable"] { background:var(--panel); border:1px solid var(--line); }
.stDownloadButton button, .stButton button, .stFormSubmitButton button { background:#355f87; color:white; border:1px solid #355f87; border-radius:6px; font-weight:800; }
@media (max-width:1200px){ .kpi-grid{grid-template-columns:repeat(2,minmax(180px,1fr));}.insight-row{grid-template-columns:1fr;} }
@media (max-width:760px){ .kpi-grid{grid-template-columns:1fr;} }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def load_data() -> pd.DataFrame:
    url = st.secrets.get("GITHUB_CSV_URL", GITHUB_CSV_DEFAULT) if hasattr(st, "secrets") else GITHUB_CSV_DEFAULT
    try:
        df = pd.read_csv(url)
        st.sidebar.success("Live GitHub CSV data")
    except Exception as exc:
        st.error("Live GitHub CSV could not be loaded. This production dashboard does not support workbook upload fallback.")
        st.caption(f"Data source attempted: {url}")
        st.caption(f"Load error: {exc}")
        return pd.DataFrame()

    if not df.empty and str(df.columns[0]).startswith("Unnamed"):
        df = df.drop(columns=df.columns[0])
    for col in ["Month", "Email/JIRA Date", "Reporting Month"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    if "Month Label" not in df.columns:
        source = "Reporting Month" if "Reporting Month" in df.columns else "Month" if "Month" in df.columns else None
        if source:
            df["Month Label"] = df[source].dt.strftime("%b %Y")
    return df


def page_header(title: str):
    st.markdown(f"<div class='page-hero'><h1>{title}</h1><p>{PAGE_DESCRIPTIONS.get(title,'')}</p></div>", unsafe_allow_html=True)


def date_filter(df: pd.DataFrame, key: str) -> pd.DataFrame:
    if df.empty:
        return df
    date_col = next((c for c in ["Reporting Month", "Month", "Email/JIRA Date"] if c in df.columns), None)
    if not date_col:
        return df
    dates = df[date_col].dropna()
    if dates.empty:
        return df
    min_date, max_date = dates.min().date(), dates.max().date()
    st.markdown("<div class='filter-panel'>", unsafe_allow_html=True)
    a, b, c = st.columns([1, 1, 2])
    start = a.date_input("Start date", min_date, min_value=min_date, max_value=max_date, key=f"{key}_start")
    end = b.date_input("End date", max_date, min_value=min_date, max_value=max_date, key=f"{key}_end")
    c.caption(f"Date filter uses **{date_col}** and applies to this page.")
    st.markdown("</div>", unsafe_allow_html=True)
    if start > end:
        st.warning("Start date is after end date. Showing the full available range.")
        return df
    return df[(df[date_col].dt.date >= start) & (df[date_col].dt.date <= end)].copy()


def apply_sidebar_filters(df: pd.DataFrame) -> pd.DataFrame:
    st.sidebar.markdown("---")
    st.sidebar.markdown("### Filters")
    out = df.copy()
    for col in ["Customer", "Event type", "Issue Type", "Severity", "Root Cause", "Reason", "Short Term Fix Status", "RCA Requested", "Standard Automation Focus"]:
        if col in out.columns:
            vals = sorted(out[col].dropna().astype(str).unique())
            chosen = st.sidebar.multiselect(col, vals, key=f"filter_{col}")
            if chosen:
                out = out[out[col].astype(str).isin(chosen)]
    q = st.sidebar.text_input("Search tracker")
    if q:
        out = out[out.astype(str).apply(lambda r: r.str.contains(q, case=False, na=False).any(), axis=1)]
    return out


def count_table(df: pd.DataFrame, col: str, base: int | None = None) -> pd.DataFrame:
    if df.empty or col not in df.columns:
        return pd.DataFrame(columns=[col, "Records", "% of Total"])
    t = df[col].fillna("Blank").astype(str).value_counts().reset_index()
    t.columns = [col, "Records"]
    denom = max(base or len(df), 1)
    t["% of Total"] = (t["Records"] / denom * 100).round(1).astype(str) + "%"
    return t


def cross_table(df: pd.DataFrame, rows: str, cols: str) -> pd.DataFrame:
    if df.empty or rows not in df.columns or cols not in df.columns:
        return pd.DataFrame()
    return pd.crosstab(df[rows].fillna("Blank"), df[cols].fillna("Blank")).reset_index()


def metric_card(label, value, foot="", accent="#3b6f9f"):
    st.markdown(f"<div class='kpi' style='--accent:{accent}'><div class='kpi-label'>{label}</div><div class='kpi-num'>{value}</div><div class='kpi-foot'>{foot}</div></div>", unsafe_allow_html=True)


def kpis(items: Iterable[tuple]):
    st.markdown("<div class='kpi-grid'>", unsafe_allow_html=True)
    for item in items:
        metric_card(*item)
    st.markdown("</div>", unsafe_allow_html=True)


def excel_bar_table(df: pd.DataFrame, label_col: str, value_col: str = "Records"):
    if df.empty:
        st.info("No data available for this view.")
        return
    max_v = max(float(df[value_col].max()), 1)
    rows = []
    for _, r in df.iterrows():
        width = float(r[value_col]) / max_v * 100
        rows.append(f"<tr><td>{r[label_col]}</td><td class='bar-cell'><div class='bar-box' style='--w:{width:.1f}%'><span>{r[value_col]}</span></div></td><td>{r.get('% of Total','')}</td></tr>")
    st.markdown("<table class='excel-table'><thead><tr><th>Category</th><th>Records</th><th>% of Total</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>", unsafe_allow_html=True)


def chart(df: pd.DataFrame, label_col: str, value_col: str = "Records", title: str = "", kind: str = "bar"):
    if df.empty:
        return None
    data = df.head(20).copy()
    if kind == "pie":
        fig = px.pie(data, names=label_col, values=value_col, hole=.42, title=title, color_discrete_sequence=px.colors.qualitative.Safe)
    else:
        fig = px.bar(data, x=value_col, y=label_col, orientation="h", text=value_col, title=title, color_discrete_sequence=["#3b6f9f"])
        fig.update_yaxes(categoryorder="total ascending", tickfont=dict(size=13, color="#202124"))
        fig.update_xaxes(tickfont=dict(size=12, color="#202124"), gridcolor="#dfe5ec")
        fig.update_traces(opacity=.9, textposition="outside", cliponaxis=False)
    fig.update_layout(template="plotly_white", plot_bgcolor="#fff", paper_bgcolor="#fff", font=dict(color="#202124", size=13), margin=dict(l=20, r=45, t=44, b=28), height=max(360, min(720, len(data) * 36 + 130)), showlegend=(kind == "pie"))
    st.plotly_chart(fig, use_container_width=True)
    return fig


def download_section(df: pd.DataFrame, name: str, fig=None):
    c1, c2, c3 = st.columns([1, 1, 3])
    c1.download_button("Download table CSV", df.to_csv(index=False).encode(), f"{name}.csv", "text/csv", key=f"csv_{name}")
    if fig is not None:
        try:
            c2.download_button("Download chart HTML", fig.to_html().encode(), f"{name}_chart.html", "text/html", key=f"chart_{name}")
        except Exception:
            pass
    c3.caption("Use the chart toolbar to zoom, pan, reset, or view details on hover.")


def source_page(title: str, df: pd.DataFrame, col: str, key: str):
    page_header(title)
    page = date_filter(df, key)
    t = count_table(page, col)
    st.markdown("<div class='section-card' style='--accent:#3b6f9f'><h3>Source table</h3>", unsafe_allow_html=True)
    excel_bar_table(t, col)
    download_section(t, key)
    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-card' style='--accent:#427f87'><h3>Chart view</h3>", unsafe_allow_html=True)
    fig = chart(t, col, title=title)
    download_section(t, f"{key}_chart_data", fig)
    st.markdown("</div>", unsafe_allow_html=True)
    if col == "Customer":
        extra = cross_table(page, "Customer", "Reason")
        if not extra.empty:
            st.markdown("<div class='section-card' style='--accent:#4f7d63'><h3>Customer × reason table</h3>", unsafe_allow_html=True)
            st.dataframe(extra, use_container_width=True, hide_index=True)
            download_section(extra, "customer_reason")
            st.markdown("</div>", unsafe_allow_html=True)


def urgency_table(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "Standard Automation Focus" not in df.columns:
        return pd.DataFrame()
    g = df.groupby("Standard Automation Focus", dropna=False).agg(
        Records=("Standard Automation Focus", "size"),
        Customers=("Customer", "nunique") if "Customer" in df.columns else ("Standard Automation Focus", "size"),
        High_Severity=("Severity", lambda s: int((s.astype(str) == "High").sum())) if "Severity" in df.columns else ("Standard Automation Focus", "size"),
        RCA_Requested=("RCA Requested", lambda s: int((s.astype(str) == "Yes").sum())) if "RCA Requested" in df.columns else ("Standard Automation Focus", "size"),
        Misses=("Missed_Flag", lambda s: int((s.astype(str) == "Yes").sum())) if "Missed_Flag" in df.columns else ("Standard Automation Focus", "size"),
    ).reset_index()
    g["Urgency Score"] = g["Records"] * 2 + g["High_Severity"] * 3 + g["RCA_Requested"] * 2 + g["Misses"] * 2 + g["Customers"]
    g["Priority"] = g["Urgency Score"].rank(method="first", ascending=False).astype(int)
    g["Recommended control"] = g["Standard Automation Focus"].astype(str).map(recommendation_for_focus)
    return g.sort_values(["Priority", "Records"])


def recommendation_for_focus(focus: str) -> str:
    text = focus.lower()
    if "source" in text: return "Expand monitored sources, vendor feeds, multilingual discovery terms, and source-miss QA checks."
    if "warroom" in text or "decision" in text: return "Automate WarRoom validation, notification checks, and late/missing WarRoom alerts."
    if "geofenc" in text: return "Improve geofence validation and affected-site proximity checks before publishing."
    if "entity" in text or "supplier" in text: return "Strengthen supplier/entity resolution and customer mapping validation."
    if "cluster" in text or "duplicate" in text: return "Add duplicate-cluster detection and split/merge review controls."
    if "industry" in text: return "Automate industry tagging QA with exception review for ambiguous events."
    if "keyword" in text: return "Maintain keyword expansion from misses, including multilingual variants."
    if "notification" in text: return "Add delivery and visibility monitoring for customer profiles and notification paths."
    return "Review recurring complaint evidence and implement targeted detection, workflow, or validation controls."


def manual_entry_form(source_cols: list[str]):
    with st.expander("Add complaint / inquiry entry manually", expanded=False):
        st.caption("Use this when a valid complaint or inquiry was missed. The entry is staged for review/export; production CSV updates should still follow approval and write controls.")
        with st.form("manual_entry_form"):
            c1, c2, c3 = st.columns(3)
            row = {}
            row["Email/JIRA Date"] = c1.date_input("Email/JIRA Date")
            row["Customer"] = c2.text_input("Customer *")
            row["Issue Type"] = c3.selectbox("Issue Type *", ["Complaint", "Inquiry"])
            c4, c5, c6 = st.columns(3)
            row["Event type"] = c4.text_input("Event type *")
            row["Reason"] = c5.text_input("Reason *")
            row["Root Cause"] = c6.selectbox("Root Cause", ["", "People", "Process", "Product"])
            row["Event/Bulletin Title"] = st.text_input("Event/Bulletin Title *")
            c7, c8, c9 = st.columns(3)
            row["Severity"] = c7.selectbox("Severity", ["Medium", "High", "Low"])
            row["RCA Requested"] = c8.selectbox("RCA Requested", ["No", "Yes"])
            row["Short Term Fix Status"] = c9.selectbox("Short Term Fix Status", ["", "Fixed", "RCA Shared", "Clarification Provided"])
            row["Standard Automation Focus"] = st.text_input("Standard Automation Focus")
            row["Comments"] = st.text_area("Comments / evidence summary *")
            save = st.form_submit_button("Save staged entry")
        if save:
            required = ["Customer", "Issue Type", "Event type", "Reason", "Event/Bulletin Title", "Comments"]
            missing = [c for c in required if not str(row.get(c, "")).strip()]
            if missing:
                st.error("Missing required fields: " + ", ".join(missing))
            else:
                clean = {c: row.get(c, "") for c in source_cols if c in row}
                for k, v in row.items():
                    clean.setdefault(k, v)
                staged = pd.DataFrame([clean])
                st.success("Manual entry saved for review/export. Download it and add it through the approved tracker update process.")
                st.dataframe(staged, use_container_width=True, hide_index=True)
                st.download_button("Download staged manual entry CSV", staged.to_csv(index=False).encode(), "manual_complaint_entry.csv", "text/csv")


st.sidebar.title(APP_TITLE)
st.sidebar.caption("Executive navigation")
selected_page = st.sidebar.radio("Dashboard pages", PAGE_OPTIONS, label_visibility="collapsed")

df = load_data()
if df.empty:
    st.stop()
filtered = apply_sidebar_filters(df)

if selected_page == "Executive Summary":
    page_header(selected_page)
    page = date_filter(filtered, "executive")
    complaints = page[page["Issue Type"].astype(str).eq("Complaint")] if "Issue Type" in page.columns else page
    inquiries = page[page["Issue Type"].astype(str).eq("Inquiry")] if "Issue Type" in page.columns else page.iloc[0:0]
    total = max(len(page), 1)
    missed = int((page.get("Missed_Flag", pd.Series(dtype=str)).astype(str) == "Yes").sum()) if "Missed_Flag" in page.columns else 0
    people = int((page.get("Root Cause", pd.Series(dtype=str)).astype(str) == "People").sum()) if "Root Cause" in page.columns else 0
    process = int((page.get("Root Cause", pd.Series(dtype=str)).astype(str) == "Process").sum()) if "Root Cause" in page.columns else 0
    product = int((page.get("Root Cause", pd.Series(dtype=str)).astype(str) == "Product").sum()) if "Root Cause" in page.columns else 0
    kpis([
        ("Total records", len(page), f"{len(complaints)} complaints · {len(inquiries)} inquiries", "#3b6f9f"),
        ("Complaints %", f"{len(complaints)/total*100:.1f}%", "Share of selected records", "#9f4b4b"),
        ("Missed events", missed, f"{missed/total*100:.1f}% of selected records", "#a36b22"),
        ("People misses", people, "People-rooted records", "#5f6368"),
        ("Process/Product", f"{process}/{product}", "Process vs Product root causes", "#427f87"),
    ])
    st.markdown("<div class='insight-row'>", unsafe_allow_html=True)
    top_customer = count_table(complaints, "Customer").head(1)
    top_reason = count_table(complaints, "Reason").head(1)
    st.markdown(f"<div class='insight-box' style='--accent:#3b6f9f'><b>Most complaining customer:</b> {top_customer.iloc[0,0] if not top_customer.empty else 'No complaint customer in range'}.</div>", unsafe_allow_html=True)
    st.markdown(f"<div class='insight-box' style='--accent:#a36b22'><b>Leading complaint nature:</b> {top_reason.iloc[0,0] if not top_reason.empty else 'No complaint reason in range'}.</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)
    sections = [("Top complaints by customer", "Customer"), ("Nature of complaints", "Reason"), ("Missed event types", "Event type"), ("Automation opportunities", "Standard Automation Focus")]
    for title, col in sections:
        if col in complaints.columns:
            t = count_table(complaints, col).head(10)
            st.markdown(f"<div class='section-card' style='--accent:#3b6f9f'><h3>{title}</h3>", unsafe_allow_html=True)
            excel_bar_table(t, col)
            fig = chart(t, col, title=title)
            download_section(t, title.lower().replace(' ', '_'), fig)
            st.markdown("</div>", unsafe_allow_html=True)

elif selected_page == "SOURCE 01 · Monthly trend":
    page_header(selected_page)
    page = date_filter(filtered, "monthly")
    if "Month Label" in page.columns and "Issue Type" in page.columns:
        monthly = page.groupby("Month Label", dropna=False)["Issue Type"].value_counts().unstack(fill_value=0).reset_index()
        monthly["Total"] = monthly.drop(columns=["Month Label"]).sum(axis=1)
        st.markdown("<div class='section-card' style='--accent:#3b6f9f'><h3>Source table</h3>", unsafe_allow_html=True)
        st.dataframe(monthly, use_container_width=True, hide_index=True)
        download_section(monthly, "monthly_trend")
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div class='section-card' style='--accent:#427f87'><h3>Grouped monthly chart</h3>", unsafe_allow_html=True)
        y = [c for c in ["Complaint", "Inquiry"] if c in monthly.columns]
        fig = px.bar(monthly, x="Month Label", y=y, barmode="group", text_auto=True, color_discrete_sequence=["#3b6f9f", "#7b8b9a"])
        fig.update_layout(template="plotly_white", plot_bgcolor="#fff", paper_bgcolor="#fff", font=dict(color="#202124", size=13), margin=dict(l=20, r=30, t=30, b=40), height=430)
        fig.update_xaxes(tickfont=dict(color="#202124", size=12)); fig.update_yaxes(tickfont=dict(color="#202124", size=12), gridcolor="#dfe5ec")
        st.plotly_chart(fig, use_container_width=True)
        download_section(monthly, "monthly_trend_chart_data", fig)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.info("Monthly trend requires Month/Reporting Month and Issue Type fields.")

elif selected_page == "SOURCE 02 · Fix status": source_page(selected_page, filtered, "Short Term Fix Status", "fix_status")
elif selected_page == "SOURCE 03 · Severity": source_page(selected_page, filtered, "Severity", "severity")
elif selected_page == "SOURCE 04 · Root cause": source_page(selected_page, filtered, "Root Cause", "root_cause")
elif selected_page == "SOURCE 05 · Top customers": source_page(selected_page, filtered, "Customer", "top_customers")
elif selected_page == "SOURCE 06 · Automation focus": source_page(selected_page, filtered, "Standard Automation Focus", "automation_focus")
elif selected_page == "DETAIL · Event workload": source_page(selected_page, filtered, "Event type", "event_workload")

elif selected_page == "Automation urgency":
    page_header(selected_page)
    page = date_filter(filtered, "urgency")
    complaints = page[page["Issue Type"].astype(str).eq("Complaint")] if "Issue Type" in page.columns else page
    t = urgency_table(complaints)
    st.markdown("<div class='section-card' style='--accent:#a36b22'><h3>Urgency table</h3>", unsafe_allow_html=True)
    st.dataframe(t, use_container_width=True, hide_index=True)
    download_section(t, "automation_urgency")
    st.markdown("</div>", unsafe_allow_html=True)
    if not t.empty:
        st.markdown("<div class='section-card' style='--accent:#427f87'><h3>Urgency score graph</h3>", unsafe_allow_html=True)
        fig = chart(t, "Standard Automation Focus", "Urgency Score", "Automation urgency score")
        download_section(t, "automation_urgency_chart_data", fig)
        st.markdown("</div>", unsafe_allow_html=True)

elif selected_page == "Dynamic Source Discovery":
    page_header(selected_page)
    page = date_filter(filtered, "discovery")
    if "Standard Automation Focus" in page.columns:
        disc = page[page["Standard Automation Focus"].astype(str).eq("Dynamic Source Discovery")]
    else:
        disc = page.iloc[0:0]
    st.markdown("<div class='section-card' style='--accent:#427f87'><h3>Source-miss meaning</h3><p>Dynamic Source Discovery identifies event types, customers, reasons, feeds, keywords, or source coverage patterns that the current sensing setup is missing or under-detecting.</p></div>", unsafe_allow_html=True)
    for title, col in [("Event types missed by sources", "Event type"), ("Customers affected by source misses", "Customer"), ("Reasons linked to source misses", "Reason")]:
        if col in disc.columns:
            t = count_table(disc, col, base=max(len(page), 1))
            st.markdown(f"<div class='section-card' style='--accent:#3b6f9f'><h3>{title}</h3>", unsafe_allow_html=True)
            excel_bar_table(t, col)
            fig = chart(t, col, title=title)
            download_section(t, title.lower().replace(' ', '_'), fig)
            st.markdown("</div>", unsafe_allow_html=True)
    for rows, cols, name in [("Customer", "Event type", "Customer × event type"), ("Event type", "Reason", "Event type × reason"), ("Customer", "Reason", "Customer × reason")]:
        ct = cross_table(disc, rows, cols)
        if not ct.empty:
            st.markdown(f"<div class='section-card' style='--accent:#4f7d63'><h3>{name}</h3>", unsafe_allow_html=True)
            st.dataframe(ct, use_container_width=True, hide_index=True)
            download_section(ct, name.lower().replace(' ', '_'))
            st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("<div class='section-card' style='--accent:#5f6368'><h3>Complete Dynamic Source Discovery records</h3>", unsafe_allow_html=True)
    st.dataframe(disc, use_container_width=True, hide_index=True, height=420)
    download_section(disc, "dynamic_source_discovery_complete")
    st.markdown("</div>", unsafe_allow_html=True)

elif selected_page == "Definitions":
    page_header(selected_page)
    groups = {
        "Tracker fields": [("Month / Reporting Month", "Month used for trend reporting and date filtering."), ("Email/JIRA Date", "Formal received/logged date for the complaint, inquiry, or Jira trail."), ("Customer", "Account that raised the concern, not the affected supplier."), ("Event/Bulletin Title", "Published EventWatch title or concise factual event title."), ("Comments", "Concise evidence-backed summary of complaint, finding, action, and status.")],
        "Issue and reason types": [("Complaint", "Confirmed or alleged EventWatch service miss, delay, incorrect handling, visibility issue, duplicate/missing WarRoom, or RCA-driven concern."), ("Inquiry", "Coverage, methodology, supplier/site, or threshold clarification without confirmed service failure."), ("Reason", "Specific operational issue such as Missed Event, Missed WarRoom, Delayed Event, Duplicate WarRooms, Incorrect Action, or Mapping Clarification.")],
        "Root cause groups": [("People", "Human review, prioritization, judgment, communication, or execution miss."), ("Process", "Workflow, policy, methodology, handoff, or procedural gap."), ("Product", "Ingestion, source coverage, keyword, clustering, mapping, visibility, platform, or automation defect/gap.")],
        "Severity and status": [("High", "Material operational or customer-trust impact requiring elevated attention."), ("Medium", "Standard tracked complaint or quality issue."), ("Low", "Limited-impact inquiry or minor quality signal."), ("Fixed", "Corrective action completed."), ("RCA Shared", "RCA approved/shared for customer communication."), ("Clarification Provided", "Explanation provided where no fix/RCA is required.")],
        "Automation focus": [("Dynamic Source Discovery", "Source, feed, keyword, vendor monitoring, or article discovery gap."), ("WarRoom & Decision Validation", "Missing, delayed, duplicate, or incorrect WarRoom/decision handling."), ("Entity & Supplier Resolution", "Supplier, customer, entity, or mapping quality issue."), ("AI-Assisted Geofencing", "Location/polygon/proximity validation opportunity."), ("Notification Visibility Monitoring", "Delivery, profile visibility, and notification path monitoring."), ("Cluster Integrity & Duplicate Prevention", "Duplicate/split clusters or inconsistent event grouping."), ("Automated Industry Tagging", "Industry tagging validation or automation."), ("Multilingual Keyword Expansion", "Language/keyword coverage expansion from observed misses."), ("Other Control Automation", "Targeted control not covered by the standard categories.")],
        "Evidence and deduplication": [("Missed_Flag", "Yes when expected alerting, coverage, notification, escalation, or WarRoom creation was missed or materially delayed."), ("Confidence", "HIGH, MEDIUM, or LOW based on evidence quality and duplicate checks."), ("Duplicate check", "Match against Jira key, Outlook conversation, customer/event title, facility, date/type, and source message ID before adding a new row.")],
    }
    for group, rows in groups.items():
        st.markdown(f"<div class='definition-group'><h3>{group}</h3>", unsafe_allow_html=True)
        st.table(pd.DataFrame(rows, columns=["Term", "Definition"]))
        st.markdown("</div>", unsafe_allow_html=True)

elif selected_page == "Complaint Tracker":
    page_header(selected_page)
    page = date_filter(filtered, "tracker")
    concise = [c for c in ["Month Label", "Email/JIRA Date", "Customer", "Event type", "Event/Bulletin Title", "Issue Type", "Reason", "Root Cause", "Short Term Fix Status", "RCA Requested", "Severity", "Standard Automation Focus", "Comments"] if c in page.columns]
    c1, c2 = st.columns(2)
    c1.download_button("Download visible tracker CSV", page[concise].to_csv(index=False).encode(), "customer_tracker_visible.csv", "text/csv")
    c2.download_button("Download full filtered source CSV", page.to_csv(index=False).encode(), "customer_tracker_full_filtered.csv", "text/csv")
    st.dataframe(page[concise], use_container_width=True, hide_index=True, height=560)
    manual_entry_form(list(df.columns))
