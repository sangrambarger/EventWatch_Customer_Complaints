from __future__ import annotations

import html
import os
import re
import textwrap
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(page_title="EventWatch Executive Dashboard", layout="wide")

APP_TITLE = "EventWatch Executive Dashboard"
# Data file names, not locations. Where they are read from is resolved at runtime by
# data_sources() -- no owner, repo or branch is hardcoded anywhere in this file.
CSV_NAME = "customer_tracker.csv"
WORKBOOK_NAME = "EventWatch_Customer_Complaints_2026.xlsx"
APP_DIR = Path(__file__).resolve().parent

PAGES = [
    # All customer emails sits second on purpose: it is where the vocabulary every other
    # tab uses is defined, so a reader who stops on a category name anywhere else finds
    # its meaning one click away rather than at the bottom of a list of fifteen.
    "Executive Summary", "All customer emails",
    "Monthly trend", "Root cause", "Top customer complaints",
    "DETAIL · Event workload", "Dynamic Source Discovery",
]

DESCRIPTIONS = {
    "Executive Summary": "What customers sent in, how much of it we got wrong, why, who it hit, and whether it is moving.",
    "Monthly trend": "Month-by-month complaint and inquiry trend, sorted chronologically from January onward, with the missed-event rate that volume alone hides.",
    "Root cause": "People, Process, and Product themes with deeper drill-downs below the current summary.",
    "Top customer complaints": "Customers with the highest complaint or inquiry volume and the reasons behind those records.",
    "DETAIL · Event workload": "Event types that repeatedly drive complaints, inquiries, or operational workload.",
    "Dynamic Source Discovery": "Source coverage, feed, keyword, vendor monitoring, and event-discovery gaps.",
    "All customer emails": "Every complaint and inquiry a customer sent in, with the category behind each one, downloads, and controlled manual-entry staging.",
}

CSS = """
<style>
:root{--bg:#0f1115;--panel:#1b1f26;--panel2:#202631;--ink:#f3f4f6;--muted:#b6beca;--line:#3a414d;--line2:#515a68;--blue:#8ab4f8;--teal:#80cbc4;--amber:#f6c177;--red:#f28b82;--green:#a8dab5}
html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--bg)!important;color:var(--ink)!important}.main .block-container{padding-top:.75rem;max-width:1450px;background:var(--bg)!important}[data-testid="stHeader"],[data-testid="stToolbar"]{background:#0c0e12!important}[data-testid="stSidebar"]{background:var(--bg)!important;border-right:1px solid var(--line)}[data-testid="stSidebar"] *{color:var(--ink)!important}[data-testid="stSidebar"] label{color:var(--muted)!important}
[data-testid="stSidebar"] div[role="radiogroup"]{gap:0!important;margin-top:4px}[data-testid="stSidebar"] label[data-testid="stRadioOption"]{width:100%;box-sizing:border-box;background:transparent!important;border:0!important;border-left:3px solid color-mix(in srgb,var(--nav,var(--blue)) 42%,transparent)!important;border-radius:0!important;padding:11px 16px!important;margin:0!important;display:flex!important;align-items:center!important;box-shadow:none!important;cursor:pointer;transition:background .12s ease,border-left-color .12s ease}[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover{background:color-mix(in srgb,var(--nav,var(--blue)) 9%,transparent)!important;border-left-color:var(--nav,var(--blue))!important}[data-testid="stSidebar"] label[data-testid="stRadioOption"] p{font-size:13.5px!important;font-weight:500!important;color:var(--muted)!important;margin:0!important;line-height:1.3}[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"]{border-left-color:var(--nav,var(--blue))!important;background:color-mix(in srgb,var(--nav,var(--blue)) 15%,transparent)!important}[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p{color:#fff!important;font-weight:700!important}[data-testid="stSidebar"] label[data-testid="stRadioOption"] div:has(+[data-testid="stMarkdownContainer"]){display:none!important}[data-testid="stSidebar"] label[data-testid="stRadioOption"] input{display:none!important}
h1,h2,h3,h4,h5,h6,p,span,div,label{color:var(--ink)!important}.page-hero,.section-card,.kpi,.insight-box,.excel-table.wide{width:auto;min-width:100%}.excel-table.wide td,.excel-table.wide th{white-space:nowrap}.excel-table.wide td:first-child{overflow-wrap:normal}.excel-table.wide td.wrap,.excel-table.wide th.wrap{white-space:normal;overflow-wrap:anywhere;text-align:left;min-width:280px;max-width:520px;vertical-align:top}.excel-table.record td{text-align:left;overflow-wrap:anywhere;white-space:normal}.excel-table.record td:first-child{width:220px;color:var(--muted)!important;font-weight:700}.definition-group{background:var(--panel)!important;border:1px solid var(--line);box-shadow:0 2px 8px rgba(0,0,0,.28)}.page-hero{position:relative;overflow:hidden;border-left:5px solid var(--accent,var(--blue));padding:14px 18px;margin-bottom:16px}.page-hero:after{content:"";position:absolute;inset:0;background:linear-gradient(120deg,rgba(255,255,255,.05),transparent 55%);pointer-events:none}.page-kicker{display:flex;align-items:center;gap:7px;font-size:11px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:var(--accent,var(--blue))!important;margin-bottom:5px}.page-kicker .dot{width:7px;height:7px;border-radius:50%;background:var(--accent,var(--blue));box-shadow:0 0 0 3px color-mix(in srgb,var(--accent,var(--blue)) 25%,transparent)}.page-hero h1{margin:0 0 4px 0;font-size:25px}.page-hero p,.section-card p{margin:0;color:var(--muted)!important;font-size:14px;line-height:1.4}.section-card{border-left:4px solid var(--accent,var(--blue));border-radius:8px;padding:12px 14px;margin:18px 0 10px;display:flex;flex-direction:column;gap:2px}.section-card h3{margin:0 0 2px 0;font-size:20px;display:flex;align-items:center;gap:8px}.section-card h3:before{content:"";width:9px;height:9px;border-radius:3px;background:var(--accent,var(--blue));display:inline-block;flex:none}.kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(145px,1fr));gap:10px;margin:10px 0 14px}.kpi{position:relative;min-height:92px;border-top:4px solid var(--accent);border-radius:8px;padding:11px 13px;transition:transform .15s ease,box-shadow .15s ease}.kpi:hover{transform:translateY(-3px);box-shadow:0 10px 22px rgba(0,0,0,.4)}.kpi-label{font-size:11px;color:var(--muted)!important;font-weight:800;text-transform:uppercase;letter-spacing:.04em}.kpi-num{font-size:29px;font-weight:900;line-height:1.05;margin:6px 0 4px;background:linear-gradient(180deg,#fff,var(--ink));-webkit-background-clip:text;background-clip:text}.kpi-foot{font-size:12px;color:var(--muted)!important}.section-rule{height:1px;background:var(--line);margin:30px 0 14px}
.root-card{background:var(--panel)!important;border:1px solid var(--line);border-top:5px solid var(--accent);border-radius:10px;padding:14px 16px;box-shadow:0 2px 10px rgba(0,0,0,.3);min-height:150px}.root-card .rc-name{font-size:12px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;color:var(--accent)!important}.root-card .rc-num{font-size:42px;font-weight:900;line-height:1.02;margin:8px 0 0}.root-card .rc-base{font-size:13px;color:var(--muted)!important;font-weight:700}.root-card .rc-share{display:inline-block;margin-top:8px;font-size:15px;font-weight:900;color:var(--accent)!important}.root-card .rc-desc{font-size:13px;color:var(--muted)!important;margin-top:8px;line-height:1.35}
.takeaway{border-left:4px solid var(--accent,var(--blue));background:var(--panel)!important;border-radius:8px;padding:13px 15px;margin:14px 0 4px;font-size:15px;line-height:1.45}.takeaway b{color:var(--accent,var(--blue))!important}
.donut-pair{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.insight-row{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:10px}.insight-box{border-left:4px solid var(--accent);border-radius:8px;padding:11px 12px;font-size:14px}
.table-wrap{overflow-x:auto;border-radius:8px;border:1px solid var(--line);box-shadow:0 2px 8px rgba(0,0,0,.22)}.excel-table{width:100%;border-collapse:collapse;background:var(--panel)!important;font-size:13px}.excel-table th{background:#2d3542!important;color:#fff!important;border:1px solid var(--line2);padding:9px 10px;text-align:center;font-weight:800;font-size:12px;text-transform:uppercase;letter-spacing:.03em;position:sticky;top:0}.excel-table td{border:1px solid var(--line);padding:8px 10px;background:#1f242d!important;color:var(--ink)!important;font-size:13px}.excel-table tr:nth-child(even) td{background:#242a34!important}.excel-table tbody tr{transition:background .1s ease}.excel-table tbody tr:hover td{background:#2c3542!important}.excel-table td:first-child{text-align:left;overflow-wrap:anywhere;font-weight:600}.excel-table td:not(:first-child){text-align:center}.bar-cell{padding:0!important}.bar-box{position:relative;min-height:32px;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:4px}.bar-box:before{content:"";position:absolute;inset:0 auto 0 0;width:var(--w);background:linear-gradient(90deg,rgba(138,180,248,.7),rgba(138,180,248,.18))}.bar-box span{position:relative;z-index:1;font-weight:900;color:#fff!important;text-shadow:0 1px 2px #000}.definition-group{border-left:4px solid var(--teal);border-radius:8px;padding:12px 14px;margin:12px 0}.stDownloadButton button,.stButton button,.stFormSubmitButton button{background:#374151!important;color:#fff!important;border:1px solid var(--blue)!important;border-radius:7px!important;font-weight:800!important;transition:border-color .15s ease,transform .1s ease}.stDownloadButton button:hover,.stButton button:hover,.stFormSubmitButton button:hover{border-color:var(--teal)!important;transform:translateY(-1px)}[data-testid="stDataFrame"],[data-testid="stTable"]{background:var(--panel)!important;border:1px solid var(--line)!important;border-radius:8px!important;overflow:hidden}
/* The Complaint Tracker's reading grid. It is `.wide` plus a restyle, so the sideways
   scroll and the bounded wrap columns still come from there. A full box grid, centred
   text and zebra fills read as a spreadsheet export rather than a table someone is meant
   to read: with rows of very unequal height -- one wrapped Comments cell can be five
   lines against a neighbour's one -- the vertical rules draw ragged columns and the
   alternating fills emphasise the raggedness. Hairline row separators and a hover band
   carry the row instead. Cells align top so a short value sits beside the first line of
   a long one rather than floating in the middle of it, and the first column is sticky so
   the month stays on screen through twenty-six columns of sideways scroll. */
.excel-table.grid{border-collapse:separate;border-spacing:0;background:transparent!important}
.excel-table.grid th{background:#161a21!important;border:0;border-bottom:1px solid var(--line2);padding:11px 15px;text-align:left;font-size:10.5px;letter-spacing:.075em;color:var(--muted)!important;font-weight:800}
.excel-table.grid td{--cell-bg:#0f1115;border:0;border-bottom:1px solid rgba(58,65,77,.5);padding:11px 15px;background:transparent!important;text-align:left;vertical-align:top;line-height:1.5}
.excel-table.grid tr:nth-child(even) td{background:transparent!important}
.excel-table.grid tbody tr:hover td{--cell-bg:#181d27;background:rgba(138,180,248,.06)!important}
.excel-table.grid tbody tr:last-child td{border-bottom:0}
.excel-table.grid th:first-child,.excel-table.grid td:first-child{position:sticky;left:0;z-index:2;background:#161a21!important;border-right:1px solid var(--line);white-space:nowrap;font-weight:700}
.excel-table.grid td:first-child.wrapcol,.excel-table.grid th:first-child.wrapcol{white-space:normal;min-width:140px;max-width:170px}
.excel-table.grid th:first-child{z-index:4}
.excel-table.grid tbody tr:hover td:first-child{background:#1d232c!important}
.excel-table.grid td.num{font-variant-numeric:tabular-nums;color:var(--muted)!important}
.excel-table.grid td.key{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;letter-spacing:-.01em}
.excel-table.grid td.wrap{min-width:320px;max-width:600px;color:var(--muted)!important}
.excel-table.grid td.wrap.narrow,.excel-table.grid th.wrap.narrow{min-width:170px;max-width:200px}
.excel-table.grid td.wrap.mid,.excel-table.grid th.wrap.mid{min-width:220px;max-width:260px}
.excel-table.grid td.wrap.bullets{white-space:pre-line}
.excel-table.roomy td{padding:12px 14px;font-size:13.5px;line-height:1.5}.excel-table.roomy th{padding:11px 14px;font-size:11px;letter-spacing:.06em}.excel-table.roomy td:first-child{font-weight:700;font-size:14px;line-height:1.4;padding-right:18px}.excel-table.roomy td.wrap,.excel-table.roomy th.wrap{text-align:left;font-weight:400;color:var(--muted)!important}.excel-table.roomy td:not(:first-child):not(.wrap){font-variant-numeric:tabular-nums}.excel-table.wide.roomy td.wrap,.excel-table.wide.roomy th.wrap{min-width:340px;max-width:640px}.excel-table.wide.roomy td.wrap.tight,.excel-table.wide.roomy th.wrap.tight{min-width:150px;max-width:190px}.owner-pill{display:inline-flex;align-items:baseline;gap:5px;padding:2px 9px;margin:1px 4px 1px 0;border-radius:999px;font-size:11.5px;font-weight:800;letter-spacing:.02em;white-space:nowrap;background:color-mix(in srgb,var(--c) 15%,transparent);border:1px solid color-mix(in srgb,var(--c) 40%,transparent)}.excel-table td .owner-pill,.excel-table td .owner-pill b{color:var(--c)!important}.excel-table td .owner-pill b{font-weight:900;font-size:12.5px}.excel-table td.owners{text-align:left!important;white-space:normal}.excel-table tbody tr.total td{background:#1a202a!important;border-top:2px solid var(--line2);font-weight:800;color:var(--ink)!important}.excel-table.stickytotal tbody tr.total td{position:sticky;bottom:0;z-index:2;box-shadow:0 -2px 6px rgba(0,0,0,.45)}.excel-table tbody tr.total td .bar-box:before{opacity:.35}
.excel-table.grid tbody tr.total td{--cell-bg:#1a202a;background:#1a202a!important;border-top:2px solid var(--line2);border-bottom:0;font-weight:800;color:var(--ink)!important}
.excel-table.grid td.wrap>.cell{max-height:100px;overflow-y:auto;background:linear-gradient(var(--cell-bg) 32%,rgba(0,0,0,0)) top/100% 22px no-repeat local,linear-gradient(rgba(0,0,0,0),var(--cell-bg) 68%) bottom/100% 22px no-repeat local,radial-gradient(farthest-side at 50% 0,rgba(138,180,248,.42),rgba(0,0,0,0)) top/100% 11px no-repeat,radial-gradient(farthest-side at 50% 100%,rgba(138,180,248,.42),rgba(0,0,0,0)) bottom/100% 11px no-repeat}
.excel-table.grid td.wrap>.cell::-webkit-scrollbar{width:8px}
.excel-table.grid td.wrap>.cell::-webkit-scrollbar-thumb{background:var(--line2);border-radius:4px;border:2px solid transparent;background-clip:content-box}
.excel-table.grid td.wrap>.cell::-webkit-scrollbar-track{background:rgba(255,255,255,.04);border-radius:4px}
@media(max-width:1200px){.kpi-grid{grid-template-columns:repeat(2,minmax(180px,1fr))}.insight-row{grid-template-columns:1fr}}@media(max-width:760px){.kpi-grid{grid-template-columns:1fr}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# The fifteen pages fall into four jobs, and the job -- not the page -- is what a colour
# can usefully say. Fifteen hues would be confetti, and repeating a hue across unrelated
# pages claims a kinship that is not there; four groups give the eye landmarks in a long
# list while staying inside the app's own tokens. The index is derived from PAGES rather
# than written out, so reordering or renaming a page cannot leave a rule pointing at the
# wrong row.
NAV_GROUPS = {
    "Where you start": ("#8ab4f8", ("Executive Summary", "All customer emails")),
    "Why it happened": ("#f28b82", ("Monthly trend", "Root cause")),
    "Who it happened to": ("#f6c177", ("Top customer complaints", "DETAIL · Event workload")),
    "What we do about it": ("#80cbc4", ("Dynamic Source Discovery",)),
}
NAV_ACCENT = {page: colour for colour, names in NAV_GROUPS.values() for page in names}
NAV_CSS = "".join(
    f'[data-testid="stSidebar"] div[role="radiogroup"]>label:nth-of-type({i + 1})'
    f'{{--nav:{NAV_ACCENT.get(name, "#b6beca")}}}'
    for i, name in enumerate(PAGES))
st.markdown(f"<style>{NAV_CSS}</style>", unsafe_allow_html=True)


def read_csv_or_excel(src):
    src = str(src)
    if src.split("?")[0].lower().endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(src, sheet_name="Data"), "Excel workbook"
    return pd.read_csv(src), "CSV"


def get_secret(key, default=None):
    """Streamlit secret, else environment variable, else default."""
    try:
        value = st.secrets.get(key)
    except Exception:
        value = None
    return value if value else os.environ.get(key, default)


def data_sources():
    """Resolve where to read the tracker from, most explicit first.

    1. GITHUB_CSV_URL / GITHUB_WORKBOOK_URL - an explicit path or URL, wins outright.
    2. The files sitting next to app.py - Streamlit Cloud deploys the whole repo, so
       uploading the data files alongside the app is all that is needed. Also makes a
       local checkout work with zero configuration.
    3. A raw URL derived from GITHUB_REPO (owner/name) and optional GITHUB_BRANCH,
       for the case where the data lives in a different repo than the app.

    No owner, repo or branch is baked into this file, so the app follows whatever it
    is deployed alongside instead of pointing at one fixed fork.
    """
    sources: list[tuple[str, str]] = []
    for key, name in (("GITHUB_CSV_URL", CSV_NAME), ("GITHUB_WORKBOOK_URL", WORKBOOK_NAME)):
        explicit = get_secret(key)
        if explicit:
            sources.append((explicit, "configured"))
    for name in (CSV_NAME, WORKBOOK_NAME):
        local = APP_DIR / name
        if local.exists():
            sources.append((str(local), "this repo"))
    repo = get_secret("GITHUB_REPO")
    if repo:
        branch = get_secret("GITHUB_BRANCH", "main")
        base = f"https://raw.githubusercontent.com/{repo.strip('/')}/{branch}"
        sources += [(f"{base}/{CSV_NAME}", f"{repo}@{branch}"),
                    (f"{base}/{WORKBOOK_NAME}", f"{repo}@{branch}")]
    return sources


def load_data():
    sources = data_sources()
    if not sources:
        st.error(f"No data source found. Put {CSV_NAME} (or the workbook) next to app.py, "
                 f"or set GITHUB_CSV_URL, or set GITHUB_REPO.")
        return pd.DataFrame()
    errors = []
    for src, origin in sources:
        try:
            df, label = read_csv_or_excel(src)
            st.sidebar.success(f"{label} loaded from {origin}")
            # Say what was loaded, not just that something was. Without this there is no way
            # to tell a stale deploy from a chart that legitimately excludes a small customer.
            newest = pd.to_datetime(df.get("Email/JIRA Date"), errors="coerce").max() if len(df) else None
            stamp = f" · newest {newest:%d-%b-%Y}" if pd.notna(newest) else ""
            st.sidebar.caption(f"**{len(df)} customer emails**{stamp}")
            st.sidebar.caption("Workbook upload is disabled; data comes from the deployed files.")
            break
        except Exception as exc:
            errors.append(f"{src}: {exc}")
    else:
        st.error("Dashboard data could not be loaded from any configured source. "
                 "Uploading a workbook in the dashboard is intentionally disabled.")
        for err in errors: st.caption(err)
        return pd.DataFrame()
    if not df.empty and str(df.columns[0]).startswith("Unnamed"):
        df = df.drop(columns=df.columns[0])
    for c in ["Month", "Email/JIRA Date", "Reporting Month", "Resolution Date"]:
        if c in df.columns: df[c] = pd.to_datetime(df[c], errors="coerce")
    source = next((c for c in ["Reporting Month", "Month", "Email/JIRA Date"] if c in df.columns), None)
    if source and "Month Label" not in df.columns:
        df["Month Label"] = df[source].dt.strftime("%b %Y")
    return df


PAGE_KICKERS = {
    "Executive Summary": ("Overview", "#8ab4f8"),
    "Monthly trend": ("Chart source", "#80cbc4"),
    "Root cause": ("Chart source", "#80cbc4"),
    "Top customer complaints": ("Chart source", "#80cbc4"),
    "DETAIL · Event workload": ("Detail view", "#f6c177"),
    "Dynamic Source Discovery": ("Coverage gap", "#f6c177"),
    "All customer emails": ("The records", "#f28b82"),
}


def page_header(title):
    kicker, accent = PAGE_KICKERS.get(title, ("Dashboard", "#8ab4f8"))
    st.markdown(
        f"<div class='page-hero' style='--accent:{accent}'><div class='page-kicker'><span class='dot'></span>{kicker}</div>"
        f"<h1>{title}</h1><p>{DESCRIPTIONS.get(title,'')}</p></div>",
        unsafe_allow_html=True,
    )


def add_section(title, desc="", accent="#8ab4f8"):
    st.markdown(f"<div class='section-card' style='--accent:{accent}'><h3>{title}</h3><p>{desc}</p></div>", unsafe_allow_html=True)


def date_filter(df):
    """Filter the whole dashboard by the date each record was actually raised.

    One range in the sidebar, not fourteen. Every page used to own a private copy of
    this control, so narrowing Executive Summary to September and then opening Root cause
    showed the full year with no hint that the two disagreed -- a reader comparing the
    two pages was comparing different populations. The date now sits beside Customer and
    Severity, because it is the same kind of thing: one choice the whole dashboard obeys.

    `Email/JIRA Date` first, deliberately. This used to prefer `Reporting Month`, which
    holds the FIRST of the month on every single row -- so "2 Sep to 30 Sep" matched
    nothing at all while nine September records sat in the tracker, and the end-date box
    read 01-Sep while the newest record was the 14th. A filter that silently returns an
    empty page is worse than no filter: the reader concludes the data is broken.
    """
    date_col = next((c for c in ["Email/JIRA Date", "Month", "Reporting Month"] if c in df.columns), None)
    if df.empty or not date_col or df[date_col].dropna().empty:
        return df
    mn, mx = df[date_col].dropna().min().date(), df[date_col].dropna().max().date()
    # Streamlit ignores a widget's `value` once its key exists in session state, so these
    # boxes froze at whatever span the data had when they were first drawn. Records that
    # arrived afterwards -- a merge to main, a row staged on the Complaint Tracker --
    # then fell outside an end date nobody chose, and the dashboard went on showing the
    # old set while looking like a working filter. That is the same failure as the
    # `Reporting Month` bug above: the filter is silently wrong, so the reader concludes
    # the data is. Remember the span the widgets were built from and move a bound only
    # while it still sits on the old edge, so growth is followed and a range the reader
    # narrowed on purpose is left alone.
    span = st.session_state.get("date_span")
    if span != (mn, mx):
        for wkey, was, now in (("date_start", span[0] if span else None, mn),
                               ("date_end", span[1] if span else None, mx)):
            if wkey in st.session_state and st.session_state[wkey] == was:
                st.session_state[wkey] = now
        st.session_state["date_span"] = (mn, mx)
    st.sidebar.markdown("### Date range")
    # No min_value/max_value: clamping the picker to the data's own span meant you could
    # not select a date outside it -- including next month, to check nothing has landed
    # there yet. The defaults still open on the data's range.
    start = st.sidebar.date_input("Start date", mn, key="date_start")
    end = st.sidebar.date_input("End date", mx, key="date_end")
    if start > end:
        st.sidebar.warning("Start date is after end date — showing the full range.")
        return df
    out = df[(df[date_col].dt.date >= start) & (df[date_col].dt.date <= end)].copy()
    st.sidebar.caption(f"Filtering on **{date_col}**: **{len(out)}** of {len(df)} record(s) "
                       f"between {start:%d-%b-%Y} and {end:%d-%b-%Y}.")
    st.session_state["_filter_note"] = (len(out), len(df), date_col, start, end)
    return out


def filter_note():
    """Say on the page itself how many records survived the sidebar.

    The date control moved to the sidebar, and a reader who has scrolled into a page has
    no view of it. Without this an empty or thin page reads as broken data rather than as
    a filter choice -- which is exactly how the `Reporting Month` bug went unreported for
    months. Every page prints its own population, so the number is never more than one
    line away from the tables it explains.
    """
    note = st.session_state.get("_filter_note")
    if not note:
        return
    shown, total, date_col, start, end = note
    st.caption(f"Showing **{shown}** of {total} customer email(s) — {date_col} between "
               f"{start:%d-%b-%Y} and {end:%d-%b-%Y}, plus any sidebar filters.")
    if not shown:
        st.info("No customer emails match the current filters. Widen the date range in the "
                "sidebar, or clear a sidebar filter, to see data again.")


def customer_names(series):
    """Every individual account named in a Customer column, slashes split out.

    `Ford/GM` is one incident both companies raised, not a company called "Ford/GM".
    Listing it as its own option put three non-existent customers in the filter and left
    Penske unselectable, since its only record is the Penske/Ford row.
    """
    if series is None:
        return []
    names = set()
    for value in series.dropna().astype(str):
        names.update(part.strip() for part in value.split("/") if part.strip())
    return sorted(names)


def names_match(series, chosen):
    """Rows naming any of `chosen`. A row naming two selected accounts matches once.

    This is the rule `customer_exposure()` already uses for the Executive Summary tally,
    so filtering to Ford now returns the same 42 records the summary counts rather than
    the 37 an exact string match found.
    """
    wanted = set(chosen)
    return series.fillna("").astype(str).apply(
        lambda value: bool(wanted & {part.strip() for part in value.split("/")}))


# The filters name the same things the pages name, and nothing else.
#
# What went: `Severity`, `Short Term Fix Status` and `RCA Requested` filtered on fields
# no page shows any more -- a control that narrows a population by something invisible
# leaves a reader unable to explain their own numbers. `Routed To` is derived from
# `Root Cause` on every row, so it was the same filter twice under two names.
# `Standard Automation Focus` is how the Dynamic Source Discovery page selects itself,
# not a cut a reader makes. And the raw `Reason` dropdown listed forty wordings for
# seven real things, so no one could use it.
#
# What arrived: the two derived vocabularies the pages are written in (the reason
# category and the plain sub-type), and `Confirmed miss` -- the field every headline
# number on the dashboard keys on, which had no filter at all.
#
# (label, kind, column). `kind` says how the values are read and matched, because three
# of these are computed rather than stored.
FILTERS = [
    ("Customer", "customer", "Customer"),
    ("Event type", "direct", "Event type"),
    ("Complaint or inquiry", "direct", "Issue Type"),
    ("Confirmed miss", "direct", "Missed_Flag"),
    ("What they wrote about", "reason", "Reason"),
    ("What went wrong", "subtype", "Sub-type"),
    ("Who fixes it", "direct", "Root Cause"),
]
FILTER_KEYS = [f"filter_{label}" for label, _, _ in FILTERS]


def filter_values(frame, kind, col):
    """The options a filter offers, and the series it matches against.

    A derived filter has to offer the label the pages print, not the tracker value
    underneath it -- otherwise the sidebar speaks a vocabulary the reader has never
    seen on screen. Both come back together so the match cannot drift from the list.
    """
    if kind == "reason":
        keys = reason_category(frame)
    elif kind == "subtype":
        keys = frame[col].fillna("Blank").astype(str).str.strip().map(lambda v: plain(v, PLAIN_SUBTYPE))
    else:
        keys = frame[col].fillna("").astype(str).str.strip()
    return sorted(v for v in keys.unique() if v and v != "nan"), keys


def sidebar_filters(df):
    st.sidebar.markdown("---")
    out = date_filter(df)
    # The column filters and the search box collapse behind one control. They were
    # always open, which made the sidebar taller than any screen: the page list scrolled
    # out of sight below them and reaching a tab meant scrolling past ten dropdowns
    # nobody was using. The date range stays out here because it is the one control
    # that gets touched on every visit.
    active = sum(1 for k in FILTER_KEYS if st.session_state.get(k))
    label = f"Filters ({active} active)" if active else "Filters"
    with st.sidebar.expander(label, expanded=bool(active)):
        for name, kind, col in FILTERS:
            if col not in out.columns:
                continue
            if kind == "customer":
                # Customer is the one column whose cells can name more than one account.
                vals = customer_names(out[col])
                chosen = st.multiselect(name, vals, key=f"filter_{name}")
                if chosen:
                    out = out[names_match(out[col], chosen)]
                continue
            vals, keys = filter_values(out, kind, col)
            chosen = st.multiselect(name, vals, key=f"filter_{name}")
            if chosen:
                out = out[keys.isin(chosen)]
        q = st.text_input("Search all fields")
        if q:
            out = out[out.astype(str).apply(lambda r: r.str.contains(q, case=False, na=False).any(), axis=1)]
    return out


def split_by_issue(frame, keys, index):
    """Complaint and Inquiry counts per key, so a total never hides its make-up."""
    out = pd.DataFrame(index=index)
    if "Issue Type" not in frame.columns:
        return out
    issue = frame["Issue Type"].fillna("").astype(str).str.strip()
    # Spelled out, not pluralised by concatenation -- "Inquiry" + "s" is "Inquirys",
    # which silently never matched the column the callers look for.
    for value, column in (("Complaint", "Complaints"), ("Inquiry", "Inquiries")):
        out[column] = keys[issue == value].value_counts().reindex(index).fillna(0).astype(int)
    return out


def count_table(df, col, base=None):
    """One row per value: the complaint/inquiry split, the confirmed misses, the total.

    `Misses` is here rather than on each page's own table because every tab has to state
    the same three bases the Executive Summary states. A count column on its own does not
    say whether those emails were a failure: `Process Clarification` is 13 emails of which
    2 were misses and `Review` is 23 of which 21 were, and a table showing only 13 and 23
    ranks them the wrong way round. It is a clean partition of `Records`, so the Total row
    adds up and `audit_pages.py` reconciles it like any other column.
    """
    cols = [col, "Complaints", "Inquiries", "Misses", "Reported timely", "Records", "% of Total"]
    if df.empty or col not in df.columns: return pd.DataFrame(columns=cols)
    keys = df[col].fillna("Blank").astype(str)
    t = keys.value_counts().reset_index()
    t.columns = [col, "Records"]
    parts = split_by_issue(df, keys, pd.Index(t[col]))
    for name in ("Complaints", "Inquiries"):
        if name in parts.columns:
            t[name] = parts[name].values
    if "Missed_Flag" in df.columns:
        missed = keys[df["Missed_Flag"].astype(str).str.strip().eq("Yes")].value_counts()
        t["Misses"] = t[col].map(missed).fillna(0).astype(int)
        # The remainder, named. Every row of every count table on the dashboard used to
        # read "25 emails, 24 misses" and leave the reader to wonder what the 25th was.
        # Records = Misses + Reported timely, on every row, with nothing unaccounted for.
        t["Reported timely"] = t["Records"] - t["Misses"]
    denom = max(base or len(df), 1)
    t["% of Total"] = (t["Records"] / denom * 100).round(1).astype(str) + "%"
    return t[[c for c in cols if c in t.columns]]


def long_pair_table(df, first, second, base=None):
    if df.empty or first not in df.columns or second not in df.columns: return pd.DataFrame(columns=[first, second, "Records", "% of Total"])
    out = df.groupby([first, second], dropna=False).size().reset_index(name="Records")
    out[first], out[second] = out[first].fillna("Blank").astype(str), out[second].fillna("Blank").astype(str)
    denom = max(base or int(out["Records"].sum()), 1)
    out["% of Total"] = (out["Records"] / denom * 100).round(1).astype(str) + "%"
    return out.sort_values(["Records", first, second], ascending=[False, True, True])


def kpis(items, columns=None):
    """A row of cards, on one row. `columns` sizes the grid to the count.

    The default five-column grid is right for the KPI strips, which are always five
    cards. Everything else is a variable count, and both auto-fitting and assuming five
    get it wrong: auto-fit wrapped a five-card row to four-plus-one on any window
    narrower than about 1200px, and a fixed five leaves a hole when there are four.
    Passing the count keeps the row a row at any width the dashboard is read at.
    """
    cards = [f"<div class='kpi' style='--accent:{a}'><div class='kpi-label'>{esc(l)}</div><div class='kpi-num'>{esc(v)}</div><div class='kpi-foot'>{esc(f)}</div></div>" for l, v, f, a in items]
    style = f" style='grid-template-columns:repeat({columns},minmax(0,1fr))'" if columns else ""
    st.markdown(f"<div class='kpi-grid'{style}>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def esc(v):
    return html.escape(str(v)) if pd.notna(v) else ""


def excel_bar_table(df, label_col, value_col="Records", extras=None, label_head=None,
                    value_head="Total emails", height=None, total_row=True, variant=None,
                    totals=None, wrap=(), raw=(), classes=None, caption=None):
    """A ranked table whose last-but-one column is a bar drawn inside the cell.

    `extras` are the columns carried between the label and the bar; the default picks
    up the complaint/inquiry split wherever a table has it. `height` caps the table and
    scrolls it in place -- which is how a full list of every account stays on an
    executive page without either truncating it or costing thirty rows of scroll. It is
    a scroll box rather than a collapsed expander on purpose: a collapsed expander is
    laid out at zero height, so `innerText` reads empty and `audit_pages.py` stops
    reconciling every row it hides.

    `wrap` names the columns that hold a sentence rather than a value. Without it the
    `wide` variant sets `white-space:nowrap` on every cell, so a column of explanations
    pushed the table sideways off the panel and the reader scrolled horizontally to
    read a sentence -- the single worst thing on this page. A wrapped column is
    left-aligned and bounded, and the rest of the table keeps its one-line rows.

    `raw` names the columns whose value is already HTML and must not be escaped -- the
    owner pills, and nothing else. Everything a customer or an analyst typed goes
    through `esc()`; only strings this module builds itself may skip it.
    """
    if df.empty or label_col not in df.columns or value_col not in df.columns:
        st.info("No data available for this view."); return
    max_v = max(float(df[value_col].max()), 1)
    extra = [c for c in (extras if extras is not None
                         else ("Complaints", "Inquiries", "Misses", "Reported timely"))
             if c in df.columns]
    wrap = tuple(wrap); raw = tuple(raw); classes = classes or {}
    klass_of = {}
    for c in extra:
        names = (["wrap"] if c in wrap else []) + ([classes[c]] if c in classes else [])
        klass_of[c] = f" class='{' '.join(names)}'" if names else ""
    rows = []
    for _, r in df.iterrows():
        width = float(r[value_col]) / max_v * 100
        cells = "".join(f"<td{klass_of[c]}>{r[c] if c in raw else esc(r[c])}</td>" for c in extra)
        rows.append(f"<tr><td>{esc(r[label_col])}</td>{cells}"
                    f"<td class='bar-cell'><div class='bar-box' style='--w:{width:.1f}%'><span>{esc(r[value_col])}</span></div></td>"
                    f"<td>{esc(r.get('% of Total',''))}</td></tr>")
    if total_row and len(df):
        # Summed here rather than by a generic helper, because the share column is a
        # formatted string: "29.5%" cannot be added up after the fact, and the total of
        # a column of shares is 100% of whatever base the table was built from, not the
        # sum of the strings in it.
        #
        # `totals` overrides a column's sum with the true figure, for the one table whose
        # rows deliberately double-count: an email naming two accounts appears on both
        # their rows, so the columns add to more than the tracker holds. Adding the
        # column up there would print a total that contradicts every other number on the
        # page, which is exactly what a total row exists to prevent.
        def foot(col):
            if totals and col in totals:
                return int(totals[col])
            if pd.api.types.is_numeric_dtype(df[col]):
                return int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
            return None
        sums = "".join(f"<td{klass_of[c]}>{esc(v)}</td>" if (v := foot(c)) is not None
                       else f"<td{klass_of[c]}></td>" for c in extra)
        grand = foot(value_col)
        rows.append(f"<tr class='total'><td>Total</td>{sums}<td>{esc(grand)}</td>"
                    f"<td>{'100%' if '% of Total' in df.columns else ''}</td></tr>")
    heads = "".join(f"<th{klass_of[c]}>{esc(c)}</th>" for c in extra)
    box = f" style='max-height:{int(height)}px;overflow-y:auto'" if height else ""
    if height and total_row:
        variant = f"{variant} stickytotal" if variant else "stickytotal"
    klass = "excel-table" + (f" {variant}" if variant else "")
    st.markdown(f"<div class='table-wrap'{box}><table class='{klass}'><thead><tr>"
                f"<th>{esc(label_head or label_col)}</th>" + heads +
                f"<th>{esc(value_head)}</th><th>% of Total</th></tr></thead><tbody>" + "".join(rows) +
                "</tbody></table></div>", unsafe_allow_html=True)
    if caption:
        st.caption(caption)


def cell(v):
    """One display string per value.

    A date column read from the CSV arrives as a Timestamp, and str() on that prints
    "2026-01-09 00:00:00" -- a midnight time on every row of the tracker that means
    nothing and crowds the column. Whole floats lose their trailing ".0" for the same
    reason, and a missing value renders as empty rather than "nan".
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    # pd.NaT satisfies isinstance(v, datetime) as well as the Timestamp check above,
    # and strftime raises on it -- so both date branches have to guard, not just one.
    # Nothing rendered a date column containing blanks until Resolution Date arrived,
    # which is why this only surfaced now.
    if isinstance(v, (pd.Timestamp, datetime)):
        return "" if pd.isna(v) else v.strftime("%d-%b-%Y")
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    text = str(v)
    return "" if text in {"nan", "NaT", "None"} else text


