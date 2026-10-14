"""The manual-entry form on All customer emails, and the session-scoped rows it stages.

Staged rows join the frame before filtering, so every page counts them without knowing
they exist. Staging is per browser session and never written to the tracker file.
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

from dashboard.config import CSV_NAME
from dashboard.components import styled_table



STAGED_FLAG = "_Staged"
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
