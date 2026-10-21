"""EventWatch customer complaints dashboard -- the entry point, and nothing else.

Configuration, the data load, the one shared filter set, navigation, and dispatch to a
page module. Every calculation lives in `dashboard/metrics.py`, every classification
wording in `dashboard/taxonomy.py`, every rendered component in
`dashboard/components.py`, and each page in `dashboard/pages/`.

This file was 3,389 lines. A number that appeared on two pages was computed twice, a
page could quietly grow its own filter, and finding the rule behind a figure meant
reading the whole application. The split is behaviour-preserving: no total, wording,
chart, filter or layout changed with it.

`dashboard/pages/` sits INSIDE the package on purpose. Streamlit auto-discovers a
`pages/` directory sitting next to the entry point and turns every file in it into a
page of its own, which would add a second navigation beside the one `PAGES` draws.
Inside the package it is an ordinary module directory and Streamlit never looks at it.
"""
from __future__ import annotations

import streamlit as st

from dashboard.config import APP_TITLE, PAGES

st.set_page_config(page_title="EventWatch Executive Dashboard", layout="wide",
                   initial_sidebar_state="expanded")

from dashboard.styles import CSS_BLOCKS
from dashboard.data import load_data
from dashboard.filters import sidebar_filters
from dashboard.staging import STAGED_FLAG, apply_staged
from dashboard.pages import analysis, executive_summary, records

for block in CSS_BLOCKS:
    st.markdown(block, unsafe_allow_html=True)

RENDERERS = {
    "Executive Summary": executive_summary,
    "All customer emails": records,
    "Analysis": analysis,
}
# Every name in PAGES needs a renderer and vice versa -- but this is NOT an assert any
# more, and the reason is a failure that took the deployed app down.
#
# `app.py` is the main script, so Streamlit re-reads it from disk on every rerun. The
# modules it imports are NOT re-imported: once `dashboard.config` is in `sys.modules`
# the process keeps the version it first loaded. After a Cloud hot update that pulls a
# commit changing both, this file is new and `config` is old -- so RENDERERS held the
# three current pages while PAGES still listed the seven it replaced, and the bare
# `assert` killed the page with a message Cloud redacts. A reader saw `AssertionError`
# and a line number, and nothing about why.
#
# Worse, it raised at this line -- ABOVE `load_data()`, which is where the build stamp
# draws. The one diagnostic built for exactly this situation could not reach the screen.
#
# `st.error` renders as an element rather than an exception, so Cloud shows the text
# instead of redacting it, and the string "could not be loaded" is already in
# `smoke_app.ERROR_TEXT` -- a genuine mismatch still fails the gate rather than being
# softened into a warning nobody reads.
if set(RENDERERS) != set(PAGES):
    # Read the stamp defensively: a process stale enough to cause this may predate
    # `build_note()` itself, and an ImportError here would replace a legible message
    # with a redacted one. This is the one place that trade is worth a local import.
    try:
        from dashboard.config import build_note
        stamp = build_note()[0]
    except Exception:
        stamp = "Build unknown."
    st.error(
        "**This app could not be loaded: its navigation and its page modules disagree.**\n\n"
        f"- Listed in `PAGES` with no renderer: `{sorted(set(PAGES) - set(RENDERERS)) or 'none'}`\n"
        f"- Renderers with no entry in `PAGES`: `{sorted(set(RENDERERS) - set(PAGES)) or 'none'}`\n"
        f"- {stamp}\n\n"
        "On Streamlit Cloud this nearly always means the process is running a mix of old "
        "and new code. `app.py` is re-read from disk on every rerun; modules it already "
        "imported are not. **Reboot the app** -- Manage app, then the three dots, then "
        "Reboot app -- and check the log shows a fresh `Starting up repository` line.\n\n"
        "If it survives a reboot that logged a real startup, this is a code fault and "
        "not staleness: every name in `PAGES` needs a renderer, and vice versa."
    )
    st.stop()

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

RENDERERS[selected_page].render(df, filtered, selected_page)