def styled_table(df, max_rows=None, height=None, variant=None, wrap=(), styles=None,
                 total_row=False):
    """Render any dataframe as a clean bordered table matching the Excel dashboard's table style.

    `variant="wide"` is for a grid with more columns than fit the panel -- the tracker's
    eighteen. The default table is `width:100%`, which squeezes those columns until every
    multi-word cell wraps and the rows come out two and three lines tall; the wide variant
    sizes to its content and scrolls sideways instead, so each row is one line.
    `variant="record"` is the one-record card: two columns, left-aligned and wrapping,
    because centring a paragraph of Comments across half the page is unreadable.
    `variant="wide grid"` adds the Complaint Tracker's restyle on top of `wide`: hairline
    row separators instead of a full box grid, top-aligned cells and a sticky first column.
    `wrap` names the columns that may wrap inside a bounded width rather than being held
    to one line, so a long value is shown whole instead of cut. `styles` gives a column one
    more cell class -- `num` for tabular figures so dates line up down the column, `key` for
    the monospace Jira key.
    """
    if df is None or df.empty:
        st.info("No data available for this view."); return
    show = df.head(max_rows) if max_rows else df
    styles = styles or {}
    klasses = []
    for c in show.columns:
        names = (["wrap"] if c in wrap else []) + ([styles[c]] if c in styles else [])
        klasses.append(f" class='{' '.join(names)}'" if names else "")
    head = "".join(f"<th{k}>{esc(c)}</th>" for c, k in zip(show.columns, klasses))
    # A wrapped cell's text goes inside a div, because `max-height` on a `td` is advisory
    # -- the cell still grows to its content. The div is what the grid variant caps.
    wrapped = [c in wrap for c in show.columns]
    last = len(show) - 1
    mark = " class='total'"
    body = "".join(
        "<tr" + (mark if total_row and i == last else "") + ">" + "".join(
            f"<td{k}><div class='cell'>{esc(cell(v))}</div></td>" if w else f"<td{k}>{esc(cell(v))}</td>"
            for v, k, w in zip(row, klasses, wrapped)) + "</tr>"
        for i, row in enumerate(show.itertuples(index=False))
    )
    wrap_style = f" style='max-height:{height}px;overflow-y:auto'" if height else ""
    klass = f"excel-table {variant}" if variant else "excel-table"
    st.markdown(f"<div class='table-wrap'{wrap_style}><table class='{klass}'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>", unsafe_allow_html=True)
    if max_rows and len(df) > max_rows:
        st.caption(f"Showing {max_rows} of {len(df)} rows — use the download button below for the full set.")


# The Complaint Tracker's reading columns, in the order a reader scans them: when it
# happened, who raised it, what it was, how it was classified, where it stands. The eight
# left out are either derived (Month, Number of Customers, Month_Sort), near-constant
# (Improvement VS Bug is `Improvement` on 110 of 111 rows), or prose too long for a grid.
# Forty distinct `Reason` strings for about seven real things, and every page inherits
# the mess: "Missed Event", "Missed insolvency alert" and "WarRoom should have been
# created but was not" are one category written three ways, so no chart of Reason can
# rank anything. This maps every value in the tracker onto a reusable category.
#
# It is **derived, not stored**. `Reason` keeps the customer's own words -- "Turkish
# keyword miss", "Missing Automotive industry tag" -- because that wording is the record
# of what they actually wrote, and a category is a reading of it. Storing it would mean a
# 27th column, a rewritten Data sheet, a wider `ComplaintTracker` ref and three scripts
# changed, for something every page can compute in a millisecond.
#
# `validate.py`'s `reason_categories` fails if a Reason value in the tracker is missing
# from this map, so a new wording cannot quietly fall into an "Uncategorised" bucket and
# go unnoticed -- which is exactly how forty values accumulated in the first place.
REASON_CATEGORIES = {
    # An event we should have reported was not reported at all.
    "Missed Event": "Event missed",
    "Missed insolvency alert": "Event missed",
    "Missed insolvency event": "Event missed",
    "Missed alert / event not captured": "Event missed",
    "Missed WarRoom": "Event missed",
    "Missed WarRoom / No notification": "Event missed",
    "Missed Relevant Event": "Event missed",
    "Missed severe weather alert": "Event missed",
    "Missed / Delayed Event": "Event missed",
    "Missed + Delayed Reporting": "Event missed",
    "Missing Resilinc alert / insolvency not captured": "Event missed",
    "Missing EventWatch coverage / feeds not captured": "Event missed",
    "WarRoom should have been created but was not": "Event missed",
    "WarRoom not created despite nationwide disruption": "Event missed",
    "SEC notification not captured/provided on time": "Event missed",
    # We reported it, but after the customer had already heard.
    "Delayed Event": "Reported late",
    "Delayed WarRoom": "Reported late",
    "Delayed alert / WarRoom created late": "Reported late",
    "Delayed / Missing WarRoom": "Reported late",
    "Delay in creating separate WarRoom / delayed escalation": "Reported late",
    # We reported it; the classification on it was wrong.
    "Wrong Relevancy": "Classified wrongly",
    "Incorrect Action": "Classified wrongly",
    "Incorrect Industry selection": "Classified wrongly",
    "Missing Automotive industry tag (customer tracking missed it)": "Classified wrongly",
    "Geographic Misclassification": "Classified wrongly",
    "Severity / consolidation handling concern": "Classified wrongly",
    # Published, but the customer's own supplier was never linked to it.
    "Impacted Supplier Missing": "Supplier not included",
    "Supplier Impact Mapping Clarification": "Supplier not included",
    "Event not triggered / not notified": "Supplier not included",
    # Published and linked, but the customer could not see it on their portal.
    "WarRoom not visible in customer profile": "Published but not visible",
    "News dashboard visibility gap": "Published but not visible",
    # Published, linked and visible -- the customer's own profile filter excluded
    # Resilinc as a source, so nothing was hidden by us. Kept out of the category above
    # because that one is named for our failures, and one of four being a customer-side
    # setting would overstate it by a quarter.
    "WarRoom visibility affected by customer profile filters": "Published but not visible",
    # One event published twice.
    "Duplicate WarRooms": "Duplicate published",
    # A question about how coverage works, not a report of a failure.
    "Coverage Verification Request": "Question about coverage",
    "Geographic Coverage Clarification": "Question about coverage",
    "Monitoring Strategy RFI": "Question about coverage",
    "Customer Requested Verification": "Question about coverage",
    "Customer Terminology Preference": "Question about coverage",
    "WarRoom Timing/Trigger Criteria Clarification": "Question about coverage",
    "Intelligence/Advisory Request": "Question about coverage",
}
# What each category means, in the words a reader who has never seen the tracker would
# need. These are read off the records, not invented, and each one says what happened
# rather than naming a field: "Supplier not included" is the Caterpillar case where the
# WarRoom existed and Dana Holding was left off its impacted list.
#
# `Hidden by the customer's own filter` was folded into `Published but not visible` on
# the owner's instruction. It was a category of its own so that a bucket named for our
# failures did not carry a customer-side setting; the owner's framing is that the bucket
# is "we published it correctly and the customer did not see it", and on that definition
# the reason the portal hid it -- our industry tag, a fault, or their own source
# preference -- does not change what happened to them. The cost of the fold is that the
# bucket now mixes our settings with theirs, so it can no longer be read as a pure
# measure of our failure. The meaning below says so.
CATEGORY_MEANING = {
    "Event missed": "We never reported it. The customer found out some other way.",
    "Reported late": "We reported it, but only after the customer had written to us. "
                     "It was captured and the bulletin was still being worked on.",
    "Question about coverage": "They asked how coverage works, or challenged a judgement. "
                               "No reporting failure was found in any of these.",
    "Classified wrongly": "We did report it, and got a field on it wrong \u2014 how relevant "
                          "it was, which industry, which geography, or how severe.",
    "Supplier not included": "The WarRoom existed, and their supplier was left off its "
                             "impacted list, so nothing reached them.",
    "Published but not visible": "We reported it correctly and it never appeared on their "
                                 "portal \u2014 an industry not selected, a fault, or their own "
                                 "source preference. The cause sits on either side.",
    "Duplicate published": "One event published twice, as two separate WarRooms.",
}


