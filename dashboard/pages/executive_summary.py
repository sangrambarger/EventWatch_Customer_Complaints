"""Executive Summary -- The whole story in seven sections, in reading order."""
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

from dashboard.styles import ROOT_COLOURS, SPLIT_COLOURS
from dashboard.taxonomy import ROOT_OWNERSHIP, SPLIT_MEANING
from dashboard.filters import filter_note
from dashboard.metrics import _miss_parts, card_details, miss_owner_split, overview_split, trend_windows
from dashboard.components import add_rule, add_section, clickable_kpis, detail_panel, donut, downloads, excel_bar_table, kpis, page_header
from dashboard.sections import render_customers, render_event_types, render_monthly_volume, render_nature, render_root_cause



def _open_card(details, key):
    """Open one card's breakdown as a modal.

    `st.dialog` is applied here rather than at module level so the dialog's title is
    the card's own eyebrow instead of one generic heading on all eight, and
    `width="medium"`: at `large` the panel stretches past 1200px and the line of plain
    English under each row becomes one nobody tracks back to its start.
    """
    card = details[key]
    st.dialog(card["eyebrow"], width="medium")(lambda c=card: detail_panel(c))()


def render(df, filtered, selected_page):
    page_header(selected_page); page = filtered; filter_note()
    issue = page.get("Issue Type", pd.Series(dtype=str)).astype(str).str.strip()
    flag = page.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip()
    complaints = int(issue.eq("Complaint").sum()); inquiries = int(issue.eq("Inquiry").sum())
    total = max(len(page), 1)
    missed = int(flag.eq("Yes").sum())
    not_a_miss = int((issue.eq("Complaint") & flag.ne("Yes")).sum())
    # The three stages a missed event can stop at, from `_miss_parts()` -- the same
    # function the popups use, so a card and the panel it opens can never disagree.
    part = _miss_parts(page)
    never = int((part["source"] | part["keyword"]).sum())
    lost = int(part["platform"].sum())
    # Owner-based, NOT a bucket index. Reading one `MISS_BUCKETS` rule meant the card
    # counted only the sub-types that rule happens to name, so a People miss whose
    # sub-type moved out of it -- `Prioritization` becoming `Published Late`, `Review`
    # becoming `Analyst Review Miss` -- silently left the summary while still being a
    # miss on every other page. Every People-rooted miss is one an analyst had, by
    # definition, which is both the honest reading and the one a new sub-type cannot
    # go stale against.
    seen = int(part["analyst"].sum())
    rate, band = trend_windows(page)
    # Eight cards in two rows of four, not eight across: eight in one row is 180px each
    # at the width this is read at, and the number -- the only part anyone reads from
    # across a meeting room -- is the first thing to shrink. Every card prints its own
    # denominator inside the number, because a bare percentage beside a bare count on
    # one screen is what made the last read-out of this page unreadable.
    #
    # Row one is the funnel: what arrived, what was a complaint, what we got wrong.
    # Row two is where the misses stopped, and it carries ALL THREE stages. It used to
    # carry two of them and one account's share, so a reader adding 42 and 35 against a
    # headline of 86 came up nine short with nowhere to put them -- the stage where we
    # had the story and no person saw it had no card. The account card went to make
    # room: Ford's share is on card one's own panel and on Customers impacted below,
    # and a third telling of it is a third thing to reconcile.
    #
    # A line under the row printed `42 + 9 + 35 = 86` and the owner removed it. The
    # three stages still partition the misses -- `_miss_parts()` is what guarantees
    # that, not the caption -- and each card's own panel prints the equation for the
    # split it shows. What went is the restatement; do not read its absence as licence
    # to put a stage back that does not belong to the partition.
    # The whole card opens its own breakdown; there is no separate control. See
    # `clickable_kpis()` for why that is an overlaid button and not a link.
    details = {c["key"]: c for c in card_details(page)}
    opened = clickable_kpis([("Customer emails", len(page), f"{complaints} complaints · {inquiries} inquiries", "#8ab4f8"),
          ("Complaints", f"{complaints} of {len(page)}",
           f"{complaints / total * 100:.0f}% of what customers sent us", "#f6c177"),
          ("Confirmed misses", f"{missed} of {len(page)}",
           "we did not get the event to them in time", "#f28b82"),
          ("Complaints, not a miss", f"{not_a_miss} of {max(complaints, 1)}",
           "we did report it; something else was wrong", "#80cbc4")],
         ("emails", "complaints", "misses", "notamiss"), "1", available=set(details))
    # Both rows run every time. `opened = opened or clickable_kpis(...)` short-circuits:
    # when a top card returned a key, Python never evaluated the right-hand side, so the
    # second row of four was never drawn on that rerun and the bottom cards vanished the
    # moment a top card was clicked.
    second = clickable_kpis([("Never reached us", f"{never} of {max(missed, 1)}",
           "no source carried it, or our keywords missed it", "#8ab4f8"),
          ("Lost before an analyst", f"{lost} of {max(missed, 1)}",
           "we had the story and no person ever saw it", "#8ab4f8"),
          ("An analyst saw it", f"{seen} of {max(missed, 1)}",
           "a person had it, and it still did not go out", "#f28b82"),
          ("Last three months",
           f"{band['recent']['value']:.0f}%" if band else "—",
           (f"of emails were a miss, against {band['older']['value']:.0f}% in the three before"
            if band else "needs six months of emails to compare"), "#f6c177")],
        ("nevercaptured", "lostinside", "overlooked", "trend"), "2", available=set(details))
    opened = opened or second
    if opened:
        _open_card(details, opened)

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

    # The order is the owner's, and it is a reading order rather than a granularity one:
    # why we missed, who it hit, what kind of event, when it arrived, and last what the
    # customer themselves called it. A pure coarse-to-fine sort was tried and put
    # Customers impacted at the foot of the page on the width of its table; the owner's
    # call is that it is the section a reader comes here for, so it sits fourth, directly
    # under the failure analysis it belongs to. `render_deeper_root_cause` is NOT on this page --
    # it is the taxonomy at full depth and lives on Root cause, which already renders
    # the same function beneath this page's own root-cause block.
    add_rule()
    render_root_cause(page)

    add_rule()
    render_customers(page)

    add_rule()
    render_event_types(page)

    add_rule()
    # "Is it getting better?" (`render_trend`) was removed from THIS page on the owner's
    # call and stays on Monthly trend, which is the page for it. What sits here instead
    # is the volume block from that page -- the same function, so the two cannot drift.
    render_monthly_volume(page)

    add_rule()
    render_nature(page)
