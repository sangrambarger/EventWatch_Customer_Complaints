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
from dashboard.pages import (event_workload, executive_summary, monthly_trend, records,
                             root_cause, source_discovery, top_customers)

for block in CSS_BLOCKS:
    st.markdown(block, unsafe_allow_html=True)

RENDERERS = {
    "Executive Summary": executive_summary,
    "All customer emails": records,
    "Monthly trend": monthly_trend,
    "Root cause": root_cause,
    "Top customer complaints": top_customers,
    "DETAIL · Event workload": event_workload,
    "Dynamic Source Discovery": source_discovery,
}
assert set(RENDERERS) == set(PAGES), "every page in PAGES needs a renderer, and vice versa"

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