def category_table(df, total=True):
    """One row per category, carrying the customer wordings folded into it.

    The wordings column is the point: it turns the fold from something a reader has to
    trust into something they can check. Only the wordings present in the current filter
    are listed, most used first, so the column narrows with the date range rather than
    reciting all forty every time.
    """
    cols = ["Category", "What it means", "Their exact wordings",
            "Emails", "% of these", "Complaints", "Inquiries", "Misses"]
    if df.empty or "Reason" not in df.columns:
        return pd.DataFrame(columns=cols)
    frame = df.assign(_cat=reason_category(df))
    total = max(len(frame), 1)
    rows = []
    for name, group in frame.groupby("_cat"):
        wordings = group["Reason"].astype(str).str.strip().value_counts()
        missed = int((group.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip() == "Yes").sum())
        rows.append({
            "Category": name,
            "What it means": CATEGORY_MEANING.get(name, ""),
            "Their exact wordings": "\n".join(f"• {w} ({n})" for w, n in wordings.items()),
            "Emails": len(group),
            "% of these": f"{len(group) / total * 100:.0f}%",
            "Complaints": int((group.get("Issue Type", pd.Series(dtype=str)).astype(str) == "Complaint").sum()),
            "Inquiries": int((group.get("Issue Type", pd.Series(dtype=str)).astype(str) == "Inquiry").sum()),
            "Misses": f"{missed} ({missed / max(len(group), 1) * 100:.0f}%)",
        })
    out = pd.DataFrame(rows)[cols].sort_values("Emails", ascending=False).reset_index(drop=True)
    if total:
        # Built here rather than by a generic helper, because two of these columns are
        # formatted strings -- "62 (100%)" cannot be summed after the fact, only before.
        every = int((frame.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip() == "Yes").sum())
        out.loc[len(out)] = {
            "Category": "Total", "What it means": "", "Their exact wordings": "",
            "Emails": len(frame), "% of these": "100%",
            "Complaints": int((frame.get("Issue Type", pd.Series(dtype=str)).astype(str) == "Complaint").sum()),
            "Inquiries": int((frame.get("Issue Type", pd.Series(dtype=str)).astype(str) == "Inquiry").sum()),
            "Misses": f"{every} ({every / max(len(frame), 1) * 100:.0f}%)",
        }
    return out


UNCATEGORISED = "Uncategorised"


def reason_category(df):
    """The reusable category behind each email's `Reason`, as a Series."""
    if df.empty or "Reason" not in df.columns:
        return pd.Series(dtype=str, index=df.index)
    return (df["Reason"].fillna("").astype(str).str.strip()
            .map(lambda v: REASON_CATEGORIES.get(v, UNCATEGORISED)))


def with_failure_label(df):
    """Add the plain failure label beside the tracker Sub-type, for the record grid."""
    if df.empty or "Sub-type" not in df.columns:
        return df
    out = df.copy()
    out["What went wrong"] = out["Sub-type"].fillna("Blank").astype(str).str.strip().map(
        lambda v: plain(v, PLAIN_SUBTYPE))
    return out


def with_reason_category(df):
    """The frame with `Reason Category` inserted directly before `Reason`."""
    if df.empty or "Reason" not in df.columns or "Reason Category" in df.columns:
        return df
    out = df.copy()
    out.insert(out.columns.get_loc("Reason"), "Reason Category", reason_category(df))
    return out


TRACKER_COLUMNS = ["Month Label", "Email/JIRA Date", "Jira Key", "Customer", "Event type",
                   "Event/Bulletin Title", "Issue Type", "Reason Category", "Reason",
                   "Root Cause", "Sub-type", "What went wrong",
                   "Missed_Flag", "Short Term Fix Status", "Resolution Date", "RCA Requested",
                   "Severity", "Standard Automation Focus", "Routed To", "Comments"]

# Free-text columns, which wrap inside a bounded width in the grid rather than being cut.
# They were briefly truncated with an ellipsis, on the reasoning that the full text sat one
# click away in the record card. It does, but 68 of 114 Comments run past 110 characters,
# so nearly every row showed a sentence that stopped mid-thought and the column a reader
# most wants to read was the one least readable. Wrapping costs row height, which is the
# honest price of showing the whole value; `white-space:nowrap` still holds every other
# column to one line, so only these get tall.
# One extra cell class for the tracker grid: dates as tabular figures so they line up
# down the column, the Jira key monospaced so EAO-9 and EAO-48 read as the same shape.
# Column names a reader sees, where the tracker's own is a field name rather than words.
# `Missed_Flag` is the only one that really reads as a database column; the rest are
# already English and renaming them would only make the grid disagree with the CSV a
# reader downloads from the same page.
DISPLAY_NAMES = {"Missed_Flag": "Confirmed miss"}

GRID_STYLES = {"Email/JIRA Date": "num", "Resolution Date": "num", "Delay (Hours)": "num",
               "Month_Sort": "num", "Number of Customers": "num", "Jira Key": "key"}

WRAP_COLUMNS = ("Event/Bulletin Title", "Reason", "What went wrong", "Automation Opportunity",
                "Comments", "RCA Details")


def shorten(value, limit=110):
    """One line of a long field, cut on a word boundary so it does not end mid-word."""
    text = "" if pd.isna(value) else str(value).strip()
    if len(text) <= limit:
        return text
    head = text[:limit].rsplit(" ", 1)[0]
    return f"{head or text[:limit]}\u2026"


def record_labels(frame):
    """Labels for the record picker, mapped back to the index they came from.

    Date, key, customer and a trimmed title -- enough to find a specific record among a
    hundred without opening each one. Duplicates are numbered rather than deduplicated,
    because two genuinely similar records must both stay selectable.
    """
    labels, seen = {}, {}
    for idx, row in frame.iterrows():
        raised = row.get("Email/JIRA Date")
        stamp = raised.strftime("%d-%b-%Y") if pd.notna(raised) and hasattr(raised, "strftime") else "undated"
        key = str(row.get("Jira Key") or "").strip() or "no key"
        label = f"{stamp} · {key} · {row.get('Customer', '')} · {shorten(row.get('Event/Bulletin Title', ''), 70)}"
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            label = f"{label} ({seen[label]})"
        labels[label] = idx
    return labels


def chart(df, label_col, value_col="Records", title="", x_title="Records"):
    if df.empty or label_col not in df.columns or value_col not in df.columns:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}, {value_col}."); return None
    # When the table carries the complaint/inquiry split, stack it so the bar shows what
    # the total is made of rather than hiding it behind one number.
    parts = [c for c in ("Complaints", "Inquiries") if c in df.columns]
    keep = [label_col, value_col] + parts
    data = df[keep].dropna(subset=[label_col, value_col]).head(20).copy()
    if data.empty: st.info("No chartable records available for this view."); return None
    data[label_col] = data[label_col].astype(str)
    if parts:
        fig = px.bar(data, x=parts, y=label_col, orientation="h", text_auto=True, title=title,
                     color_discrete_map={"Complaints": "#8ab4f8", "Inquiries": "#f6c177"})
        fig.update_layout(barmode="stack", legend_title_text="",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    else:
        fig = px.bar(data, x=value_col, y=label_col, orientation="h", text=value_col, title=title, color_discrete_sequence=["#8ab4f8"])
    fig.update_yaxes(categoryorder="total ascending", tickfont=dict(size=13, color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title=x_title)
    fig.update_traces(opacity=.92, cliponaxis=False, marker_line_width=0)
    if not parts: fig.update_traces(textposition="outside")
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26", font=dict(color="#f3f4f6", size=13), margin=dict(l=20, r=60, t=64 if parts else 44, b=28), height=max(360, min(760, len(data) * 38 + 150)), showlegend=bool(parts))
    st.plotly_chart(fig, width="stretch")
    return fig


# The app's own CSS tokens, not new hues. Every chart on every page draws from --blue,
# --amber and --red, and a new page in a different set of blues reads as a different
# product even when each chart is individually fine; one palette across the dashboard
# beats a locally optimal one. BLUE_RAMP is --panel graded up to --blue, so the heatmap
# sits on the same surface the panels do.
#
# The pair that matters is still checked: --red against --blue scores CVD dE 17.0
# (protan) and 21.1 to normal vision through scripts/validate_palette.js, comfortably
# clear of the dE 8 floor. What is deliberately NOT used is the obvious red/green for
# rising and falling, which collapses to dE 3.6 under deuteranopia -- direction carries
# a signed label too, so it never rests on colour alone.
RED_BLUE = ("#f28b82", "#8ab4f8")           # --red, --blue
BLUE_RAMP = ["#1b1f26", "#24384f", "#2f5580", "#4e7bb8", "#8ab4f8"]   # --panel -> --blue


# Forty distinct `Reason` strings for what is really a handful of complaint kinds: the
# field carries the customer's own wording, and "Missed Event", "Missed insolvency
# alert" and "WarRoom should have been created but was not" are one complaint written
# three ways. Read straight, the Nature-of-complaints table splits the single biggest
# thing the tracker says across a dozen rows and puts a 4-record bankruptcy variant
# beside a 43-record general one as if they were different failures.
#
# This folds only labels whose WHOLE meaning is "an event we should have reported was
# not reported". The hybrids -- "Missed / Delayed Event", "Delayed / Missing WarRoom" --
# are deliberately left alone: they carry a timing signal as well, and flattening them
# would lose it. It is a display normalisation, not a data edit; the tracker keeps the
# customer's wording, because that wording is the record of what they actually said.
REASON_ALIASES = {
    "Missed insolvency alert": "Missed Event",
    "Missed insolvency event": "Missed Event",
    "Missing Resilinc alert / insolvency not captured": "Missed Event",
    "Missed alert / event not captured": "Missed Event",
    "Missed WarRoom": "Missed Event",
    "Missed WarRoom / No notification": "Missed Event",
    "Missed Relevant Event": "Missed Event",
    "Missed severe weather alert": "Missed Event",
    "Missing EventWatch coverage / feeds not captured": "Missed Event",
    "WarRoom should have been created but was not": "Missed Event",
    "WarRoom not created despite nationwide disruption": "Missed Event",
    "Event not triggered / not notified": "Missed Event",
    "SEC notification not captured/provided on time": "Missed Event",
}


def normalise_reason(df):
    """The frame with `Reason` folded onto its canonical label. Never written back."""
    if df.empty or "Reason" not in df.columns:
        return df
    reason = df["Reason"].fillna("Blank").astype(str).str.strip()
    return df.assign(Reason=reason.map(lambda v: REASON_ALIASES.get(v, v)))


# Why an event was missed, in the categories leadership actually asks about, plus the
# residue. Each bucket is a set of `Sub-type` values and optionally a set of `Root Cause`
# values, so the block is auditable against the tracker rather than being a hand-kept
# number on a slide.
#
# Analyst and model are two slices, not one. They were merged while the split was only a
# colour choice; they are not the same finding, because they have different owners. An
# item that reached a human reviewer and was not raised is EventWatch Ops' to fix; one
# the model did not identify is Product's. The taxonomy already separates them -- these
# are the same `Sub-type` values under a different `Root Cause` -- so merging them threw
# away the only part of the number that says who acts on it. Split, it reads 25 analyst
# against 13 model, which is a staffing conversation and a model conversation, not one
# undifferentiated 38.
#
# The last bucket is the honest part. The named categories do not cover the taxonomy --
# Mapping, Tagging, Visibility, Policy/Logic, Captured Late and WarRoom Creation are none
# of source, keyword, analyst or model, and neither is a Process-rooted Review -- and
# folding them into the analyst number to keep the picture tidy would overstate it by the
# size of the residue. It is shown as its own slice instead.
#
# Colour: Source and Keyword are one family in two steps of BLUE_RAMP, because both are
# "it never reached a person" and the eye should group them. Analyst and model take --red
# and --amber. --green is deliberately not used even though it measures clean against
# --red here (dE 9.7 deutan, 20.5 normal -- the dE 3.6 pair CLAUDE.md warns about is a
# saturated red/green, not these two tokens): every slice on this chart is a failure, and
# green would say one of them went well.
# Named in English rather than in the tracker's taxonomy, because these labels are read
# by people outside the team and "Source Miss" is not a phrase that tells anyone what
# happened. `audit_pages.py` recomputes them from the CSV under the same names, so a
# bucket renamed here without being renamed there fails the audit rather than quietly
# ceasing to be checked.
#
# These four are the ones where the OWNER changes the answer: the same sub-type reached
# a human on a People row and a model on a Product row, and merging them throws away the
# part of the number that says who acts on it. Every other missed email takes a bucket
# named after its own sub-type, generated in `miss_bucket_series()` -- there is no
# `Other`. A residue bucket is how eleven real failures (a supplier never linked, a
# WarRoom never created, a bulletin published but never shown) became one grey slice
# nobody could act on, and it also hides a sub-type added to the tracker tomorrow.
MISS_BUCKETS = (
    ("Source not in our vendor or monitoring network", ("Source Coverage",), (), "#8ab4f8",
     "The event never entered our system · Product"),
    ("Keyword Miss", ("Keyword Update",), (), "#4e7bb8",
     "A source we monitor carried it; no keyword matched · Product"),
    # These two are the only labels on the page that may name an actor, because the
    # owner is part of the rule that selects the rows rather than a property of the
    # sub-type: People on one, Product on the other.
    ("An analyst let it through", ("Review", "Event Identification", "Prioritization"), ("People",), "#f28b82",
     "An analyst saw this event and chose not to report it · EventWatch Ops"),
    ("The model did not spot it", ("Review", "Event Identification", "Prioritization"), ("Product",), "#f6c177",
     "The model had this event and did not flag it as reportable · Product"),
)
MISS_COLOURS = [c for _, _, _, c, _ in MISS_BUCKETS]


def miss_bucket_series(df):
    """The bucket each row falls in, or "" for a row that is not a missed event.

    One implementation, so the cards, the ring, the per-account table and the monthly
    split cannot disagree about which bucket a record belongs to. Buckets are applied in
    order and are mutually exclusive by construction: non-misses start out claimed so
    they can never take a bucket, and the last bucket has no sub-types, so it sweeps up
    whatever the others left and the slices always sum to the missed count however the
    taxonomy grows.
    """
    out = pd.Series("", index=df.index, dtype=object)
    if df.empty or not {"Missed_Flag", "Sub-type", "Root Cause"} <= set(df.columns):
        return out
    missed = df["Missed_Flag"].astype(str).str.strip().eq("Yes")
    sub = df["Sub-type"].fillna("Blank").astype(str).str.strip()
    root = df["Root Cause"].fillna("Blank").astype(str).str.strip()
    claimed = ~missed
    for label, subs, roots, _, _ in MISS_BUCKETS:
        hit = sub.isin(subs)
        if roots:
            hit = hit & root.isin(roots)
        hit = hit & ~claimed
        out[hit] = label
        claimed = claimed | hit
    # Everything the four named rules did not take keeps its own sub-type, in English.
    # `plain()` falls back to the raw value, so a sub-type added to the tracker tomorrow
    # appears under its own name rather than disappearing into a bucket.
    rest = ~claimed
    out[rest] = sub[rest].map(lambda v: plain(v, PLAIN_SUBTYPE))
    return out


def miss_categories(df):
    """Missed events split by what actually failed. Counts every missed record once.

    Colour here fails the dataviz normal-vision floor at five categorical slots -- the
    grey residue against --blue scores dE 9.5 -- which is legal only with secondary
    encoding, so every slice and every card carries its own label, count and share, and
    nothing on this block rests on colour alone. CVD separation passes at dE 8.5 worst
    all-pairs and 10.7 worst adjacent. Introducing a hue from outside the app's tokens to
    clear the remaining check would break the one-palette rule the rest of the dashboard
    keeps, which is the worse trade.
    """
    cols = ["Category", "Records", "% of Total"]
    buckets = miss_bucket_series(df)
    total = int((buckets != "").sum())
    if total == 0:
        return pd.DataFrame(columns=cols)
    counts = buckets[buckets != ""].value_counts()
    named = [label for label, *_ in MISS_BUCKETS]
    order = named + [k for k in counts.index if k not in named]
    out = pd.DataFrame({"Category": order})
    out["Records"] = [int(counts.get(label, 0)) for label in out["Category"]]
    out["_named"] = [0 if label in named else 1 for label in out["Category"]]
    out = (out[out["Records"] > 0]
           .sort_values(["Records", "_named"], ascending=[False, True])
           .drop(columns="_named").reset_index(drop=True))
    out["% of Total"] = (out["Records"] / total * 100).round(1).astype(str) + "%"
    return out


def miss_colours(df, table):
    """A colour per bucket: the four named ones keep theirs, the rest take their owner's.

    Eleven buckets is far past where categorical colour carries meaning, so colour here
    says *who fixes it* rather than trying to give every bucket its own hue. Each bar
    still carries its own name, count and share, so nothing rests on colour alone.
    """
    fixed = {label: colour for label, _, _, colour, _ in MISS_BUCKETS}
    buckets = miss_bucket_series(df)
    root = df.get("Root Cause", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    out = {}
    for label in table["Category"]:
        if label in fixed:
            out[label] = fixed[label]
            continue
        owners = root[buckets == label].value_counts()
        owner = str(owners.index[0]).strip() if len(owners) else ""
        out[label] = ROOT_COLOURS.get(owner, "#b6beca")
    return out


def root_recent_note(df, window=3, span=6, move=5.0):
    """One line naming the last `window` months' root-cause mix when the view is wider.

    The cards are cumulative over whatever the filter spans, and a cumulative mix buries
    a quarter in which the mix changed. It has: read over nine months the source bucket
    is a third of the misses, but over the last three it is first, and the model bucket
    falls to nothing. A reader taking the cumulative picture as "the picture" gets the
    wrong two priorities, which is exactly the misread this line exists to stop -- it is
    how a claim that source misses had not moved survived review, when 11 of the 20 had
    landed in the previous three months.

    Only shown when the frame spans more than `span` months, because below that the two
    windows are mostly the same emails and the line says nothing, and only for roots that
    moved `move` points or more -- listing all three would restate the cards.
    """
    if df.empty or "Email/JIRA Date" not in df.columns:
        return None
    months = pd.to_datetime(df["Email/JIRA Date"], errors="coerce").dt.to_period("M")
    order = sorted(m for m in months.dropna().unique())
    if len(order) <= span:
        return None
    recent = root_summary(df[months.isin(order[-window:])])
    overall = root_summary(df)
    if not recent or not overall:
        return None
    base = {root: share for root, _, share, _, _ in overall}
    moved = [(root, share, base.get(root, 0.0)) for root, _, share, _, _ in recent
             if abs(share - base.get(root, 0.0)) >= move]
    if not moved:
        return None
    total = sum(n for _, n, *_ in recent)
    label = lambda m: pd.Period(m, freq="M").strftime("%b %Y")
    parts = ", ".join(f"{root} {now:.0f}% (all months {was:.0f}%)" for root, now, was in moved)
    return (f"The cards are all {len(order)} months. Over the last {window} "
            f"({label(order[-window])}–{label(order[-1])}, {total} misses): {parts}.")


def inquiry_table(df):
    """Inquiries only: what they asked about, and what went back to them.

    An inquiry is one where the customer asked how something works rather than asserting
    we failed, and the test that settles it is what we did next: an explanation means
    inquiry, a bulletin or a correction means we were at fault and it is a complaint.
    That distinction is invisible on a table that counts complaints and inquiries in one
    column, so they get a table of their own.
    """
    cols = ["Category", "What they asked about", "Their exact wordings",
            "Inquiries", "% of these", "How we answered", "Was a real miss"]
    if df.empty or "Issue Type" not in df.columns:
        return pd.DataFrame(columns=cols)
    frame = df[df["Issue Type"].astype(str) == "Inquiry"].copy()
    if frame.empty:
        return pd.DataFrame(columns=cols)
    frame["_cat"] = reason_category(frame)
    total = len(frame)
    rows = []
    for name, group in frame.groupby("_cat"):
        wordings = group["Reason"].astype(str).str.strip().value_counts()
        answered = group.get("Short Term Fix Status", pd.Series(dtype=str)).astype(str).value_counts()
        missed = int((group.get("Missed_Flag", pd.Series(dtype=str)).astype(str) == "Yes").sum())
        rows.append({
            "Category": name,
            "What they asked about": CATEGORY_MEANING.get(name, ""),
            "Their exact wordings": "\n".join(f"• {w} ({n})" for w, n in wordings.items()),
            "Inquiries": len(group),
            "% of these": f"{len(group) / total * 100:.0f}%",
            "How we answered": "\n".join(f"• {k} ({n})" for k, n in answered.items()),
            "Was a real miss": missed,
        })
    out = pd.DataFrame(rows)[cols].sort_values("Inquiries", ascending=False).reset_index(drop=True)
    every = frame.get("Short Term Fix Status", pd.Series(dtype=str)).astype(str).value_counts()
    out.loc[len(out)] = {
        "Category": "Total", "What they asked about": "", "Their exact wordings": "",
        "Inquiries": total, "% of these": "100%",
        "How we answered": "\n".join(f"• {k} ({n})" for k, n in every.items()),
        "Was a real miss": int((frame.get("Missed_Flag", pd.Series(dtype=str)).astype(str) == "Yes").sum()),
    }
    return out


def donut(t, label_col="Category", value_col="Records", colours=None, centre="", title="",
          meanings=None):
    """Parts of one whole, labelled on the slice.

    A pie is usually the wrong answer, but this is the one shape it is right for: four
    mutually exclusive buckets that sum to a stated total, where the question is "which
    one is the biggest share of the misses". Labels sit outside the ring with the count
    and the share on them, so the ring is the shape and the text is the number.
    """
    if t is None or t.empty or value_col not in t.columns:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}.")
        return None
    total = int(t[value_col].sum())
    # Each slice explains itself on hover, wrapped before it reaches plotly -- plotly's
    # hover label neither wraps nor is clipped to the panel, so an unwrapped sentence
    # runs off both edges of a half-width column and loses its own ends.
    note = [("<br>".join(textwrap.wrap((meanings or {}).get(str(label), ""), 44)))
            for label in t[label_col]]
    fig = go.Figure(go.Pie(
        labels=list(t[label_col]), values=list(t[value_col]), hole=0.58, sort=False,
        direction="clockwise", marker=dict(colors=colours or MISS_COLOURS,
                                           line=dict(color="#1b1f26", width=2)),
        # One decimal on the share, like the table under it. Plotly's default gives two
        # significant figures, so a 3-miss slice printed 3.85% beside a table saying 3.8%.
        texttemplate="%{label}<br><b>%{percent:.1%}</b> · %{value}", textposition="outside",
        textfont=dict(size=13, color="#f3f4f6"), customdata=note,
        hovertemplate="<b>%{label}</b> — %{value} of " + str(total) +
                      ", %{percent:.1%}<br>%{customdata}<extra></extra>"))
    fig.update_layout(
        template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
        font=dict(color="#f3f4f6", size=13), showlegend=False, title=title,
        hoverlabel=dict(bgcolor="#11151b", align="left",
                        font=dict(color="#f3f4f6", size=12)),
        margin=dict(l=90, r=90, t=70 if title else 40, b=40), height=440,
        annotations=[dict(text=f"<b style='font-size:30px'>{total}</b><br>{centre}",
                          x=0.5, y=0.5, showarrow=False,
                          font=dict(size=13, color="#b6beca"))])
    st.plotly_chart(fig, width="stretch")
    return fig


def subtype_matrix(df):
    """Sub-type by Root Cause. The taxonomy calls Sub-type the category *beneath* Root
    Cause, but nothing ever showed the two together -- so the fact that the two biggest
    sub-types are a pure People failure and a pure Product failure was invisible."""
    if not {"Sub-type", "Root Cause"} <= set(df.columns) or df.empty:
        return pd.DataFrame()
    grid = pd.crosstab(df["Sub-type"].astype(str).str.strip().map(lambda v: plain(v, PLAIN_SUBTYPE)),
                       df["Root Cause"].astype(str).str.strip())
    grid.index.name = "Sub-type"
    if grid.empty:
        return grid
    return grid.loc[grid.sum(axis=1).sort_values(ascending=False).index]


def heatmap(grid, title=""):
    """A grid of magnitudes wants a heatmap, not sixteen coloured bars.

    Sixteen sub-types is far past the point where categorical colour stays readable, and
    a single sequential hue also shows the *sparsity* -- People and Product barely
    overlap -- which a ranked bar chart cannot say at all.
    """
    if grid is None or grid.empty:
        st.info("Chart cannot be rendered because required fields are missing: Sub-type, Root Cause.")
        return None
    fig = px.imshow(grid.values, x=list(grid.columns), y=list(grid.index),
                    color_continuous_scale=BLUE_RAMP, aspect="auto", text_auto=True, title=title)
    fig.update_traces(xgap=2, ygap=2,  # the 2px surface gap between fills
                      hovertemplate="%{y} · %{x}<br>%{z} record(s)<extra></extra>")
    fig.update_xaxes(side="top", tickfont=dict(size=13, color="#f3f4f6"), title="")
    fig.update_yaxes(tickfont=dict(size=12, color="#f3f4f6"), title="")
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=13), coloraxis_showscale=False,
                      margin=dict(l=20, r=30, t=70, b=30),
                      height=max(380, len(grid.index) * 32 + 150))
    st.plotly_chart(fig, width="stretch")
    return fig


