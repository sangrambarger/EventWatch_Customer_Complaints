"""All customer emails -- Every customer email, the vocabulary behind it, and the staging form."""
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

from dashboard.styles import GRID_STYLES, WRAP_COLUMNS
from dashboard.taxonomy import DISPLAY_NAMES, TRACKER_COLUMNS, reason_category, with_failure_label, with_reason_category
from dashboard.filters import filter_note
from dashboard.metrics import category_table, inquiry_table, record_labels
from dashboard.components import add_section, cell, downloads, kpis, page_header, styled_table
from dashboard.staging import STAGED_FLAG, manual_entry_form



def render(df, filtered, selected_page):
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
