"""The one sidebar filter set, shared by every page.

Every page used to own a private date filter, so narrowing one page and opening another
silently compared different populations. `sidebar_filters()` is the single control now.
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

from dashboard.taxonomy import labels_for, reason_category




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
        keys = labels_for(frame, col)
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
    # Counted off session state before the widgets render, which is accurate only
    # because the options above are stable: when a list cascaded, a selection could be
    # dropped during the render while session state still held it, so the label read
    # "1 active" over a filter that was no longer filtering anything.
    active = sum(1 for k in FILTER_KEYS if st.session_state.get(k))
    label = f"Filters ({active} active)" if active else "Filters"
    with st.sidebar.expander(label, expanded=bool(active)):
        for name, kind, col in FILTERS:
            if col not in out.columns:
                continue
            if kind == "customer":
                # Customer is the one column whose cells can name more than one account.
                vals = customer_names(df[col])
                chosen = st.multiselect(name, vals, key=f"filter_{name}")
                if chosen:
                    out = out[names_match(out[col], chosen)]
                continue
            # Options come from `df`, the WHOLE frame, and never from `out`, which the
            # filters above have already narrowed. Reading them off `out` made the list
            # cascade, and a cascading list silently throws away a selection the reader
            # has already made: pick Event type = Factory Fire, then change Customer to
            # an account with no fire, and Factory Fire is no longer among the options,
            # so Streamlit drops it from the widget without a word. The chip vanishes,
            # the narrowing stops applying, and the click reads as "nothing happened".
            # That is the whole of the "I had to keep refreshing" symptom.
            #
            # The cost of a stable list is that a reader can now choose a combination
            # that matches nothing. `filter_note()` already prints the surviving count
            # at the top of every page, so an empty page reads as a filter choice rather
            # than a broken dashboard -- which is exactly why that line exists.
            vals, _ = filter_values(df, kind, col)
            chosen = st.multiselect(name, vals, key=f"filter_{name}")
            if chosen:
                _, keys = filter_values(out, kind, col)
                out = out[keys.isin(chosen)]
        q = st.text_input("Search all fields")
        if q:
            out = out[out.astype(str).apply(lambda r: r.str.contains(q, case=False, na=False).any(), axis=1)]
    return out