def proportion_bar(frame, label_col, part_col, whole_col, part_name, rest_name, title=""):
    """A ratio per row, drawn to a common 100% width.

    These are ratios, not categories: a two-slice pie is the classic wrong answer and a
    grouped bar makes the reader divide. Rows share a baseline, so a glance ranks them.
    """
    if frame is None or frame.empty:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}.")
        return None
    data = frame.copy()
    data["_part"] = data[part_col] / data[whole_col] * 100
    data["_rest"] = 100 - data["_part"]
    part_hue, rest_hue = RED_BLUE
    fig = go.Figure()
    fig.add_trace(go.Bar(y=data[label_col], x=data["_part"], orientation="h", name=part_name,
                         marker=dict(color=part_hue, line=dict(width=2, color="#1b1f26")),
                         text=[f"{v:.0f}%" for v in data["_part"]], textposition="inside",
                         insidetextanchor="middle", textfont=dict(color="#1b1f26", size=12),
                         customdata=data[[part_col, whole_col]].values,
                         hovertemplate="%{y}<br>%{customdata[0]} of %{customdata[1]}<extra></extra>"))
    fig.add_trace(go.Bar(y=data[label_col], x=data["_rest"], orientation="h", name=rest_name,
                         marker=dict(color=rest_hue, line=dict(width=2, color="#1b1f26")),
                         hoverinfo="skip"))
    fig.update_xaxes(ticksuffix="%", range=[0, 100], tickfont=dict(size=12, color="#f3f4f6"),
                     gridcolor="#303846", title="")
    fig.update_yaxes(tickfont=dict(size=13, color="#f3f4f6"), title="")
    fig.update_layout(barmode="stack", template="plotly_dark", plot_bgcolor="#1b1f26",
                      paper_bgcolor="#1b1f26", font=dict(color="#f3f4f6", size=13), title=title,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), legend_title_text="",
                      margin=dict(l=20, r=40, t=70, b=30),
                      height=max(320, len(data) * 40 + 150))
    st.plotly_chart(fig, width="stretch")
    return fig


def missed_rate(df):
    """Missed-event rate per month. The count of complaints tracks how many tickets were
    raised; the share that were genuine misses is the part that says whether we improved."""
    dates = pd.to_datetime(df.get("Email/JIRA Date"), errors="coerce")
    flag = df.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes")
    g = pd.DataFrame({"Month": dates.dt.to_period("M").astype(str), "Missed": flag}).dropna(subset=["Month"])
    if g.empty: return pd.DataFrame(columns=["Month", "Records", "Missed", "Missed %"])
    out = g.groupby("Month").agg(Records=("Missed", "size"), Missed=("Missed", "sum")).reset_index()
    out["Missed %"] = (out["Missed"] / out["Records"] * 100).round(0)
    return out.sort_values("Month")


def _share(frame, col, value):
    return (frame[col].astype(str).str.strip().eq(value).mean() * 100) if len(frame) else 0.0


def missed_verdict(rate, window=3, noise=5.0):
    """Say in words whether the miss rate is coming down, in a sentence a director reads.

    A grid of monthly percentages does not answer "are we getting better", and the
    honest answer here is no -- nine months in, the rate has not moved. Stating that
    is the point of the KPI; leaving the reader to eyeball nine numbers is how it went
    unnoticed.

    Compared on POOLED counts, not the mean of monthly percentages: a month with four
    emails would otherwise carry the same weight as one with eighteen. A move smaller
    than `noise` points is reported as flat rather than dressed up as a trend, and the
    latest month is flagged when it is too thin to lean on -- these are 10-20 emails a
    month, and reading a trend into that noise is worse than reading none.
    """
    if len(rate) < window * 2:
        return None
    recent, prior = rate.tail(window), rate.iloc[-window * 2:-window]
    now = recent["Missed"].sum() / max(recent["Records"].sum(), 1) * 100
    was = prior["Missed"].sum() / max(prior["Records"].sum(), 1) * 100
    delta = now - was
    label = lambda m: pd.Period(m, freq="M").strftime("%b %Y")
    span = (f"{label(recent['Month'].iloc[0])}–{label(recent['Month'].iloc[-1])} "
            f"against {was:.0f}% in {label(prior['Month'].iloc[0])}–{label(prior['Month'].iloc[-1])}")
    # One decimal on the gap and on both rates. Rounded to whole points, a 4.5-point
    # move printed as "a 5-point move ... which is noise" against a 5-point threshold,
    # which reads as the sentence contradicting itself.
    if delta <= -noise:
        verdict, colour = "Improving", "#a8dab5"
        sentence = f"down {abs(delta):.1f} points"
    elif delta >= noise:
        verdict, colour = "Getting worse", "#f28b82"
        sentence = f"up {delta:.1f} points"
    else:
        verdict, colour = "Not improving", "#f6c177"
        sentence = f"a {abs(delta):.1f}-point move, which is noise at this volume"
    detail = (f"{now:.0f}% of customer emails were confirmed misses in {span} — {sentence}. "
              f"{int(recent['Missed'].sum())} of {int(recent['Records'].sum())} emails.")
    thin = rate.iloc[-1]
    if thin["Records"] < 8:
        detail += f" {label(thin['Month'])} has only {int(thin['Records'])} emails so far."
    return verdict, detail, colour, now


def customer_exposure(df, base=None):
    """Count a multi-customer row once for each customer named in it.

    `Ford/GM` is one incident but two affected accounts, and the Excel Dashboard's
    COUNTIFS matches the whole string, so a merged row drops out of both customers'
    totals and appears as its own category. This splits on the slash so "how many
    incidents touched Ford" has an answer. It deliberately differs from the canonical
    count above, which stays exact-match so the app and the workbook agree.
    """
    if df.empty or "Customer" not in df.columns:
        return pd.DataFrame(columns=["Customer", "Records", "% of Total"])
    exploded = (df.assign(_c=df["Customer"].fillna("Blank").astype(str).str.split("/"))
                  .explode("_c"))
    keys = exploded["_c"].str.strip().replace("", "Blank")
    t = keys.value_counts().reset_index()
    t.columns = ["Customer", "Records"]
    parts = split_by_issue(exploded, keys, pd.Index(t["Customer"]))
    for name in ("Complaints", "Inquiries"):
        if name in parts.columns:
            t[name] = parts[name].values
    denom = max(base or len(df), 1)
    t["% of Total"] = (t["Records"] / denom * 100).round(1).astype(str) + "%"
    return t[[c for c in ["Customer", "Complaints", "Inquiries", "Records", "% of Total"] if c in t.columns]]


TAGS = re.compile(r"<[^>]+>")


def downloads(df, name, fig=None):
    # The plotly toolbar hint used to print beside every download row, including the many
    # that sit under a table with no chart anywhere near them.
    c1, c2 = st.columns([1, 1]) if fig is not None else (st.container(), None)
    # The Owner column carries pill markup for the screen. A CSV full of "<span class=..."
    # is not a download anybody can open in Excel, so the tags come off on the way out
    # and the cell reads "Product 12 People 3".
    export = df.copy()
    for col in export.columns:
        if export[col].dtype == object:
            export[col] = export[col].map(
                lambda v: TAGS.sub(" ", v).strip() if isinstance(v, str) and "<" in v else v)
    c1.download_button("Download table CSV", export.to_csv(index=False).encode(), f"{name}.csv", "text/csv", key=f"csv_{name}")
    if fig is not None:
        c2.download_button("Download chart HTML", fig.to_html().encode(), f"{name}_chart.html", "text/html", key=f"chart_{name}")


def owner_accounts(root_df, page):
    """Which accounts this owner's failures actually land on, and what it costs them.

    This replaces a `long_pair_table(root_df, "Customer", "Reason")` dump, which printed
    one row per customer-and-wording pair -- forty wordings against thirty-three accounts,
    so the table was long, unranked, and said nothing the tables above it had not already
    said. The question a drill-down is for is "whose problem is this", and that needs the
    account's own base beside the count: 12 Product failures at Ford is a different fact
    from 12 at an account that only ever sent 12 emails.
    """
    cols = ["Customer", "Emails", "Misses", "Their total", "Share of theirs",
            "What went wrong most", "What they wrote about most"]
    if root_df.empty or "Customer" not in root_df.columns:
        return pd.DataFrame(columns=cols)
    rows = []
    for name in customer_names(root_df["Customer"]):
        here = root_df[names_match(root_df["Customer"], [name])]
        if here.empty:
            continue
        theirs = page[names_match(page["Customer"], [name])]
        sub = here["Sub-type"].fillna("").astype(str).str.strip()
        sub = sub[sub.ne("") & sub.ne("nan")]
        cat = reason_category(here)
        cat = cat[cat.ne("")]
        rows.append({
            "Customer": name,
            "Emails": len(here),
            "Misses": int(here.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes").sum()),
            "Their total": len(theirs),
            "Share of theirs": f"{len(here) / max(len(theirs), 1) * 100:.0f}%",
            "What went wrong most": plain(sub.value_counts().index[0], PLAIN_SUBTYPE) if not sub.empty else "",
            "What they wrote about most": cat.value_counts().index[0] if not cat.empty else "",
        })
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows).sort_values(["Emails", "Misses"],
                                          ascending=False).reset_index(drop=True)[cols]


def owner_insight(root, root_df, page):
    """One computed sentence naming this owner's biggest failure and worst account."""
    if root_df.empty:
        return ""
    miss = root_df.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes")
    sub = root_df["Sub-type"].fillna("").astype(str).str.strip()
    sub = sub[sub.ne("") & sub.ne("nan")]
    first = (f"<b>{esc(root)}</b> carries {plural(len(root_df), 'customer email')}, "
             f"{int(miss.sum())} of them confirmed misses")
    if not sub.empty:
        top = sub.value_counts()
        first += (f", and {int(top.iloc[0])} of those emails are "
                  f"<b>{esc(plain(top.index[0], PLAIN_SUBTYPE))}</b>")
    out = [first]
    accounts = owner_accounts(root_df, page)
    if not accounts.empty:
        worst = accounts.iloc[0]
        out.append(f"The account most exposed to it is <b>{esc(worst['Customer'])}</b> — "
                   f"{int(worst['Emails'])} of their "
                   f"{plural(int(worst['Their total']), 'email')} "
                   f"({worst['Share of theirs']})")
    return ". ".join(out) + "."


def render_owner_drilldown(root, root_df, page):
    """One owner's failures: what broke, what customers called it, and who it hit.

    Three tables **stacked full width**, not two squeezed into `st.columns(2)`. Side by
    side, a `count_table` with six numeric columns and a wrapped meaning column had about
    forty characters of width per column: every header wrapped to three lines and the
    meaning column was unreadable, which is the opposite of what a drill-down is for.

    Each table answers a different question, and none of them repeats another:
    what failed (the taxonomy), what the customer called it (their own words, folded),
    and which accounts carry it (with the account's own base beside the count).
    """
    colour = {"Product": "#8ab4f8", "People": "#f28b82"}.get(root, "#f6c177")
    add_section(f"{root} drill-down",
                f"Everything the tracker holds under {root}, in the order a reader needs it: "
                f"what actually failed, what the customer called it, and which accounts it "
                f"landed on. {ROOT_OWNERSHIP.get(root, '')} is the area that owns the fix.",
                colour)
    line = owner_insight(root, root_df, page)
    if line:
        st.markdown(f"<div class='takeaway' style='--accent:{colour}'>{line}</div>",
                    unsafe_allow_html=True)

    if "Sub-type" in root_df.columns:
        st.markdown(f"**What failed, under {root}**")
        failures = name_subtypes(count_table(root_df, "Sub-type"))
        excel_bar_table(failures, "Sub-type", label_head="Tracker value", value_head="Emails",
                        extras=["What it means", "Complaints", "Inquiries", "Misses",
                                "Reported timely"],
                        wrap=["What it means"], variant="wide roomy",
                        caption="Every row adds up: **Emails = Confirmed misses + Reported "
                                "timely.** Tracker value is the Sub-type on the record; "
                                "What it means is the same failure in the words the rest of "
                                "the dashboard uses.")
        downloads(failures, f"{root.lower()}_failures")

    if "Reason" in root_df.columns:
        st.markdown(f"**What customers wrote about, under {root}**")
        cats = nature_table(root_df)
        excel_bar_table(cats, "Category", label_head="What they wrote about",
                        value_head="Emails",
                        extras=["What it means", "Complaints", "Inquiries", "Misses",
                                "Reported timely"],
                        wrap=["What it means"], variant="wide roomy",
                        caption="The customer's own wording, folded onto the categories every "
                                "tab uses. It is not the same cut as the table above: that one "
                                "says what broke, this one says what they told us about it.")
        downloads(cats, f"{root.lower()}_categories")

    accounts = owner_accounts(root_df, page)
    if not accounts.empty:
        st.markdown(f"**Which accounts {root} failures land on**")
        excel_bar_table(accounts, "Customer", value_col="Emails",
                        extras=["Misses", "Their total", "Share of theirs",
                                "What went wrong most", "What they wrote about most"],
                        label_head="Customer", value_head=f"Emails under {root}",
                        # Both "most" columns hold a whole label -- without wrap the
                        # `wide` nowrap rule pushed this table 1350px into a 1138px
                        # panel and it scrolled sideways, which is the fault this page
                        # was being cleaned of.
                        wrap=["What went wrong most", "What they wrote about most"],
                        classes={"What went wrong most": "tight",
                                 "What they wrote about most": "tight"},
                        variant="wide roomy", height=380, total_row=False,
                        caption=f"Share of theirs is how much of that account's whole "
                                f"traffic sits under {root} — the number that says whether this "
                                f"is their main problem or a side issue. No Total row: an email "
                                f"naming two accounts is counted for both, so the column would "
                                f"add to more than the tracker holds.")
        downloads(accounts, f"{root.lower()}_accounts")


def account_failures(frame):
    """One account's failures at full granularity: owner, what went wrong, both bases.

    "Customer root-cause patterns" used to be Product / People / Process and nothing
    else, which names the team and not the problem -- "Ford: Product 34" tells a reader
    who to go and see and nothing about what to say when they get there. This keys on the
    (Root Cause, Sub-type) pair, so the owner is still there and the failure sits beside
    it in the words the rest of the dashboard uses.
    """
    cols = ["What went wrong", "Owner", "Emails", "Misses", "Reported timely", "% of Total"]
    if frame.empty or not {"Root Cause", "Sub-type"} <= set(frame.columns):
        return pd.DataFrame(columns=cols)
    work = pd.DataFrame({
        "What went wrong": frame["Sub-type"].fillna("Blank").astype(str).str.strip().map(
            lambda v: plain(v, PLAIN_SUBTYPE)),
        "_owner": frame["Root Cause"].fillna("Blank").astype(str).str.strip(),
        "_miss": frame.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes"),
    })
    rows = []
    for label, group in work.groupby("What went wrong"):
        misses = int(group["_miss"].sum())
        rows.append({"What went wrong": label,
                     "Owner": owner_pills(group["_owner"].value_counts()),
                     "Emails": len(group), "Misses": misses,
                     "Reported timely": len(group) - misses})
    out = pd.DataFrame(rows).sort_values(["Emails", "Misses"], ascending=False).reset_index(drop=True)
    out["% of Total"] = (out["Emails"] / max(int(out["Emails"].sum()), 1) * 100).round(1).astype(str) + "%"
    return out[cols]


