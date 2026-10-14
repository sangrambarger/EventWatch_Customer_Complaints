"""Loading the tracker, and the three places it may come from.

`data_sources()` resolves secrets, then the files beside the entry point, then a raw
GitHub URL. `smoke_app.py` writes no secrets on purpose, so it exercises the middle path.
"""
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

from dashboard.config import APP_DIR, CSV_NAME, WORKBOOK_NAME




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
