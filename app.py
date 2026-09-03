import io
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="EventWatch Executive Dashboard", layout="wide")

APP_TITLE = "EventWatch Executive Dashboard"
DEFAULT_WORKBOOK = "EventWatch_Customer_Complaints_2026.xlsx"

st.markdown("""
<style>
.main .block-container {padding-top: 1.1rem; padding-bottom: 2rem;}
section[data-testid="stSidebar"] {background:#27465f;}
section[data-testid="stSidebar"] * {color:white;}
.excel-card {background:white; border:1px solid #d6e0ea; border-left:4px solid #326887; padding:16px 18px; margin-bottom:14px; box-shadow:0 5px 14px rgba(34,52,72,.07);}
.kpi {background:white; border:1px solid #d6e0ea; padding:14px; box-shadow:0 5px 14px rgba(34,52,72,.07);}
.kpi-label {font-size:12px; color:#64748b; font-weight:700; text-transform:uppercase;}
.kpi-num {font-size:30px; font-weight:850; color:#0f2c47;}
.note {font-size:12px; color:#52677f;}
</style>
""", unsafe_allow_html=True)


def load_data(uploaded_file=None):
    source = uploaded_file if uploaded_file is not None else Path(DEFAULT_WORKBOOK)
    if uploaded_file is None and not Path(DEFAULT_WORKBOOK).exists():
        st.warning("Upload the EventWatch workbook in the sidebar, or add EventWatch_Customer_Complaints_2026.xlsx to the repo.")
        return pd.DataFrame()
    df = pd.read_excel(source, sheet_name="Data")
    if df.columns[0].startswith("Unnamed"):
        df = df.drop(columns=df.columns[0])
    for col in ["Month", "Email/JIRA Date", "Reporting Month"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    if "Month" in df.columns:
        df["Month Label"] = df["Month"].dt.strftime("%b %Y")
    return df


def metric_card(label, value, foot=""):
    st.markdown(f"""
    <div class="kpi"><div class="kpi-label">{label}</div><div class="kpi-num">{value}</div><div class="note">{foot}</div></div>
    """, unsafe_allow_html=True)


def count_table(df, col, issue_type=None, pct_base=None):
    work = df.copy()
    if issue_type and "Issue Type" in work.columns:
        work = work[work["Issue Type"].eq(issue_type)]
    out = work[col].fillna("Blank").value_counts().reset_index()
    out.columns = [col, "Records"]
    base = pct_base or max(out["Records"].sum(), 1)
    out["% of Total"] = (out["Records"] / base * 100).round(0).astype(int).astype(str) + "%"
    return out


def bar_chart(df, x_col, y_col="Records", title=""):
    fig = px.bar(df, x=y_col, y=x_col, orientation="h", text=y_col, title=title)
    fig.update_layout(plot_bgcolor="white", paper_bgcolor="white", font_color="#183048", margin=dict(l=10, r=10, t=35, b=10), height=max(320, len(df) * 34), yaxis={"categoryorder":"total ascending"}, showlegend=False)
    fig.update_traces(marker_color="#638ec6", opacity=.72, textposition="outside")
    st.plotly_chart(fig, use_container_width=True)


def excel_bar_table(df, label_col, value_col="Records"):
    max_v = max(df[value_col].max(), 1)
    rows = []
    for _, r in df.iterrows():
        width = float(r[value_col]) / max_v * 100
        rows.append(f"<tr><td>{r[label_col]}</td><td style='padding:0; min-width:160px;'><div style='position:relative;height:30px;display:flex;align-items:center;justify-content:center;background:white;'><div style='position:absolute;left:0;top:0;bottom:0;width:{width}%;background:linear-gradient(90deg,rgba(99,142,198,.58),rgba(99,142,198,.18));'></div><b style='position:relative;color:#10243a'>{r[value_col]}</b></div></td><td>{r.get('% of Total','')}</td></tr>")
    st.markdown("<style>.excel-table{border-collapse:collapse;width:100%;font-size:13px}.excel-table th{background:#326887;color:#fff;border:1px solid #2a5874;padding:8px;text-align:center}.excel-table td{border:1px solid #dfe8f1;padding:8px}.excel-table td:not(:first-child){text-align:center}</style><table class='excel-table'><thead><tr><th>Category</th><th>Records</th><th>% of Total</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>", unsafe_allow_html=True)


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


def add_entry_form(df):
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
            row = {"Customer": customer, "Event type": event_type, "Issue Type": issue_type, "Event/Bulletin Title": title, "Reason": reason, "Root Cause": root, "Severity": severity, "RCA Requested": rca, "Standard Automation Focus": focus, "Comments": comments}
            st.success("Candidate row prepared. Review before adding to the source tracker.")
            st.json(row)

uploaded = st.sidebar.file_uploader("Upload EventWatch workbook", type=["xlsx"])
df = load_data(uploaded)
st.sidebar.title(APP_TITLE)
page = st.sidebar.radio("Pages", ["Executive Summary", "SOURCE 01 · Monthly trend", "SOURCE 02 · Fix status", "SOURCE 03 · Severity", "SOURCE 04 · Root cause", "SOURCE 05 · Top customers", "SOURCE 06 · Automation focus", "DETAIL · Event workload", "Automation urgency", "Dynamic Source Discovery", "Definitions", "Complaint Tracker"])
if df.empty:
    st.stop()
filtered = apply_filters(df)
complaints = df[df["Issue Type"].eq("Complaint")] if "Issue Type" in df.columns else df
inquiries = df[df["Issue Type"].eq("Inquiry")] if "Issue Type" in df.columns else df.iloc[0:0]

if page == "Executive Summary":
    st.markdown("<div class='excel-card'><h1>Executive Summary</h1><p>Executive-ready complaint monitoring view sourced from the approved workbook.</p></div>", unsafe_allow_html=True)
    c = st.columns(5)
    with c[0]: metric_card("Total records", len(df), f"{len(complaints)} complaints · {len(inquiries)} inquiries")
    with c[1]: metric_card("RCA requested", int((df.get("RCA Requested") == "Yes").sum()) if "RCA Requested" in df else 0)
    with c[2]: metric_card("High severity", int((df.get("Severity") == "High").sum()) if "Severity" in df else 0)
    with c[3]: metric_card("Customers", df["Customer"].nunique() if "Customer" in df else 0)
    with c[4]: metric_card("Automation categories", df["Standard Automation Focus"].nunique() if "Standard Automation Focus" in df else 0)
    if "Event type" in complaints:
        st.info(f"Top complaint event type: {complaints['Event type'].value_counts().idxmax()} ({complaints['Event type'].value_counts().max()} complaints).")
    if "Standard Automation Focus" in complaints:
        st.info(f"Top automation focus: {complaints['Standard Automation Focus'].value_counts().idxmax()} ({complaints['Standard Automation Focus'].value_counts().max()} complaints).")
elif page == "SOURCE 01 · Monthly trend":
    st.header(page)
    monthly = df.groupby("Month Label", dropna=False)["Issue Type"].value_counts().unstack(fill_value=0).reset_index()
    st.dataframe(monthly, use_container_width=True, hide_index=True)
    fig = px.bar(monthly, x="Month Label", y=[c for c in ["Complaint", "Inquiry"] if c in monthly.columns], barmode="group", text_auto=True)
    fig.update_layout(plot_bgcolor="white", paper_bgcolor="white", margin=dict(l=10,r=10,t=30,b=10))
    st.plotly_chart(fig, use_container_width=True)
elif page == "SOURCE 02 · Fix status":
    st.header(page); t = count_table(df, "Short Term Fix Status"); excel_bar_table(t, "Short Term Fix Status"); bar_chart(t, "Short Term Fix Status")
elif page == "SOURCE 03 · Severity":
    st.header(page); t = count_table(df, "Severity"); excel_bar_table(t, "Severity"); bar_chart(t, "Severity")
elif page == "SOURCE 04 · Root cause":
    st.header(page); t = count_table(df, "Root Cause"); excel_bar_table(t, "Root Cause"); bar_chart(t, "Root Cause")
elif page == "SOURCE 05 · Top customers":
    st.header(page); t = count_table(df, "Customer").head(15); excel_bar_table(t, "Customer"); bar_chart(t, "Customer")
elif page == "SOURCE 06 · Automation focus":
    st.header(page); t = count_table(complaints, "Standard Automation Focus", pct_base=max(len(complaints),1)); excel_bar_table(t, "Standard Automation Focus"); bar_chart(t, "Standard Automation Focus")
elif page == "DETAIL · Event workload":
    st.header(page); t = count_table(complaints, "Event type", pct_base=max(len(complaints),1)); excel_bar_table(t, "Event type"); bar_chart(t, "Event type")
elif page == "Automation urgency":
    st.header(page); t = count_table(complaints, "Standard Automation Focus", pct_base=max(len(complaints),1)); t.insert(0, "Priority", range(1, len(t)+1)); st.dataframe(t, use_container_width=True, hide_index=True)
elif page == "Dynamic Source Discovery":
    st.header(page)
    st.markdown("Dynamic Source Discovery covers misses caused by source coverage, feed ingestion, keyword detection, vendor monitoring, or article discovery gaps.")
    if "Standard Automation Focus" in df.columns:
        st.dataframe(df[df["Standard Automation Focus"].eq("Dynamic Source Discovery")], use_container_width=True, hide_index=True)
elif page == "Definitions":
    st.header(page)
    st.table(pd.DataFrame([["Complaint", "Confirmed EventWatch service miss, delay, missing/duplicate WarRoom, visibility failure, incorrect handling, or RCA-driven service concern."], ["Inquiry", "Customer asks for clarification, methodology, coverage check, or supplier/site reasoning without confirmed service failure."], ["Dynamic Source Discovery", "Misses caused by source coverage, ingestion, keyword, vendor feed, or discovery gaps."]], columns=["Term", "Definition"]))
elif page == "Complaint Tracker":
    st.header(page)
    concise_cols = [c for c in ["Month Label", "Email/JIRA Date", "Customer", "Event type", "Event/Bulletin Title", "Issue Type", "Reason", "Root Cause", "Short Term Fix Status", "RCA Requested", "Severity", "Standard Automation Focus", "Comments"] if c in filtered.columns]
    st.download_button("Download customer tracker CSV", filtered.to_csv(index=False).encode(), "customer_tracker_filtered.csv", "text/csv")
    st.dataframe(filtered[concise_cols], use_container_width=True, hide_index=True, height=560)
    add_entry_form(df)