def account_headline(name, frame, page):
    """What this account's numbers actually say, in one computed sentence."""
    if frame.empty:
        return ""
    miss = int(frame.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes").sum())
    rate = miss / max(len(frame), 1) * 100
    whole = len(page.get("Customer", pd.Series(dtype=str)))
    out = [f"<b>{esc(name)}</b> sent {plural(len(frame), 'email')} — "
           f"{len(frame) / max(whole, 1) * 100:.0f}% of everything in this filter — "
           f"and {miss} of them ({rate:.0f}%) were confirmed misses"]
    fails = account_failures(frame)
    second = ""
    if not fails.empty:
        top = fails.iloc[0]
        second = (f"Their biggest single failure is <b>{esc(top['What went wrong'])}</b>, "
                  f"{int(top['Emails'])} of their {len(frame)} emails")
    cats = reason_category(frame)
    cats = cats[cats.ne("")]
    if not cats.empty:
        top_cat = cats.value_counts()
        tail = (f"what they wrote about most is <b>{esc(top_cat.index[0])}</b> "
                f"({int(top_cat.iloc[0])})")
        second = f"{second}, and {tail}" if second else tail[0].upper() + tail[1:]
    if second:
        out.append(second)
    return ". ".join(out) + "."


def render_account_view(page):
    """One account at a time, chosen from a dropdown -- not every account in one list.

    The three tables this replaces were `long_pair_table` dumps: one row per
    customer-and-value pair, thirty-three accounts deep, unranked and ungrouped, so
    reading one account meant scanning past thirty-two others. A reader asking about an
    account wants that account. The selector narrows THIS block only; the tables above
    keep following the sidebar, so the two never silently disagree.
    """
    add_section("One account at a time", "Pick an account to see what it sent, what failed on "
                "it, and what its people actually wrote about. A record naming two accounts "
                "counts for both, the same way every other tab counts it.", "#a8dab5")
    options = customer_names(page.get("Customer"))
    if not options:
        st.info("No customer recorded in the current filter.")
        return
    # Default to the busiest account rather than the alphabetically first: an empty-looking
    # page on first load reads as a broken filter, and the busiest one is the question
    # this page is usually opened to answer.
    busiest = max(options, key=lambda n: int(names_match(page["Customer"], [n]).sum()))
    picked = st.selectbox("Account", options, index=options.index(busiest),
                          key="account_view_pick",
                          help="Applies to this section only. The tables above follow the sidebar.")
    frame = page[names_match(page["Customer"], [picked])]
    if frame.empty:
        st.info(f"No emails for {picked} in the current filter.")
        return
    issue = frame.get("Issue Type", pd.Series(dtype=str)).astype(str).str.strip()
    miss = int(frame.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes").sum())
    kpis([("Emails", len(frame), f"{int(issue.eq('Complaint').sum())} complaints · "
                                 f"{int(issue.eq('Inquiry').sum())} inquiries", "#8ab4f8"),
          ("Confirmed misses", f"{miss} of {len(frame)}",
           f"{miss / max(len(frame), 1) * 100:.0f}% of their emails", "#f28b82"),
          ("Reported timely", f"{len(frame) - miss} of {len(frame)}",
           "the event did reach them in time", "#80cbc4"),
          ("Share of this filter", f"{len(frame) / max(len(page), 1) * 100:.0f}%",
           f"of {plural(len(page), 'email')} on this page", "#f6c177")], columns=4)
    line = account_headline(picked, frame, page)
    if line:
        st.markdown(f"<div class='takeaway' style='--accent:#a8dab5'>{line}</div>",
                    unsafe_allow_html=True)

    st.markdown(f"**What went wrong for {picked}**")
    fails = account_failures(frame)
    if fails.empty:
        st.info("No root cause recorded on this account's emails.")
    else:
        f_fail = chart(fails.rename(columns={"Emails": "Records"}), "What went wrong",
                       title=f"{picked}: what failed", x_title="Customer emails")
        excel_bar_table(fails, "What went wrong", value_col="Emails",
                        extras=["Owner", "Misses", "Reported timely"],
                        label_head="What went wrong", value_head="Emails",
                        raw=["Owner"], classes={"Owner": "owners"}, variant="wide roomy",
                        caption="Owner is the team that fixes it; the failure beside it is what "
                                "actually broke. Every row adds up: **Emails = Misses + Reported "
                                "timely.**")
        downloads(fails, f"account_failures_{picked}", f_fail)

    left, right = st.columns(2)
    with left:
        st.markdown(f"**What {picked} wrote about**")
        cats = nature_table(frame)
        f_cat = chart(cats.rename(columns={"Records": "Records"}), "Category", title="",
                      x_title="Customer emails") if not cats.empty else None
    with right:
        st.markdown(f"**Which events {picked} raised**")
        types = count_table(frame, "Event type")
        f_type = chart(types, "Event type", title="", x_title="Customer emails") \
            if not types.empty else None
    if not cats.empty:
        excel_bar_table(cats, "Category", label_head="What they wrote about", value_head="Emails",
                        extras=["What it means", "Complaints", "Inquiries", "Misses",
                                "Reported timely"],
                        wrap=["What it means"], variant="wide roomy")
        downloads(cats, f"account_categories_{picked}", f_cat)
    if not types.empty:
        excel_bar_table(types, "Event type", label_head="Event type", value_head="Emails")
        downloads(types, f"account_event_types_{picked}", f_type)


def source_page(title, df, col, key, primary=None, summary=True):
    """`primary` overrides how the main table is counted -- Customer needs a counter that
    credits every account named in a multi-customer row, not the whole string.

    `summary=False` drops the generic count-table-and-chart pair at the top. Where a
    page now renders the Executive Summary's own block for the same dimension, that pair
    was the same numbers a second time in weaker words, and two tables of one thing on
    one page is exactly the repetition this dashboard is being cleaned of.
    """
    page_header(title); page = df; filter_note(); label = col.replace("Standard Automation Focus", "Automation focus")
    if summary:
        t = primary(page) if primary else count_table(page, col)
        note = (" A row naming two customers is counted for each of them, so one incident reported by two accounts "
                "adds to both tallies." if primary else "")
        add_section(f"{label} summary table", f"Every record the customer sent in -- complaints and inquiries both -- by {label.lower()}, with count and share of the current filter.{note}")
        excel_bar_table(t, col); downloads(t, key)
        add_section(f"{label} chart", f"Visual ranking of {label.lower()} categories so leaders can quickly see the biggest drivers.", "#80cbc4")
        fig = chart(t, col, title=f"{label} distribution"); downloads(t, f"{key}_chart_data", fig)
    if col == "Customer":
        if {"Customer", "Missed_Flag"} <= set(page.columns) and not page.empty:
            spread = page.assign(_c=page["Customer"].astype(str).str.split("/")).explode("_c")
            spread["_c"] = spread["_c"].str.strip()
            rate = spread.groupby("_c").agg(
                Records=("_c", "size"),
                Missed=("Missed_Flag", lambda x: int((x.astype(str).str.strip() == "Yes").sum()))
            ).reset_index().rename(columns={"_c": "Customer"})
            rate = rate[rate["Records"] >= 3].copy()
            rate["Missed %"] = (rate["Missed"] / rate["Records"] * 100).round(0)
            # Keep the twelve busiest accounts, then order by RATE: the bars share a
            # baseline so that ordering is the whole point, and sorting by raw count
            # left 100% rows sitting below 50% ones. Ascending, because a horizontal
            # bar draws its first row at the bottom.
            rate = rate.sort_values("Records", ascending=False).head(12).sort_values("Missed %")
            if not rate.empty:
                add_section("How often each customer is right", "The share of each account's records that "
                            "turned out to be a confirmed miss, on a common 100% width so the rows rank at "
                            "a glance. An account near the top is not raising noise -- every ticket it "
                            "sends is a real failure.", "#f28b82")
                pb = proportion_bar(rate, "Customer", "Missed", "Records",
                                    "Confirmed miss", "Not a miss", title="Confirmed misses as a share of each account's records")
                downloads(rate, "customer_miss_rate", pb)
        render_account_view(page)
    if col == "Root Cause":
        add_section("Sub-type by root cause", "Sub-type is the category beneath Root Cause in the "
                    "taxonomy, and until now nothing showed the two together. Darker means more "
                    "records. The shape matters as much as the counts: where a row is dark in one "
                    "column and empty in the others, that failure mode belongs to a single root "
                    "cause and has a single owner.", "#80cbc4")
        # A selector here rather than only in the sidebar: this is the question the page
        # is for -- "for Ford, how many were a source miss" -- and it should not depend on
        # knowing the sidebar exists. It narrows THIS block only; the drill-downs below
        # keep following the sidebar, so the two never silently disagree.
        options = ["All customers"] + customer_names(page.get("Customer"))
        picked = st.selectbox("Customer", options, key=f"{key}_subtype_customer",
                              help="Applies to this section only. A record naming two accounts "
                                   "counts for each of them.")
        focus = page if picked == "All customers" else page[names_match(page["Customer"], [picked])]
        if picked != "All customers":
            complaints = int(focus["Issue Type"].astype(str).eq("Complaint").sum()) if "Issue Type" in focus.columns else 0
            inquiries = int(focus["Issue Type"].astype(str).eq("Inquiry").sum()) if "Issue Type" in focus.columns else 0
            st.caption(f"**{picked}: {len(focus)} record(s)** — {complaints} complaint(s), "
                       f"{inquiries} inquiry(ies). Records naming {picked} alongside another account "
                       f"are included, which is how the Executive Summary counts them too.")
        grid = subtype_matrix(focus)
        if grid.empty:
            st.info(f"No records for {picked} in the current filter.")
        else:
            hm = heatmap(grid, title=f"Records by sub-type and root cause"
                                     f"{'' if picked == 'All customers' else ' — ' + picked}")
            # The grid's index is already the plain label, so nothing is translated here
            # a second time -- `plain()` falls back to the value itself, which would have
            # produced a column repeating its neighbour word for word.
            flat = grid.reset_index().rename(columns={"index": "Sub-type", "Sub-type": "What went wrong"})
            flat["Total"] = grid.sum(axis=1).values
            styled_table(flat); downloads(flat, "subtype_by_root_cause", hm)
        for root in ["Product", "People", "Process"]:
            root_df = page[page["Root Cause"].astype(str).eq(root)] if "Root Cause" in page.columns else page.iloc[0:0]
            if root_df.empty:
                continue
            render_owner_drilldown(root, root_df, page)


    return page

STAGED_FLAG = "_Staged"
# Fields the form fills from the tracker's own values, so a new entry can only use a
# term the Definitions sheet already defines. `enum_definitions` gates the workbook;
# this gates the app, and the two agree because both read the same column.
PICKLISTS = ["Customer", "Event type", "Reason", "Sub-type", "Standard Automation Focus"]
NEW_VALUE = "— add a new value —"


def taxonomy(df, column, extra=()):
    """Distinct values in use for a column, plus any fixed options that must appear."""
    values = set(extra)
    if column in df.columns:
        values |= {str(v).strip() for v in df[column].dropna() if str(v).strip()}
    return sorted(values)


def stage_entry(row):
    st.session_state.setdefault("staged", []).append(row)


def staged_frame(columns):
    rows = st.session_state.get("staged", [])
    if not rows:
        return pd.DataFrame(columns=list(columns) + [STAGED_FLAG])
    frame = pd.DataFrame(rows)
    for col in columns:
        if col not in frame.columns:
            frame[col] = pd.NA
    frame[STAGED_FLAG] = True
    return frame[list(columns) + [STAGED_FLAG]]


def apply_staged(df):
    """Append this session's staged entries to the loaded tracker.

    Everything downstream -- the sidebar filters, every count table, every chart, the
    Executive Summary cards -- derives from this one frame, so appending here is what
    makes an entry on the Complaint Tracker page show up on all fourteen pages at
    once. Nothing else needs to know staging exists.
    """
    df = df.copy()
    df[STAGED_FLAG] = False
    extra = staged_frame([c for c in df.columns if c != STAGED_FLAG])
    if extra.empty:
        return df
    out = pd.concat([df, extra], ignore_index=True)
    for col in ("Month", "Email/JIRA Date", "Reporting Month", "Resolution Date"):
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], errors="coerce")
    source = next((c for c in ["Reporting Month", "Month", "Email/JIRA Date"] if c in out.columns), None)
    if source and "Month Label" in out.columns:
        out["Month Label"] = out[source].dt.strftime("%b %Y")
    return out


def derive_row(row):
    """Fill the columns a complete tracker row carries but nobody should retype.

    `validate.py` requires ten fields and the Dashboard's COUNTIFS read several more.
    Deriving them here is what lets a staged row be pasted into the tracker and pass
    validate.py unedited, rather than becoming a row someone has to finish by hand.
    """
    date = pd.Timestamp(row["Email/JIRA Date"])
    row["Month"] = date.replace(day=1)
    row["Reporting Month"] = date.replace(day=1)
    row["Month Label"] = date.strftime("%b %Y")
    row["Month_Sort"] = date.month
    row["Number of Customers"] = len([p for p in str(row["Customer"]).split("/") if p.strip()])
    # Routing is derived from Root Cause and a human override is expected; see CLAUDE.md.
    row["Routed To"] = ("Product & Platform" if row.get("Root Cause") == "Product"
                        else "EventWatch Ops - Nitin Rindhe")
    return row


def manual_entry_form(df):
    source_cols = [c for c in df.columns if c != STAGED_FLAG]
    with st.expander("Add a customer email", expanded=False):
        st.caption("A saved entry is counted on every tab immediately -- cards, tables and "
                   "charts alike. It is held in this browser session only, not written to the "
                   "tracker: download the combined CSV below and commit it through the approved "
                   "update process to make it permanent.")
        with st.form("manual_entry_form"):
            c1, c2, c3 = st.columns(3)
            row = {"Email/JIRA Date": c1.date_input("Email/JIRA Date *"),
                   "Jira Key": c2.text_input("Jira Key (e.g. EAO-39)"),
                   "Issue Type": c3.selectbox("Issue Type *", ["Complaint", "Inquiry"])}
            c4, c5 = st.columns(2)
            row["Customer"] = c4.selectbox("Customer *", taxonomy(df, "Customer") + [NEW_VALUE])
            new_customer = c5.text_input("New customer (slash-separate two accounts: Eaton/Ford)")
            row["Event/Bulletin Title"] = st.text_input("Event/Bulletin Title *")

            c6, c7, c8 = st.columns(3)
            row["Event type"] = c6.selectbox("Event type *", taxonomy(df, "Event type"))
            row["Reason"] = c7.selectbox("Reason *", taxonomy(df, "Reason"))
            row["Sub-type"] = c8.selectbox("Sub-type", [""] + taxonomy(df, "Sub-type"))

            c9, c10, c11 = st.columns(3)
            row["Root Cause"] = c9.selectbox("Root Cause *", ["People", "Process", "Product"])
            row["Severity"] = c10.selectbox("Severity *", ["Medium", "High", "Low"])
            row["Standard Automation Focus"] = c11.selectbox(
                "Standard Automation Focus *", taxonomy(df, "Standard Automation Focus"))

            c12, c13, c14 = st.columns(3)
            row["Short Term Fix Status"] = c12.selectbox(
                "Short Term Fix Status", taxonomy(df, "Short Term Fix Status", ("Pending",)))
            row["RCA Requested"] = c13.selectbox("RCA Requested", ["No", "Yes"])
            row["Missed_Flag"] = c14.selectbox("Missed_Flag", ["No", "Yes"])

            c15, c16 = st.columns(2)
            row["Improvement VS Bug"] = c15.selectbox(
                "Improvement VS Bug", [""] + taxonomy(df, "Improvement VS Bug"))
            row["Delay"] = c16.text_input("Delay (free text, e.g. '2 days')")
            resolved = st.date_input("Resolution Date (leave as-is and tick below only if closed)",
                                     value=None, format="DD/MM/YYYY")
            row["Resolution Date"] = resolved
            row["Comments"] = st.text_area("Comments / evidence summary *")
            row["RCA Details"] = st.text_area(
                "RCA Details (leave blank where no RCA has been issued; do not paraphrase a PDF)")
            save = st.form_submit_button("Add entry to this session")

        if save:
            if row["Customer"] == NEW_VALUE:
                row["Customer"] = new_customer.strip()
            required = ["Customer", "Event/Bulletin Title", "Event type", "Reason",
                        "Root Cause", "Severity", "Standard Automation Focus", "Comments"]
            missing = [c for c in required if not str(row.get(c, "")).strip()]
            if row.get("Resolution Date") and row.get("Short Term Fix Status") == "Pending":
                missing.append("(a Pending record cannot have a Resolution Date)")
            if missing:
                st.error("Missing required fields: " + ", ".join(missing))
            else:
                stage_entry({k: v for k, v in derive_row(row).items() if k in source_cols or k == "Month Label"})
                st.success("Entry added. Every page now counts it. Download the combined CSV "
                           "below to make it permanent.")
                st.rerun()

    staged = st.session_state.get("staged", [])
    if not staged:
        return
    st.markdown("<div class='definition-group'><h3>Staged this session</h3>", unsafe_allow_html=True)
    st.caption(f"{len(staged)} entry(ies) counted on every page but not yet in the tracker file.")
    preview = [c for c in ["Email/JIRA Date", "Jira Key", "Customer", "Event type",
                           "Event/Bulletin Title", "Issue Type", "Reason", "Root Cause",
                           "Severity", "Short Term Fix Status"] if c in source_cols]
    styled_table(staged_frame(source_cols)[preview])
    combined = apply_staged(df.drop(columns=[STAGED_FLAG], errors="ignore"))
    combined = combined.drop(columns=[STAGED_FLAG, "Month Label"], errors="ignore")
    for col in ("Month", "Email/JIRA Date", "Reporting Month", "Resolution Date"):
        if col in combined.columns:
            combined[col] = pd.to_datetime(combined[col], errors="coerce").dt.strftime("%d-%b-%Y")
    c1, c2 = st.columns(2)
    c1.download_button("Download tracker CSV including staged entries",
                       combined.to_csv(index=False).encode(), CSV_NAME, "text/csv")
    if c2.button("Discard staged entries"):
        st.session_state["staged"] = []
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Executive Overview
#
# Everything from here to the page dispatch serves one page. It is grouped rather
# than scattered because the page is a story told in sections, and these functions
# only make sense as that story's parts.
# ---------------------------------------------------------------------------

# The tracker's taxonomy, read out in English. `Root Cause` and `Sub-type` are the
# vocabulary of the people who file the records, and on a leadership page they say
# nothing: "Event Identification" and "Prioritization" are not categories a reader
# outside the team can rank, and "Review" -- the single largest People bucket -- is
# the vaguest word in the file. The tracker keeps its own wording, because that is
# the record; only the chart label is translated, and the original travels with it
# in the table beside the chart so an analyst can tie any slice back to a field.
# Two pairs deliberately share a label, which is what "club them" means: they are one
# failure to a reader and two values to the tracker. `Prioritization` and `Captured Late`
# both end with the customer hearing about an event we already had, late; `Tagging` and
# `Industry selection` are both the industry being wrong or missing at publication. The
# tracker keeps both values -- they travel in the `Tracker value` column beside the label
# -- and every block that aggregates on the label (`root_frame`, the miss-bucket tail,
# `audit_pages.miss_buckets`) has to sum into the label rather than key on the sub-type,
# or the second value silently overwrites the first.
#
# What is deliberately NOT in these labels is the actor, wherever the tracker puts the
# same sub-type under more than one owner. `Event Identification` is 5 People and 4
# Product, `Review` is 21 People and 2 Product, `Relevancy`'s one record is Product --
# so a label reading "an analyst did X" is a false statement on every Product row. The
# owner is carried beside the label, by `root_frame`'s Owner column and by the two
# owner-split buckets in `MISS_BUCKETS`, which is the only place it can be said and be
# true on every row.
PLAIN_SUBTYPE = {
    "Source Coverage": "Source not in our vendor or monitoring network",
    "Keyword Update": "Keyword Miss",
    "Review": "We saw it and chose not to report it",
    "Event Identification": "Classified as not impactful, wrongly",
    "Prioritization": "Captured, but notified late",
    "Captured Late": "Captured, but notified late",
    "Mapping": "Supplier was not mapped by the customer",
    "Visibility": "Published, but not visible to the customer",
    "Policy/Logic": "Our scoring or rules got it wrong",
    "Process Clarification": "We had to clarify the reporting guidelines",
    "Duplication": "The same event published twice",
    "Tagging": "Incorrect industry selection",
    "Industry selection": "Incorrect industry selection",
    "Relevancy": "Judged not relevant to this customer",
    "WarRoom Creation": "WarRoom Missed",
    "Strategy": "How we group events",
}

# Who owns the fix, in the same three colours everywhere they appear on the page.


# The inbox in three parts. Red is the failure, amber the complaint that was not one,
# blue the question -- and every slice carries its own label, count and share, so the
# ring never rests on colour alone.
SPLIT_COLOURS = ["#f28b82", "#f6c177", "#8ab4f8"]

# What each slice of the left ring means, for its hover.
SPLIT_MEANING = {
    "Confirmed misses": "The event did not reach the customer in time, and the "
                        "investigation agreed it was our failure",
    "Complaints, not a miss": "The customer asserted we failed; we did report it, and the "
                              "issue turned out to be something else",
    "Inquiries": "The customer asked how something works rather than asserting we failed",
}


def plain(value, mapping):
    """A taxonomy value in English, or the value itself if nothing maps it.

    Falling back to the original matters: a term added to the tracker tomorrow shows
    up as itself rather than vanishing from a chart or landing in an "Other" nobody
    asked for.
    """
    return mapping.get(str(value).strip(), str(value).strip())


def add_rule():
    """A full-width hairline between sections.

    The heading card alone was not enough separation: on a page this long the eye lost
    which chart a table belonged to, and two adjacent sections read as one.
    """
    st.markdown("<div class='section-rule'></div>", unsafe_allow_html=True)


def overview_split(df):
    """Every email in three mutually exclusive parts: a failure, a complaint that was
    not one, and a question.

    This is the first thing a reader needs and no chart said it: not every complaint is
    a miss, and not every email is a complaint.
    """
    cols = ["Category", "Records", "% of Total"]
    if df.empty or not {"Issue Type", "Missed_Flag"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    issue = df["Issue Type"].astype(str).str.strip()
    missed = df["Missed_Flag"].astype(str).str.strip().eq("Yes")
    out = pd.DataFrame([
        {"Category": "Confirmed misses", "Records": int(missed.sum())},
        {"Category": "Complaints, not a miss", "Records": int((issue.eq("Complaint") & ~missed).sum())},
        {"Category": "Inquiries", "Records": int(issue.eq("Inquiry").sum())},
    ])
    out["% of Total"] = (out["Records"] / max(len(df), 1) * 100).round(1).astype(str) + "%"
    return out


# EventWatch's own name for each failure, keyed on `(Root Cause, Sub-type)` -- the two
# fields the tracker actually stores, never on the display wording of `Reason`. A pair
# that is not in this map counts as `Needs Review` rather than being talked into the
# nearest term: two of the three roots carry rows whose taxonomy and evidence disagree
# (a Product row whose Comments describe a WarRoom that was never created, a People row
# about an SEC notification that arrived late), and quietly filing those under a
# plausible heading is how a taxonomy stops meaning anything.
#
# Each entry is (internal term, the same thing in plain English). The term is what the
# chart prints, the plain English rides on the hover and fills a column of the table, so
# the page reads to a VP without costing an analyst the word they file records under.
DRIVERS = {
    # -- Product: detection and system coverage -----------------------------------
    ("Product", "Source Coverage"): ("Source Miss", "The source is not in our vendor or monitoring network"),
    ("Product", "Keyword Update"): ("Keyword Miss", "Monitored source, but retrieval logic missed the article"),
    ("Product", "Event Identification"): ("Model Miss", "Incorrect automated classification or routing"),
    ("Product", "Review"): ("Model Miss", "The model had it and did not flag it as reportable"),
    ("Product", "Prioritization"): ("Model Miss", "Incorrect automated classification or routing"),
    ("Product", "Relevancy"): ("Model Miss", "Incorrect automated classification or routing"),
    ("Product", "Mapping"): ("Supplier Impact / Mapping", "The supplier was not mapped to the impacted event"),
    ("Product", "Visibility"): ("Portal Visibility Issue", "Published, but not visible to the customer"),
    ("Product", "Policy/Logic"): ("System Limitation", "A platform rule or scoring threshold held it back"),
    ("Product", "Industry selection"): ("Industry Tagging", "Incorrect industry selection, or the industry was missed"),
    ("Product", "Tagging"): ("Industry Tagging", "Incorrect industry selection, or the industry was missed"),
    ("Product", "Captured Late"): ("Alerting Gap", "Captured, but no alert went out in time"),
    # -- People: analyst assessment and review ------------------------------------
    ("People", "Review"): ("People / Analyst Miss", "An analyst read it and decided not to report it"),
    ("People", "Event Identification"): ("Event Identification", "Seen by an analyst and classified as not impactful"),
    ("People", "Prioritization"): ("Prioritization", "Ranked too low to raise, so the customer heard late"),
    ("People", "Relevancy"): ("Impact Misclassification", "Judged not relevant to the customer, wrongly"),
    ("People", "Duplication"): ("Duplicate Assessment Error", "The same event assessed and published twice"),
    ("People", "Mapping"): ("Supplier Selection", "An impacted supplier was left off the WarRoom"),
    ("People", "Tagging"): ("Industry Selection", "Incorrect industry selection, or the industry was missed"),
    ("People", "Industry selection"): ("Industry Selection", "Incorrect industry selection, or the industry was missed"),
    ("People", "Policy/Logic"): ("Incorrect Action", "The wrong action was taken on the event"),
    # `Delayed Notification` is a Process-list term used under People on purpose: the
    # People vocabulary has no word for lateness. No row carries this pair today -- the
    # one that briefly did turned out to be an analyst who overlooked the story, which is
    # `Review` -- but the pair is plausible and mapping it keeps it out of Needs Review.
    # A term is a label, not a claim about the owner; the owner is the key it hangs on.
    ("People", "Captured Late"): ("Delayed Notification", "Captured, but the customer was told too late"),
    # -- Process: workflow and control ---------------------------------------------
    ("Process", "Process Clarification"): ("SOP Unclear", "Reporting guidelines had to be clarified to the customer"),
    ("Process", "Captured Late"): ("Delayed Notification", "Captured, but the customer was told too late"),
    ("Process", "WarRoom Creation"): ("WarRoom Issue", "A required WarRoom was missing, delayed, duplicated, or not visible"),
    ("Process", "Visibility"): ("WarRoom Issue", "A required WarRoom was missing, delayed, duplicated, or not visible"),
    ("Process", "Duplication"): ("Duplicate WarRoom", "One event published as two separate WarRooms"),
    ("Process", "Strategy"): ("Severity / Consolidation Handling", "How events are grouped, or the severity set on them"),
    ("Process", "Policy/Logic"): ("Severity / Consolidation Handling", "How events are grouped, or the severity set on them"),
    ("Process", "Review"): ("Peer Review Missing", "No second pair of eyes before it went out"),
}

NEEDS_REVIEW = "Needs Review"
DRIVER_OTHER = "Other"

# Who owns each root cause, in one line, as leadership reads it.
ROOT_OWNERSHIP = {
    "Product": "Detection and system coverage",
    "People": "Analyst assessment and review",
    "Process": "Workflow and control",
}
ROOT_COLOURS = {"Product": "#8ab4f8", "People": "#f28b82", "Process": "#f6c177"}


def name_subtypes(frame, col="Sub-type", head="What it means"):
    """Put the plain-English label beside a tracker Sub-type, on any tab.

    The Executive Summary translates the taxonomy and the source pages did not, so the
    same failure read "Source Coverage" on one tab and "Source not in our vendor or
    monitoring network" on another -- two vocabularies for one thing, which is the fault
    `PLAIN_SUBTYPE` exists to fix. The tracker value stays in its own column because it
    is the record; the label is inserted next to it, never over it.
    """
    if frame is None or frame.empty or col not in frame.columns:
        return frame
    out = frame.copy()
    out.insert(list(out.columns).index(col) + 1, head,
               out[col].map(lambda v: plain(v, PLAIN_SUBTYPE)))
    return out


def owner_pills(counts):
    """The owner column as one pill per owner, in that owner's own colour.

    It was the string "Product 12 · People 3", which reads as a single value and makes
    the reader parse two names and two numbers out of one run of text -- on the widest
    table on the page, where the owner is the column a VP actually looks for. One pill
    each, name and count set apart, coloured with the same three hues the root-cause
    cards and both donuts use, so the owner is recognised before it is read.

    This is the one place in `excel_bar_table` that writes HTML into a cell, and the
    strings are built here from `ROOT_COLOURS` keys -- never from anything a customer or
    an analyst typed, which still goes through `esc()`.
    """
    out = []
    for owner, n in counts.items():
        colour = ROOT_COLOURS.get(owner, "#b6beca")
        out.append(f"<span class='owner-pill' style='--c:{colour}'>{esc(owner)} <b>{int(n)}</b></span>")
    return "".join(out)


def plural(n, one, many=None):
    """"1 miss" / "2 misses" -- a leadership page does not write "miss(es)"."""
    return f"{n} {one if n == 1 else (many or one + 's')}"


def driver_of(root, subtype):
    """The internal term and its plain English, or Needs Review for an unmapped pair."""
    return DRIVERS.get((str(root).strip(), str(subtype).strip()),
                       (NEEDS_REVIEW, "The root cause and sub-type on this email do not map "
                                      "to a known failure driver"))


def root_summary(df):
    """Confirmed misses per root cause, biggest first, with each one's share.

    Rows are [(root, misses, share, ownership, colour)]. Only roots that actually carry
    a miss in the current filter appear, so a filtered view does not print a card whose
    number is zero.
    """
    if df.empty or not {"Root Cause", "Missed_Flag"} <= set(df.columns):
        return []
    missed = df[df["Missed_Flag"].astype(str).str.strip().eq("Yes")]
    if missed.empty:
        return []
    counts = missed["Root Cause"].fillna("Blank").astype(str).str.strip().value_counts()
    total = max(int(counts.sum()), 1)
    return [(root, int(n), n / total * 100,
             ROOT_OWNERSHIP.get(root, "Ownership not defined"),
             ROOT_COLOURS.get(root, "#b6beca"))
            for root, n in counts.items()]


def root_drivers(df, root, top=4):
    """The failure drivers behind one root cause's confirmed misses, biggest first.

    Only the top `top` are named; the rest collapse into one `Other` row whose own
    hover lists what is in it, so the fold can be checked rather than trusted.
    `Needs Review` never folds -- it is a data-quality signal, and burying it in Other
    is how a mis-filed row stays mis-filed.
    """
    cols = ["Driver", "What it means", "Misses", "% of Total"]
    if df.empty or not {"Root Cause", "Sub-type", "Missed_Flag"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    missed = df[(df["Missed_Flag"].astype(str).str.strip().eq("Yes"))
                & (df["Root Cause"].fillna("").astype(str).str.strip().eq(root))]
    if missed.empty:
        return pd.DataFrame(columns=cols)
    named = [driver_of(root, v) for v in missed["Sub-type"].fillna("").astype(str)]
    frame = pd.DataFrame({"Driver": [t for t, _ in named], "What it means": [m for _, m in named]})
    grouped = (frame.groupby(["Driver", "What it means"]).size()
                    .reset_index(name="Misses").sort_values("Misses", ascending=False))
    review = grouped[grouped["Driver"] == NEEDS_REVIEW]
    rest = grouped[grouped["Driver"] != NEEDS_REVIEW]
    keep, tail = rest.head(top), rest.iloc[top:]
    # An `Other` holding one driver hides a name to save no space -- "Other: 1 smaller
    # driver: Industry Selection (1)" is longer than "Industry Selection". Fold only when
    # there are at least two to fold.
    if len(tail) == 1:
        keep, tail = rest.head(top + 1), rest.iloc[top + 1:]
    rows = keep.to_dict("records")
    if not tail.empty:
        # The fold names itself. `Other` on a leadership chart is only honest if the
        # reader can find out what is in it without leaving the chart, so the row carries
        # every driver it swallowed, with each one's count, on its own hover.
        inside = ", ".join(f"{r['Driver']} ({int(r['Misses'])})" for _, r in tail.iterrows())
        rows.append({"Driver": DRIVER_OTHER,
                     "What it means": f"{plural(len(tail), 'smaller driver')}: {inside}",
                     "Misses": int(tail["Misses"].sum())})
    rows += review.to_dict("records")
    out = pd.DataFrame(rows)
    total = max(int(out["Misses"].sum()), 1)
    out["% of Total"] = (out["Misses"] / total * 100).round(1).astype(str) + "%"
    return out[cols].reset_index(drop=True)


def driver_table(df):
    """Every driver on one table, one row each, with the root causes that produced it.

    Grouped by driver rather than by root-and-driver, because a driver that occurs under
    two roots -- `Needs Review` does, on the current data -- would otherwise appear as
    two rows carrying the same name and different numbers, which reads as a duplicate and
    gives `audit_pages.py` two counts for one label. The roots ride in their own column
    with their counts, the way `root_frame()` carries owners.
    """
    cols = ["Driver", "Owner", "What it means", "Misses", "% of Total"]
    rows = []
    for root, _, _, _, _ in root_summary(df):
        for _, r in root_drivers(df, root, top=99).iterrows():
            rows.append({"Driver": r["Driver"], "Owner": root,
                         "What it means": r["What it means"], "Misses": int(r["Misses"])})
    if not rows:
        return pd.DataFrame(columns=cols)
    frame = pd.DataFrame(rows)
    out = []
    for driver, group in frame.groupby("Driver"):
        roots = group.groupby("Owner")["Misses"].sum().sort_values(ascending=False)
        # The column is named Owner rather than Root cause because that is the question
        # it answers on a leadership page, and it renders as one pill per owner for the
        # same reason the deeper-root-cause table does: two names and two numbers run
        # together in one string is not a column anybody reads.
        out.append({"Driver": driver,
                    "Owner": owner_pills(roots),
                    "What it means": group["What it means"].iloc[0],
                    "Misses": int(group["Misses"].sum())})
    table = pd.DataFrame(out).sort_values("Misses", ascending=False).reset_index(drop=True)
    total = max(int(table["Misses"].sum()), 1)
    table["% of Total"] = (table["Misses"] / total * 100).round(1).astype(str) + "%"
    return table[cols]


def driver_bar(frame, colour, title="", slots=None, xmax=None):
    """A compact bar of one root cause's drivers, all in that root's colour.

    One hue per chart on purpose: the root cause is already named on the card above, so
    colouring the drivers against each other would say a difference that is not there.
    The plain-English meaning rides on the hover so the bar stays a bar.
    """
    if frame is None or frame.empty:
        st.caption("No confirmed miss for this root cause in the current filter.")
        return None
    data = frame.copy()
    # Plotly's hover label does not wrap and is not clipped to the panel, so a long
    # meaning ran off both edges of a third-width column and lost its own ends. Wrapping
    # it here is the only thing that keeps the tooltip inside the card.
    data["_hover"] = data["What it means"].map(
        lambda t: "<br>".join(textwrap.wrap(str(t), 44)) or "")
    data["_count"] = data["Misses"].map(lambda n: plural(int(n), "confirmed miss", "confirmed misses"))
    fig = px.bar(data, x="Misses", y="Driver", orientation="h", text="Misses",
                 title=title, color_discrete_sequence=[colour],
                 custom_data=["_hover", "% of Total", "_count"],
                 category_orders={"Driver": list(data["Driver"])})
    fig.update_traces(opacity=.93, marker_line_width=0, cliponaxis=False,
                      textposition="outside", textfont=dict(size=12, color="#f3f4f6"),
                      hovertemplate="<b>%{y}</b> — %{customdata[2]}, %{customdata[1]}"
                                    "<br>%{customdata[0]}<extra></extra>")
    fig.update_yaxes(tickfont=dict(size=12.5, color="#f3f4f6"), gridcolor="#303846", title="",
                     automargin=True, ticklabelposition="outside")
    # One x scale across all three panels. Each chart used to autoscale, so Process's
    # 2-miss bar drew almost as long as Product's 24 -- three panels side by side are
    # read as a comparison whether or not they are labelled one, and bar length is the
    # thing a reader takes from a bar chart before the number beside it. The axis stays
    # hidden; the count still rides on the end of every bar.
    fig.update_xaxes(visible=False, range=[0, (xmax or float(data["Misses"].max())) * 1.16])
    # `slots` pads the axis to the longest of the three lists rather than stretching this
    # one's bars to fill the panel: three charts of equal height whose bars are three
    # different thicknesses compare their own shapes, not their numbers. The padding is
    # empty space below the last bar, which reads as "this root cause has fewer kinds".
    rows = max(slots or len(data), len(data))
    # px numbers the categories from the bottom, so the padded slots have to be added
    # below the shortest list rather than above it -- otherwise a root cause with two
    # drivers draws them at the foot of an empty panel.
    fig.update_yaxes(range=[len(data) - rows - 0.5, len(data) - 0.5])
    # hovermode "y" so the tooltip fires anywhere along the row, not only on the bar:
    # a one-miss bar is fourteen pixels wide, and the rows a reader most wants explained
    # -- Other, Needs Review -- are exactly the short ones.
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=12), showlegend=False, hovermode="y",
                      hoverlabel=dict(bgcolor="#11151b", bordercolor=colour, align="left",
                                      font=dict(color="#f3f4f6", size=12)),
                      margin=dict(l=0, r=40, t=8, b=6),
                      height=max(160, rows * 38 + 36))
    st.plotly_chart(fig, width="stretch")
    return fig


def takeaway(df):
    """One sentence, every figure in it computed from the frame on screen.

    Named the largest root cause and its two biggest drivers, or says plainly when there
    is not enough in the filter to name them -- a takeaway that invents a finding when
    the data has none is the horoscope problem in one line.
    """
    summary = root_summary(df)
    if not summary:
        return None
    root, misses, share, _, colour = summary[0]
    drivers = root_drivers(df, root, top=99)
    drivers = drivers[~drivers["Driver"].isin([DRIVER_OTHER, NEEDS_REVIEW])]
    if drivers.empty:
        return (f"Most confirmed misses are concentrated in <b>{esc(root)}</b> "
                f"({misses} of {int(sum(n for _, n, *_ in summary))}, {share:.0f}%).", colour)
    top_two = drivers.head(2)
    named = ", ".join(f"{r['Driver']} ({int(r['Misses'])})" for _, r in top_two.iterrows())
    total = int(sum(n for _, n, *_ in summary))
    return (f"Most confirmed misses are concentrated in <b>{esc(root)}</b> — "
            f"{misses} of {total}, {share:.0f}% — primarily driven by <b>{esc(named)}</b>.",
            colour)


def miss_owner_split(df):
    """The confirmed misses by who has to fix them, as the second ring.

    Named `Product` / `People` / `Process`, the tracker's own values, so the ring and the
    three cards below it speak one vocabulary -- it briefly read "The platform / Our
    analysts / How we work" here and the tracker's names in the section underneath, which
    is two words for one thing on one page. The ownership line rides on each slice's
    hover instead, which is where the plain English belongs.
    """
    cols = ["Category", "Records", "% of Total"]
    if df.empty or not {"Missed_Flag", "Root Cause"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    missed = df[df["Missed_Flag"].astype(str).str.strip().eq("Yes")]
    if missed.empty:
        return pd.DataFrame(columns=cols)
    out = missed["Root Cause"].fillna("Blank").astype(str).str.strip().value_counts().reset_index()
    out.columns = ["Category", "Records"]
    out["% of Total"] = (out["Records"] / max(len(missed), 1) * 100).round(1).astype(str) + "%"
    return out


def miss_by_customer(df):
    """One row per account: emails and what they were, then the misses by what failed.

    The email columns exist because "44" on its own does not say 44 of what. `Emails` is
    every email that named the account, complaints and inquiries together, and the two
    columns beside it break that down; `Misses` and the failure columns count only the
    confirmed misses, which is a smaller number from a different base. Both bases are on
    the row rather than left to a caption.

    Accounts are split on the slash, the same rule `customer_exposure()` uses, so a
    `Ford/GM` email counts for both and the email totals agree with every other page.
    That also means the Emails column sums to more than the tracker holds -- a merged
    email is counted once per account it names -- which the total row shows honestly
    rather than hiding.
    """
    if df.empty or "Customer" not in df.columns:
        return pd.DataFrame(columns=["Customer", "Emails", "Complaints", "Inquiries", "Misses"])
    frame = df.assign(_bucket=miss_bucket_series(df))
    # explode() repeats the source index, and crosstab cannot reindex a duplicated axis,
    # so the exploded frame gets a fresh one.
    exploded = (frame.assign(_c=frame["Customer"].fillna("Blank").astype(str).str.split("/"))
                     .explode("_c").reset_index(drop=True))
    exploded["_c"] = exploded["_c"].str.strip().replace("", "Blank")
    issue = exploded.get("Issue Type", pd.Series(dtype=str)).astype(str).str.strip()
    emails = exploded["_c"].value_counts()
    grid = pd.crosstab(exploded["_c"], exploded["_bucket"])
    labels = [c for c in miss_categories(df)["Category"] if c in grid.columns]
    out = pd.DataFrame({"Customer": list(emails.index), "Emails": list(emails.values)})
    for name, value in (("Complaints", "Complaint"), ("Inquiries", "Inquiry")):
        counts = exploded["_c"][issue.eq(value)].value_counts()
        out[name] = [int(counts.get(c, 0)) for c in out["Customer"]]
    for label in labels:
        out[label] = [int(grid.loc[c, label]) if c in grid.index else 0 for c in out["Customer"]]
    out["Misses"] = out[labels].sum(axis=1) if labels else 0
    # Against the tracker's own miss count, NOT the sum of this column: the column
    # double-counts every email that names two accounts, so a share taken from it would
    # be a share of a number that appears nowhere else on the dashboard.
    total = max(int((miss_bucket_series(df) != "").sum()), 1)
    out["% of Total"] = (out["Misses"] / total * 100).round(1).astype(str) + "%"
    cols = ["Customer", "Emails", "Complaints", "Inquiries"] + labels + ["Misses", "% of Total"]
    return out[cols].sort_values(["Misses", "Emails"], ascending=False).reset_index(drop=True)


def customer_totals(df):
    """The true column totals for `miss_by_customer()`, and how far its rows overshoot.

    Returns `(totals, overshoot)`. The per-account rows deliberately double-count: an
    email naming `Ford/GM` is one email in the tracker and a row on both accounts, which
    is the rule the whole app uses so that "how many emails touched Ford" has an answer.
    Adding the columns up therefore prints 120 emails against a tracker of 115 -- a
    number that appears nowhere else on the dashboard, and the first thing a reader
    challenges. The total row carries these figures instead, and `overshoot` is what the
    caption needs to explain the gap rather than leave it to be noticed.
    """
    issue = df.get("Issue Type", pd.Series(dtype=str)).astype(str).str.strip()
    buckets = miss_bucket_series(df)
    totals = {"Emails": len(df),
              "Complaints": int(issue.eq("Complaint").sum()),
              "Inquiries": int(issue.eq("Inquiry").sum()),
              "Misses": int((buckets != "").sum())}
    for label, n in buckets[buckets != ""].value_counts().items():
        totals[label] = int(n)
    shared = df["Customer"].fillna("").astype(str).str.contains("/") if "Customer" in df.columns else pd.Series(dtype=bool)
    overshoot = {"emails": int(shared.sum()),
                 "misses": int((shared & (buckets != "")).sum())}
    return totals, overshoot


def missed_event_types(df):
    """What kinds of event we actually miss -- fires, insolvencies, port disruption.

    Counted over the confirmed misses only. The block that used to sit here was titled
    "Missed event types" and counted every email, misses and non-misses alike, so it
    answered a different question from the one its own heading asked.
    """
    cols = ["Event type", "Records", "% of Total"]
    if df.empty or not {"Event type", "Missed_Flag"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    missed = df[df["Missed_Flag"].astype(str).str.strip().eq("Yes")]
    if missed.empty:
        return pd.DataFrame(columns=cols)
    out = missed["Event type"].fillna("Blank").astype(str).str.strip().value_counts().reset_index()
    out.columns = ["Event type", "Records"]
    out["% of Total"] = (out["Records"] / max(len(missed), 1) * 100).round(1).astype(str) + "%"
    return out


def all_event_types(df):
    """Every email by event type, with the complaint/inquiry split on the row.

    The miss table beside it answers "what do we fail to report"; this answers "what do
    customers write to us about at all", and neither is readable without the other -- a
    9-miss event type is a different fact depending on whether 10 emails named it or 40.
    Same shape as `count_table`, so the Complaints and Inquiries columns are the ones
    every other page carries.
    """
    cols = ["Event type", "Complaints", "Inquiries", "Records", "% of Total"]
    if df.empty or "Event type" not in df.columns:
        return pd.DataFrame(columns=cols)
    return count_table(df, "Event type")


def event_type_pairs(df):
    """Event type by emails AND confirmed misses on one row, with the miss rate.

    The two tables on their own leave the reader subtracting: this is the column that
    says which event types we are actually bad at, as against the ones we merely get a
    lot of. The rate carries its own base, because 100% of one email is not a finding.
    """
    cols = ["Event type", "Emails", "Complaints", "Inquiries", "Misses", "Reported timely",
            "Miss rate", "% of Total"]
    if df.empty or not {"Event type", "Missed_Flag"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    frame = df.copy()
    frame["Event type"] = frame["Event type"].fillna("Blank").astype(str).str.strip()
    frame["_miss"] = frame.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes")
    issue = frame.get("Issue Type", pd.Series("", index=frame.index)).astype(str).str.strip()
    rows = []
    for value, group in frame.groupby("Event type"):
        misses = int(group["_miss"].sum())
        rows.append({"Event type": value, "Emails": len(group),
                     "Complaints": int(issue.loc[group.index].eq("Complaint").sum()),
                     "Inquiries": int(issue.loc[group.index].eq("Inquiry").sum()),
                     "Misses": misses, "Reported timely": len(group) - misses,
                     "Miss rate": f"{misses / max(len(group), 1) * 100:.0f}% of {len(group)}"})
    out = pd.DataFrame(rows).sort_values(["Misses", "Emails"], ascending=False).reset_index(drop=True)
    total = max(int(out["Misses"].sum()), 1)
    out["% of Total"] = (out["Misses"] / total * 100).round(1).astype(str) + "%"
    return out[cols]


def nature_table(df):
    """The reusable categories behind what customers actually wrote.

    The same fold, the same words and now the same meaning text the All customer emails
    tab defines -- so a reader who stops on a category name here reads one sentence
    about it, not a different one on each tab.
    """
    if df.empty or "Reason" not in df.columns:
        return pd.DataFrame(columns=["Category", "What it means", "Complaints", "Inquiries",
                                     "Misses", "Reported timely", "Records", "% of Total"])
    frame = df.copy()
    frame["Category"] = reason_category(df)
    out = count_table(frame, "Category")
    out.insert(1, "What it means", out["Category"].map(CATEGORY_MEANING).fillna(""))
    return out


def stacked_bar(frame, label_col, parts, colours, title="", x_title="Records", rows=8):
    """A ranked horizontal bar broken into named parts.

    `chart()` stacks the complaint/inquiry split and nothing else; this takes any set of
    part columns, which is what lets one account's bar say *why* it was missed rather
    than only how often.
    """
    parts = [c for c in parts if c in frame.columns]
    if frame.empty or label_col not in frame.columns or not parts:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}.")
        return None
    data = frame.head(rows).copy()
    data[label_col] = data[label_col].astype(str)
    fig = px.bar(data, x=parts, y=label_col, orientation="h", title=title,
                 color_discrete_map=colours)
    # Eleven series wrap the legend onto three rows. Above the plot those rows land on
    # the title; below the axis they have the whole bottom margin to themselves.
    rows_of_legend = max(1, (len(parts) + 3) // 4)
    fig.update_layout(barmode="stack", legend_title_text="",
                      legend=dict(orientation="h", yanchor="top", y=-0.13, x=0))
    fig.update_yaxes(categoryorder="total ascending", tickfont=dict(size=13, color="#f3f4f6"),
                     gridcolor="#303846", title="")
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title=x_title)
    fig.update_traces(opacity=.92, cliponaxis=False, marker_line_width=0,
                      hovertemplate="%{y}<br>%{fullData.name}: %{x}<extra></extra>")
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=13),
                      margin=dict(l=20, r=40, t=56, b=46 + 26 * rows_of_legend),
                      height=max(360, min(780, len(data) * 40 + 190 + 26 * rows_of_legend)))
    st.plotly_chart(fig, width="stretch")
    return fig


def trend_windows(df, window=3):
    """The monthly miss rate, plus the pooled rate of the last `window` months and the
    `window` before them.

    Pooled on counts, never on the mean of the monthly percentages: a month with 4
    emails must not weigh the same as one with 18. Returns `(rate, band)` with band None
    when there are not two full windows to compare, because two averages drawn over
    four months of data is a shape, not a finding.
    """
    rate = missed_rate(df)
    if len(rate) < window * 2:
        return rate, None
    def pooled(part):
        emails = int(part["Records"].sum())
        return {"months": list(part["Month"]), "emails": emails,
                "value": part["Missed"].sum() / max(emails, 1) * 100}
    return rate, {"older": pooled(rate.iloc[-window * 2:-window]), "recent": pooled(rate.tail(window))}


def trend_chart(rate, band, title=""):
    """One bar per month, coloured by which window it belongs to.

    This was a line with two flat shelves drawn over it and a signed delta printed on the
    plot, and it was not readable: a reader had to be told what the shelves meant before
    the chart said anything. Bars need no explaining -- each month is its own bar with its
    own percentage printed on it, and the two windows being compared are told apart by
    colour, with the comparison itself stated in words above the chart rather than drawn
    into it. Months outside both windows stay grey so they cannot be mistaken for part of
    the comparison.
    """
    if rate.empty or "Missed %" not in rate.columns:
        st.info("Chart cannot be rendered because required fields are missing: Month, Missed %.")
        return None
    months = list(rate["Month"])
    older = set(band["older"]["months"]) if band else set()
    recent = set(band["recent"]["months"]) if band else set()
    colour = ["#8ab4f8" if m in recent else "#b6beca" if m in older else "#3a414d" for m in months]
    legend = ("Blue: the last three months.  Grey: the three before.  Dark: outside the comparison."
              if band else "")
    fig = go.Figure(go.Bar(
        x=months, y=list(rate["Missed %"]), marker=dict(color=colour, line=dict(width=0)),
        text=[f"{v:.0f}%" for v in rate["Missed %"]], textposition="outside",
        textfont=dict(size=13, color="#f3f4f6"),
        customdata=rate[["Missed", "Records"]].values,
        hovertemplate="%{x}<br>%{y:.0f}% — %{customdata[0]} of %{customdata[1]} emails<extra></extra>"))
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_yaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title="",
                     ticksuffix="%", range=[0, 105])
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=13), title=title, showlegend=False,
                      margin=dict(l=20, r=30, t=56 if title else 20, b=28), height=400)
    st.plotly_chart(fig, width="stretch")
    if legend:
        st.caption(legend)
    return fig


def trend_table(rate, band):
    """The monthly series as a table, with a total whose share is pooled, not averaged."""
    if rate.empty:
        return pd.DataFrame(columns=["Month", "Emails", "Confirmed misses", "Miss rate"])
    out = pd.DataFrame({
        "Month": [pd.Period(m, freq="M").strftime("%b %Y") for m in rate["Month"]],
        "Emails": rate["Records"].astype(int).values,
        "Confirmed misses": rate["Missed"].astype(int).values,
    })
    out["Miss rate"] = (out["Confirmed misses"] / out["Emails"].clip(lower=1) * 100).round(0).astype(int).astype(str) + "%"
    emails, misses = int(out["Emails"].sum()), int(out["Confirmed misses"].sum())
    out.loc[len(out)] = {"Month": "Total", "Emails": emails, "Confirmed misses": misses,
                         "Miss rate": f"{misses / max(emails, 1) * 100:.0f}%"}
    return out


def root_frame(df):
    """One row per failure: how many emails named it, and how many of those were misses.

    Both numbers on one row is the point -- `Review` is 22 emails of which 19 were
    confirmed misses, `Process Clarification` is 13 emails of which 2 were. A table of
    misses alone cannot say which failures we mostly get away with.

    Keyed on the failure, not on failure-and-owner: the same sub-type sits under two
    owners on several rows, and a chart whose y axis repeats a label silently merges the
    two. The owners are kept as a column that names them with their counts, so nothing is
    lost -- and the four buckets on "Why the events were missed" already split the ones
    where the owner changes the answer.
    """
    cols = ["What went wrong", "Owner", "Tracker value", "Emails", "Misses",
            "Reported timely", "% of Total"]
    if df.empty or not {"Root Cause", "Sub-type"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    frame = pd.DataFrame({
        "_value": df["Sub-type"].fillna("Blank").astype(str).str.strip(),
        "_owner": df["Root Cause"].fillna("Blank").astype(str).str.strip(),
        "_miss": df.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes"),
    })
    # Grouped on the LABEL, not on the sub-type. Two pairs of tracker values deliberately
    # share a label (`Prioritization`/`Captured Late`, `Tagging`/`Industry selection`), and
    # grouping on the value would draw two bars carrying the same name -- which a y axis
    # silently merges, and which gives `audit_pages.py` two counts for one label. Both
    # tracker values ride in the `Tracker value` column, so nothing is hidden by the fold.
    frame["What went wrong"] = frame["_value"].map(lambda v: plain(v, PLAIN_SUBTYPE))
    rows = []
    misses_total = max(int(frame["_miss"].sum()), 1)
    for label, group in frame.groupby("What went wrong"):
        owners = group["_owner"].value_counts()
        values = group["_value"].value_counts()
        rows.append({
            "What went wrong": label,
            "Owner": owner_pills(owners),
            "Tracker value": " · ".join(values.index) if len(values) > 1 else values.index[0],
            "Emails": len(group),
            "Misses": int(group["_miss"].sum()),
            "Reported timely": len(group) - int(group["_miss"].sum()),
        })
    out = pd.DataFrame(rows)
    out["% of Total"] = (out["Misses"] / misses_total * 100).round(1).astype(str) + "%"
    return out[cols].sort_values(["Misses", "Emails"], ascending=False).reset_index(drop=True)


def ranked_bar(frame, label_col, value_col, colours=None, title="", x_title="Records",
               height_per=38):
    """One bar per category, longest first, each in its own colour.

    A donut stops working past about six slices, and there are eleven kinds of miss once
    the residue bucket is gone. A ranked bar takes as many categories as the taxonomy
    has, keeps every name readable on the axis, and still shows the share -- which is
    what the ring was for.
    """
    if frame is None or frame.empty or label_col not in frame.columns:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}.")
        return None
    data = frame.copy()
    data[label_col] = data[label_col].astype(str)
    fig = px.bar(data, x=value_col, y=label_col, orientation="h", title=title,
                 text=value_col, color=label_col,
                 color_discrete_map=colours or {},
                 category_orders={label_col: list(data[label_col])})
    fig.update_yaxes(tickfont=dict(size=13, color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title=x_title)
    fig.update_traces(opacity=.92, cliponaxis=False, marker_line_width=0,
                      textposition="outside", textfont=dict(size=13, color="#f3f4f6"),
                      hovertemplate="%{y}<br>%{x}<extra></extra>")
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=13), showlegend=False,
                      margin=dict(l=20, r=70, t=56 if title else 20, b=34),
                      height=max(320, len(data) * height_per + 130))
    st.plotly_chart(fig, width="stretch")
    return fig


def grouped_bar(frame, label_col, series, colours, title="", x_title="Customer emails"):
    """Two bars per row, so "how many, and how many of those went wrong" is one picture.

    The sunburst that stood here was two rings of unequal wedges, and past the biggest
    four every label was too small to print. This says the same thing in a form a reader
    does not have to be taught: every sub-type on the axis, nothing folded away.
    """
    series = [c for c in series if c in frame.columns]
    if frame is None or frame.empty or not series:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}.")
        return None
    data = frame.copy()
    data[label_col] = data[label_col].astype(str)
    fig = px.bar(data, x=series, y=label_col, orientation="h", barmode="group", title=title,
                 text_auto=True, color_discrete_map=colours,
                 category_orders={label_col: list(data[label_col])})
    fig.update_yaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title=x_title)
    fig.update_traces(opacity=.92, cliponaxis=False, marker_line_width=0,
                      textfont=dict(size=11), textposition="outside",
                      hovertemplate="%{y}<br>%{fullData.name}: %{x}<extra></extra>")
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=13), legend_title_text="",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      margin=dict(l=20, r=70, t=86, b=34),
                      height=max(420, len(data) * 46 + 180))
    st.plotly_chart(fig, width="stretch")
    return fig


def render_root_cause(page):
    """Why the events were missed: the three owner cards and their failure drivers.

    One implementation, called by the Executive Summary and by Root cause. The two used
    to be different code answering the same question, which is how a dashboard ends up
    contradicting itself -- and it is also the only honest way to satisfy "put the
    Executive Summary views on the internal pages" without the internal page being a
    second, drifting copy. The summary calls it and stops; Root cause calls it and then
    goes deeper.
    """
    missed = int(page.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes").sum())
    cats = miss_categories(page)
    bucket = lambda name: int(cats.loc[cats["Category"] == name, "Records"].iloc[0]) \
        if name in set(cats["Category"]) else 0
    never = bucket(MISS_BUCKETS[0][0]) + bucket(MISS_BUCKETS[1][0])
    add_section("Why the events were missed", "Two tiers. The cards are the three root causes the "
                "tracker records, with who owns each one; under each card sit that root cause's "
                "biggest failure drivers, in EventWatch's own terms — hover any bar for what the "
                "term means. Everything is keyed on the Root Cause and Sub-type fields on the "
                "record, never on how the customer worded it, and a pair that does not map to a "
                "known driver is shown as Needs Review rather than talked into the nearest "
                "heading.", "#f28b82")
    roots = root_summary(page)
    if not roots:
        st.info("No email in the current filter is flagged as a confirmed miss.")
    else:
        # The headline of the whole page, and the one number Product can act on. Computed
        # from the two buckets above rather than written down, so it cannot go stale.
        st.markdown(
            f"<div class='insight-box' style='--accent:#8ab4f8'><b style='color:#8ab4f8'>"
            f"{never} of {missed} misses never entered our system.</b> "
            f"{bucket(MISS_BUCKETS[0][0])} because the source was not part of our vendor or "
            f"monitoring network, {bucket(MISS_BUCKETS[1][0])} because a source we do monitor "
            f"carried it and no keyword matched. That is the size of the source-and-keyword "
            f"problem; what to buy or build against it is Product's call, not this "
            f"dashboard's.</div>", unsafe_allow_html=True)
        # One height for all three, from the longest list: three panels ending at three
        # different depths reads as three unrelated charts rather than one comparison.
        frames = {root: root_drivers(page, root) for root, *_ in roots}
        slots = max((len(f) for f in frames.values()), default=1)
        widest = max((float(f["Misses"].max()) for f in frames.values() if not f.empty), default=1.0)
        # Card and bars in ONE column each, not two rows of three. As two separate
        # st.columns calls the card sat in a row of its own and its drivers in another,
        # so at the width this is read at the eye had to carry "Product" down past a
        # card border to know whose bars it was looking at -- and the three cards, being
        # equal-height, pushed the bars a full card below the fold. One column per root
        # cause reads as one story per root cause.
        for column, (root, n, share, owns, colour) in zip(st.columns(len(roots)), roots):
            with column:
                st.markdown(
                    f"<div class='root-card' style='--accent:{colour}'>"
                    f"<div class='rc-name'>{esc(root)}</div>"
                    f"<div class='rc-num'>{n}</div>"
                    f"<div class='rc-base'>of {missed} confirmed misses</div>"
                    f"<div class='rc-share'>{share:.0f}%</div>"
                    f"<div class='rc-desc'>{esc(owns)}</div></div>", unsafe_allow_html=True)
                driver_bar(frames[root], colour, slots=slots, xmax=widest)
        line = takeaway(page)
        if line:
            text, colour = line
            st.markdown(f"<div class='takeaway' style='--accent:{colour}'>{text}</div>",
                        unsafe_allow_html=True)
        note = root_recent_note(page)
        if note:
            st.caption(note)
        drivers = driver_table(page)
        # `wide roomy` plus a wrapped meaning column is the whole readability fix here.
        # Without `wrap` the `wide` variant sets white-space:nowrap on every cell, so the
        # explanation column ran the table off the right of the panel and a reader had to
        # scroll sideways to read a sentence; without `roomy` the rows were 8px-padded
        # 13px text with the sentence centred in its cell. The meaning now wraps inside
        # 340-640px, left-aligned, and the table takes the page width it has rather than
        # being squeezed to 100% of a narrower box.
        excel_bar_table(drivers, "Driver", value_col="Misses",
                        extras=["Owner", "What it means"], label_head="Failure driver",
                        value_head="Confirmed misses", variant="wide roomy",
                        wrap=["What it means"], raw=["Owner"], classes={"Owner": "owners"},
                        caption="Every driver behind the three cards above, biggest first. "
                                "Owner is the root cause on the record itself, so a driver "
                                "that occurs under two owners shows both with their counts "
                                "rather than being filed under whichever is larger.")
        downloads(drivers, "miss_drivers")


def render_customers(page):
    """Customers impacted: the stacked bar and every account, with reconciled totals."""
    accounts = miss_by_customer(page)
    cats = miss_categories(page)
    add_section("Customers impacted", "Every account in the filter. Emails is every email that named "
                "the account, complaints and inquiries together; the columns after it count only the "
                "confirmed misses, split by what failed. Both bases sit on the row, because 44 on its "
                "own does not say 44 of what. Accounts are split on the slash, so an email naming two "
                "of them appears on both rows — the rows therefore add to more than the tracker holds, "
                "and the Total row is the distinct count, not the column sum.", "#f6c177")
    if accounts.empty:
        st.info("No customer recorded in the current filter.")
    else:
        bucket_names = [c for c in accounts.columns
                        if c not in ("Customer", "Emails", "Complaints", "Inquiries", "Misses", "% of Total")]
        f_cust = stacked_bar(accounts[accounts["Misses"] > 0], "Customer", bucket_names,
                             miss_colours(page, cats),
                             title="Confirmed misses by account, and what failed",
                             x_title="Confirmed misses")
        totals, over = customer_totals(page)
        excel_bar_table(accounts, "Customer", value_col="Misses",
                        extras=["Emails", "Complaints", "Inquiries"] + bucket_names,
                        label_head="Customer", value_head="Confirmed misses", height=460,
                        variant="wide", totals=totals)
        rows_add = int(accounts["Emails"].sum())
        st.caption(
            f"All {len(accounts)} account(s) in the current filter, scrolling in place. "
            f"The rows add to {rows_add} emails because {over['emails']} email(s) name two "
            f"accounts each and are counted for both — {over['misses']} of those are "
            f"confirmed misses. **The Total row is the distinct count: {totals['Emails']} "
            f"emails and {totals['Misses']} misses**, the same figures as the cards at the "
            f"top of this page and every other tab.")
        downloads(accounts, "customers_impacted", f_cust)


def render_event_types(page):
    """Event types: every email, the confirmed misses, and one table carrying both."""
    add_section("Event types", "Two charts over the same filter, then one table carrying both. "
                "The left chart is every email a customer sent, by the kind of event it was "
                "about; the right one is only the confirmed misses. Neither is readable alone — "
                "nine misses is a different fact depending on whether ten emails named that "
                "event type or forty — so the table under them puts both bases on one row and "
                "prints the miss rate with its own denominator inside it.", "#f28b82")
    types, everything = missed_event_types(page), all_event_types(page)
    if types.empty and everything.empty:
        st.info("No email in the current filter carries an event type.")
    else:
        left, right = st.columns(2)
        with left:
            st.markdown("**Every email, by event type**")
            f_all = chart(everything, "Event type", title="", x_title="Customer emails") \
                if not everything.empty else None
        with right:
            st.markdown("**Only the confirmed misses**")
            f_types = chart(types, "Event type", title="", x_title="Confirmed misses") \
                if not types.empty else None
        pairs = event_type_pairs(page)
        if not pairs.empty:
            excel_bar_table(pairs, "Event type", value_col="Misses",
                            extras=["Emails", "Complaints", "Inquiries", "Reported timely",
                                    "Miss rate"],
                            label_head="Event type", value_head="Confirmed misses",
                            variant="wide roomy",
                            caption="Every row adds up: **Emails = Confirmed misses + "
                                    "Reported timely.** The rate prints its own denominator, "
                                    "because 100% of one email is not a finding.")
            downloads(pairs, "event_types", f_types or f_all)


def render_nature(page):
    """Nature of complaints: the seven categories, split on whether we got it wrong."""
    missed = int(page.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes").sum())
    add_section("Nature of complaints", "What the customer actually wrote about, folded onto the "
                "eight categories the All customer emails tab defines. Each bar is split: the "
                "darker part is the emails in that category that turned out to be a confirmed "
                "miss, the lighter part the ones where the event did reach them. That split is "
                "the answer to the question this block always raised — why the Event missed row "
                "does not equal the miss count at the top of the page.", "#8ab4f8")
    nature = nature_table(page)
    if nature.empty:
        st.info("No email in the current filter carries a reason.")
    else:
        # The category is what the customer complained about; Missed_Flag is whether the
        # event reached them in time. They are different measurements and the numbers
        # differ, which reads as an error until the chart shows the split on the bar
        # itself. An event reported eleven days late WAS reported, so it is not
        # `Event missed` -- but it did not arrive in time, so it is a miss.
        split = nature.copy()
        f_nature = stacked_bar(split, "Category", ["Misses", "Reported timely"],
                               {"Misses": "#f28b82", "Reported timely": "#b6beca"},
                               title="What customers wrote about, and how much of it we got wrong",
                               x_title="Customer emails", rows=len(split))
        excel_bar_table(nature, "Category", label_head="What they wrote about",
                        value_head="Emails", variant="wide roomy",
                        extras=["What it means", "Complaints", "Inquiries", "Misses",
                                "Reported timely"],
                        wrap=["What it means"],
                        caption="Every row adds up: **Emails = Confirmed misses + Reported "
                                "timely.** The same categories, with the same meanings, are "
                                "listed on All customer emails with every customer wording "
                                "folded into each one.")
        top = split.sort_values("Misses", ascending=False)
        others = top[top["Category"] != "Event missed"]
        elsewhere = int(others["Misses"].sum())
        named = ", ".join(f"{int(r['Misses'])} {r['Category'].lower()}"
                          for _, r in others[others["Misses"] > 0].iterrows())
        here = int(top.loc[top["Category"] == "Event missed", "Misses"].sum())
        st.caption(
            f"**Event missed carries {here} confirmed misses, not the {missed} on the cards "
            f"above, and that is not an error.** This column counts what the customer wrote "
            f"about; the miss count counts whether the event reached them in time. The other "
            f"{elsewhere} confirmed miss(es) sit in categories where the event was reported and "
            f"something else went wrong — {named}. "
            f"{here} + {elsewhere} = {here + elsewhere}.")
        downloads(split, "nature_of_complaints", f_nature)


def render_trend(page):
    """Is it getting better: the verdict sentence, the monthly bars and the table."""
    rate, band = trend_windows(page)
    add_section("Is it getting better?", "One bar per month: the share of that month's emails that "
                "turned out to be a confirmed miss, with its percentage printed on it. The last "
                "three months are blue and the three before them grey, and the sentence above the "
                "chart states the comparison rather than leaving it to be read off the bars. Both "
                "figures are pooled on counts, so a month with four emails does not weigh the same "
                "as one with eighteen.", "#f6c177")
    if rate.empty:
        st.info("No dated email in the current filter.")
    else:
        verdict = missed_verdict(rate)
        if verdict:
            headline, detail, colour, _ = verdict
            st.markdown(f"<div class='insight-box' style='--accent:{colour}'>"
                        f"<b style='color:{colour}'>{esc(headline)}.</b> {esc(detail)}</div>",
                        unsafe_allow_html=True)
        f_rate = trend_chart(rate, band, title="Confirmed misses as a share of each month's emails")
        months = trend_table(rate, band)
        styled_table(months, total_row=True)
        if band:
            st.caption(f"The comparison rests on {band['older']['emails']} emails and "
                       f"{band['recent']['emails']} emails. A single thin month moves it several "
                       f"points, so read it as a direction rather than a result.")
        else:
            st.caption("Fewer than six months of emails in this filter — too short to compare two windows.")
        downloads(months, "missed_event_rate", f_rate)


def render_deeper_root_cause(page):
    """The deeper root cause: every failure with both bases and its owner."""
    add_section("The deeper root cause", "Every failure in the taxonomy, in plain words, with the "
                "tracker's own value beside it in the table. Two bars on each row: how many emails "
                "named that failure at all, and how many of those we confirmed as a miss — so a "
                "failure we mostly get away with is told apart from one that costs us every time. "
                "Nothing is folded into an Other, however few emails carry it.", "#f28b82")
    roots = root_frame(page)
    if roots.empty:
        st.info("No email in the current filter carries a root cause.")
    else:
        f_root = grouped_bar(roots, "What went wrong", ["Emails", "Misses"],
                             {"Emails": "#b6beca", "Misses": "#f28b82"},
                             title="Every failure: emails raised, and how many were confirmed misses")
        excel_bar_table(roots, "What went wrong", value_col="Misses",
                        extras=["Owner", "Emails", "Tracker value"],
                        label_head="What went wrong", value_head="Confirmed misses",
                        variant="wide roomy", wrap=["Tracker value"], raw=["Owner"],
                        classes={"Owner": "owners"},
                        caption="Emails is every email that named this failure; Confirmed "
                                "misses is how many of those did not reach the customer in "
                                "time — the gap between the two is the failures we mostly "
                                "get away with. Tracker value is the Sub-type on the record, "
                                "and where two of them mean one thing to a reader both are "
                                "listed on the row.")
        downloads(roots, "root_cause_of_misses", f_root)


st.sidebar.title(APP_TITLE); st.sidebar.caption("Executive navigation")
selected_page = st.sidebar.radio("Dashboard pages", PAGES, label_visibility="collapsed")
df = load_data()
if df.empty: st.stop()
# Staged entries join the frame here, before filtering, so every page downstream
# counts them without knowing they exist.
df = apply_staged(df)
staged_count = int(df[STAGED_FLAG].sum()) if STAGED_FLAG in df.columns else 0
if staged_count:
    st.sidebar.warning(f"{staged_count} staged entry(ies) included on every page. "
                       f"Not yet written to the tracker file.")
filtered = sidebar_filters(df)

if selected_page == "Executive Summary":
    page_header(selected_page); page = filtered; filter_note()
    issue = page.get("Issue Type", pd.Series(dtype=str)).astype(str).str.strip()
    flag = page.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip()
    complaints = int(issue.eq("Complaint").sum()); inquiries = int(issue.eq("Inquiry").sum())
    total = max(len(page), 1)
    missed = int(flag.eq("Yes").sum())
    not_a_miss = int((issue.eq("Complaint") & flag.ne("Yes")).sum())
    cats = miss_categories(page)
    bucket = lambda name: int(cats.loc[cats["Category"] == name, "Records"].iloc[0]) if name in set(cats["Category"]) else 0
    never = bucket(MISS_BUCKETS[0][0]) + bucket(MISS_BUCKETS[1][0])
    overlooked = bucket(MISS_BUCKETS[2][0])
    rate, band = trend_windows(page)
    accounts = miss_by_customer(page)
    biggest = accounts.sort_values("Emails", ascending=False).head(1)
    # Eight cards in two rows of four, not eight across: eight in one row is 180px each
    # at the width this is read at, and the number -- the only part anyone reads from
    # across a meeting room -- is the first thing to shrink. Every card prints its own
    # denominator inside the number, because a bare percentage beside a bare count on
    # one screen is what made the last read-out of this page unreadable.
    kpis([("Customer emails", len(page), f"{complaints} complaints · {inquiries} inquiries", "#8ab4f8"),
          ("Complaints", f"{complaints} of {len(page)}", f"{complaints / total * 100:.0f}% of these emails", "#f6c177"),
          ("Confirmed misses", f"{missed} of {len(page)}", f"{missed / total * 100:.0f}% of these emails", "#f28b82"),
          ("Complaints, not a miss", f"{not_a_miss} of {max(complaints, 1)}",
           "we did report it; the issue was something else", "#80cbc4")], columns=4)
    kpis([("Never captured by us", f"{never} of {max(missed, 1)}",
           f"{never / max(missed, 1) * 100:.0f}% of misses — the event never entered our system", "#8ab4f8"),
          ("Seen, but overlooked", f"{overlooked} of {max(missed, 1)}",
           f"{overlooked / max(missed, 1) * 100:.0f}% of misses — captured, but an analyst did not raise it", "#f28b82"),
          ("Last three months",
           f"{band['recent']['value']:.0f}%" if band else "—",
           (f"of emails were a miss, against {band['older']['value']:.0f}% in the three before"
            if band else "needs six months of emails to compare"), "#f6c177"),
          ("One customer's share",
           f"{biggest['Customer'].iloc[0]}: {int(biggest['Emails'].iloc[0])} of {len(page)}" if not biggest.empty else "—",
           (f"{int(biggest['Emails'].iloc[0]) / total * 100:.0f}% of every email on this page"
            if not biggest.empty else "no customer recorded"), "#b6beca")], columns=4)

    add_rule()
    add_section("What customers sent us", "Two rings over the same filter. The left one is every "
                "email, split into the three things an email can be. The right one takes only the "
                "confirmed misses and splits them by who has to fix it — so the first answers "
                "\u201cis every complaint a failure\u201d and the second \u201cwhen we do fail, whose "
                "problem is it\u201d. Hover any slice for what it means.", "#8ab4f8")
    split, owners = overview_split(page), miss_owner_split(page)
    left, right = st.columns(2)
    with left:
        st.markdown("**Every email we received**")
        f_split = donut(split, colours=SPLIT_COLOURS, centre="customer<br>emails",
                        meanings=SPLIT_MEANING)
    with right:
        st.markdown("**Only the confirmed misses**")
        f_owner = donut(owners, colours=[ROOT_COLOURS.get(c, "#b6beca") for c in owners["Category"]],
                        centre="confirmed<br>misses",
                        meanings=ROOT_OWNERSHIP) if not owners.empty else None
    if not split.empty:
        excel_bar_table(split, "Category", label_head="Every email", value_head="Emails")
        downloads(split, "email_split", f_split)
    if not owners.empty:
        excel_bar_table(owners, "Category", label_head="Who fixes the miss", value_head="Misses")
        downloads(owners, "miss_owner_split", f_owner)

    add_rule()
    render_root_cause(page)

    add_rule()
    render_customers(page)

    add_rule()
    render_event_types(page)

    add_rule()
    render_nature(page)

    add_rule()
    render_trend(page)

    add_rule()
    render_deeper_root_cause(page)
elif selected_page == "Monthly trend":
    page_header(selected_page); page = filtered; filter_note()
    if "Month Label" in page.columns and "Issue Type" in page.columns:
        monthly = page.groupby("Month Label", dropna=False)["Issue Type"].value_counts().unstack(fill_value=0).reset_index()
        monthly["Month Date"] = pd.to_datetime(monthly["Month Label"], format="%b %Y", errors="coerce")
        monthly = monthly.sort_values("Month Date"); monthly["Total"] = monthly.drop(columns=["Month Label", "Month Date"]).sum(axis=1)
        display_monthly = monthly.drop(columns=["Month Date"], errors="ignore")
        add_section("Monthly trend source table", "Complaint and inquiry counts by reporting month, sorted chronologically from January onward."); styled_table(display_monthly); downloads(display_monthly, "monthly_trend")
        y_cols = [c for c in ["Complaint", "Inquiry"] if c in monthly.columns]
        add_section("Monthly complaint vs inquiry chart", "Compares complaint and inquiry volume month by month in calendar order.", "#80cbc4")
        fig = px.bar(monthly, x="Month Label", y=y_cols, barmode="group", text_auto=True, color_discrete_sequence=["#8ab4f8", "#80cbc4"])
        fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26", font=dict(color="#f3f4f6", size=13), margin=dict(l=20, r=30, t=30, b=40), height=430)
        fig.update_xaxes(categoryorder="array", categoryarray=monthly["Month Label"].tolist(), tickfont=dict(color="#f3f4f6"), gridcolor="#303846"); fig.update_yaxes(tickfont=dict(color="#f3f4f6"), gridcolor="#303846")
        st.plotly_chart(fig, width="stretch"); downloads(display_monthly, "monthly_trend_chart_data", fig)
    else: st.info("Monthly trend requires Month/Reporting Month and Issue Type fields.")
    add_rule()
    # The same block the Executive Summary carries, from the same function. This page
    # used to draw its own miss-rate line from `missed_rate()` while the summary drew
    # `trend_chart()` from pooled windows -- two charts of one number, disagreeing on
    # which months were being compared, and a reader moving between the tabs had no way
    # to tell which was the real one.
    render_trend(page)

elif selected_page == "Root cause":
    # The Executive Summary's two root-cause sections, then the cuts that do not fit on
    # a summary: the sub-type heatmap, what is growing, and the per-owner drill-downs.
    # It is the same code, so the two tabs cannot disagree about a driver's count or
    # call the same failure two things.
    render_root_cause(filtered)
    add_rule()
    render_deeper_root_cause(filtered)
    add_rule()
    source_page(selected_page, filtered, "Root Cause", "root_cause", summary=False)
elif selected_page == "Top customer complaints":
    page = source_page(selected_page, filtered, "Customer", "top_customers",
                       primary=customer_exposure, summary=False)
    # The Executive Summary's Customers impacted block, unchanged, so the account
    # numbers on the two tabs come from one computation.
    render_customers(page)
    add_rule()
    complaints = page[page["Issue Type"].astype(str).eq("Complaint")] if "Issue Type" in page.columns else page
    multi = int(complaints["Customer"].astype(str).str.contains("/").sum()) if "Customer" in complaints.columns else 0
    exact = count_table(complaints, "Customer")
    add_section("As the Excel Dashboard counts it", f"The workbook differs on two counts: it includes complaint "
                f"records only, and it matches the Customer field as a whole string, so each of the {multi} "
                f"multi-customer complaint row(s) becomes its own category instead of being added to either "
                f"account. Kept here so the two artefacts can be reconciled. The table above is the one that "
                f"answers how many emails and questions a customer sent in.", "#b6beca")
    styled_table(exact, height=420); downloads(exact, "top_customers_exact")
elif selected_page == "DETAIL · Event workload":
    page_header(selected_page); page = filtered; filter_note()
    # The Executive Summary's Event types block is the whole answer here; the generic
    # count-table-plus-chart pair this page used to draw said the same thing in weaker
    # words and with one base instead of two.
    render_event_types(page)
elif selected_page == "Dynamic Source Discovery":
    page_header(selected_page); page = filtered; filter_note(); disc = page[page["Standard Automation Focus"].astype(str).eq("Dynamic Source Discovery")] if "Standard Automation Focus" in page.columns else page.iloc[0:0]
    add_section("Source-miss meaning", "Dynamic Source Discovery identifies event types, customers, reasons, feeds, keywords, or source coverage patterns that current sources are missing or under-detecting.", "#80cbc4")
    for title, col in [("Event types missed by sources", "Event type"), ("Customers affected by source misses", "Customer"), ("Reasons linked to source misses", "Reason")]:
        if col in disc.columns: t = count_table(disc, col, base=max(len(page), 1)); add_section(title, f"Shows source-miss records by {col.lower()} with share of all selected records."); excel_bar_table(t, col); fig = chart(t, col, title=title); downloads(t, title.lower().replace(" ", "_"), fig)
    for first, second, name in [("Customer", "Event type", "Customer event-type source misses"), ("Event type", "Reason", "Event-type reason source misses"), ("Customer", "Reason", "Customer reason source misses")]:
        lt = long_pair_table(disc, first, second, base=max(len(page), 1))
        if not lt.empty: add_section(name, f"Readable detail table showing {first.lower()} and {second.lower()} as separate columns instead of a wide cross-tab.", "#a8dab5"); styled_table(lt, height=420); downloads(lt, name.lower().replace(" ", "_"))
    add_section("Complete Dynamic Source Discovery records", "All filtered records classified under Dynamic Source Discovery for detailed review.", "#b6beca"); styled_table(disc, height=420); downloads(disc, "dynamic_source_discovery_complete")
elif selected_page == "All customer emails":
    page_header(selected_page); page = with_failure_label(with_reason_category(filtered)); filter_note()
    complaints = int(page.get("Issue Type", pd.Series(dtype=str)).astype(str).eq("Complaint").sum())
    inquiries = int(page.get("Issue Type", pd.Series(dtype=str)).astype(str).eq("Inquiry").sum())
    total = max(len(page), 1)
    missed = int(page.get("Missed_Flag", pd.Series(dtype=str)).astype(str).eq("Yes").sum())
    pending = int(page.get("Short Term Fix Status", pd.Series(dtype=str)).astype(str).eq("Pending").sum())
    # Every card states the base it is a share of, in the card. A bare percentage next to
    # a bare count is what made two different denominators on one screen unreadable.
    # A complaint is not automatically a miss. 22 of the 97 are complaints where the event
    # WAS reported and the failure, if any, was something else -- wrong classification,
    # not visible on the portal, published twice, or nothing wrong at all. That gap is the
    # first thing a reader asks about and the card now answers it rather than posing it.
    other = complaints - int(((page.get("Issue Type", pd.Series(dtype=str)).astype(str) == "Complaint")
                              & (page.get("Missed_Flag", pd.Series(dtype=str)).astype(str) == "Yes")).sum())
    kpis([("Customer emails", len(page), f"{complaints} complaints · {inquiries} inquiries", "#8ab4f8"),
          ("Complaints", f"{complaints} of {len(page)}", f"{complaints / total * 100:.0f}% of these emails", "#f6c177"),
          ("Confirmed misses", f"{missed} of {len(page)}", f"{missed / total * 100:.0f}% of these emails", "#f28b82"),
          ("Complaints, not a miss", f"{other} of {max(complaints, 1)}", "we did report it; the issue was something else", "#80cbc4"),
          ("Under investigation", pending, "no answer sent to the customer yet", "#f6c177")])
    # Two audiences, one page: someone reading the tracker wants a narrow grid they can
    # scan, someone exporting a slice wants every field. A checkbox serves both without
    # a second page to keep in sync. Month_Sort is an internal sort key and never shown.
    show_all = st.checkbox("Show all fields", value=False, key="tracker_show_all",
                           help="Off: the columns worth scanning. On: every field on the record, which scrolls sideways.")
    grid = [c for c in TRACKER_COLUMNS if c in page.columns] if not show_all else \
           [c for c in page.columns if c not in (STAGED_FLAG, "Month_Sort")]
    view = page[grid].copy()
    styled_table(view.rename(columns=DISPLAY_NAMES), height=560, variant="wide grid",
                 wrap=WRAP_COLUMNS, styles=GRID_STYLES)
    st.caption("Every value is shown in full: the grid scrolls sideways, and the few long text "
               "cells that run past five lines scroll inside the cell rather than stretching the "
               "row. Open one email below to read it on its own.")

    # Counted, not typed. A prose figure that has to be remembered is a prose figure that
    # goes stale, which is the whole fault this tab exists to fix.
    said = page["Reason"].fillna("").astype(str).str.strip()
    cat = category_table(page)
    add_section("What the customer wrote about",
                f"The customer's own words run to {said[said != ''].nunique()} different wordings for "
                f"{len(cat) - 1} real things — \"Missed Event\", \"Missed insolvency alert\" and "
                "\"WarRoom should have been created but was not\" all say the same thing. Every wording "
                "folded into a category is listed beside it with its own count, so the fold can be "
                "checked rather than taken on trust. This is the wording every other tab uses.", "#80cbc4")
    # "Event missed" is smaller than the confirmed-miss count and a reader is right to
    # stop on that. They measure different things: the category is what the customer
    # complained about, the flag is whether the event reached them. An event reported
    # eleven days late was reported, so it is not "Event missed" -- but it did not reach
    # them in time, so it is a confirmed miss. Saying so beats leaving them to subtract.
    missed_here = int((reason_category(page) == "Event missed").sum())
    elsewhere = missed - missed_here
    styled_table(cat, variant="wide grid",
                 wrap=("What it means", "Their exact wordings"),
                 styles={"Category": "wrapcol", "What it means": "narrow",
                         "Their exact wordings": "mid bullets",
                         "Emails": "num", "Complaints": "num", "Inquiries": "num"},
                 total_row=True)
    if elsewhere > 0:
        spread = (reason_category(page)[page.get("Missed_Flag", pd.Series(dtype=str)).astype(str) == "Yes"]
                  .value_counts().drop(labels=["Event missed"], errors="ignore"))
        st.caption(
            f"**Why {missed} confirmed misses but only {missed_here} under Event missed?** "
            f"The category says what the customer complained about; the confirmed-miss flag says "
            f"whether the event reached them in time. *Event missed* is the clean case — we never "
            f"reported it at all, and all {missed_here} of those are misses. The other {elsewhere} "
            f"were reported, but still never reached the customer in time: "
            + ", ".join(f"{n} {k.lower()}" for k, n in spread.items()) + ".")
    downloads(cat, "reason_categories")

    still_open = page[page.get("Short Term Fix Status", pd.Series(dtype=str)).astype(str) == "Pending"]
    add_section("Under investigation", f"The {len(still_open)} customer email(s) with no answer sent back yet. "
                "Everything else has had a fix, an RCA or a clarification returned to the customer.", "#f6c177")
    if still_open.empty:
        st.info("Nothing in the current filter is still under investigation.")
    else:
        open_cols = [c for c in ("Email/JIRA Date", "Jira Key", "Customer", "Event/Bulletin Title",
                                 "Reason Category", "Missed_Flag") if c in still_open.columns]
        table = still_open[open_cols].rename(columns={"Email/JIRA Date": "Raised",
                                                      "Jira Key": "Ticket",
                                                      "Event/Bulletin Title": "What they reported",
                                                      "Missed_Flag": "Confirmed miss"})
        styled_table(table, variant="wide grid", wrap=("What they reported",),
                     styles={"Raised": "num", "Ticket": "key"})
        downloads(table, "under_investigation")

    add_section("Complaints that were not misses", f"{other} of the {complaints} complaints are ones where "
                "we did report the event. The customer still had something to raise — the classification on "
                "it was wrong, it did not show on their portal, it went out twice, or they disagreed with a "
                "judgement we had made. Only the coverage questions turned out to be nothing at all.", "#80cbc4")
    not_missed = page[(page.get("Issue Type", pd.Series(dtype=str)).astype(str) == "Complaint")
                      & (page.get("Missed_Flag", pd.Series(dtype=str)).astype(str) != "Yes")]
    if not_missed.empty:
        st.info("Every complaint in the current filter was a confirmed miss.")
    else:
        breakdown = category_table(not_missed).drop(columns=["Complaints", "Inquiries", "Misses"])
        styled_table(breakdown, variant="wide grid",
                     wrap=("What it means", "Their exact wordings"),
                     styles={"Category": "wrapcol", "What it means": "narrow",
                             "Their exact wordings": "mid bullets", "Emails": "num"},
                     total_row=True)
        downloads(breakdown, "complaints_not_missed")

    add_section("What the inquiries asked", f"{inquiries} of the {len(page)} emails are inquiries — the "
                "customer asked how something works rather than saying we had failed. The test that "
                "settles which is which is what went back to them: an explanation means it was an "
                "inquiry, a bulletin or a correction means we were at fault and it belongs with the "
                "complaints.", "#80cbc4")
    asked = inquiry_table(page)
    if asked.empty:
        st.info("No inquiries in the current filter.")
    else:
        styled_table(asked, variant="wide grid",
                     wrap=("What they asked about", "Their exact wordings", "How we answered"),
                     styles={"Category": "wrapcol", "What they asked about": "narrow",
                             "Their exact wordings": "mid bullets", "How we answered": "narrow bullets",
                             "Inquiries": "num", "Was a real miss": "num"},
                     total_row=True)
        downloads(asked, "inquiries")

    add_section("Open one email", "Every field of one customer email, including the full Comments, "
                "RCA Details and Automation Opportunity that the grid above shortens.")
    if page.empty:
        st.info("No customer emails to open under the current filters.")
    else:
        labels = record_labels(page)
        pick = st.selectbox("Customer email", list(labels), key="tracker_record",
                            help="Filtered by the sidebar, like every other tab.")
        record = page.loc[labels[pick]]
        detail = pd.DataFrame(
            [(DISPLAY_NAMES.get(c, c), cell(record[c])) for c in page.columns
             if c not in (STAGED_FLAG, "Month_Sort") and str(record[c]).strip() not in ("", "nan", "NaT")],
            columns=["Field", "Value"])
        styled_table(detail, variant="record")

    add_section("Export", "Both downloads follow the sidebar filters and the date range, "
                "so what you take away is what you are looking at.")
    c1, c2 = st.columns(2)
    c1.download_button("Download visible columns", view.to_csv(index=False).encode(),
                       "customer_tracker_visible.csv", "text/csv")
    c2.download_button("Download every field", page.drop(columns=[STAGED_FLAG], errors="ignore").to_csv(index=False).encode(),
                       "customer_tracker_full_filtered.csv", "text/csv")
    manual_entry_form(df)
