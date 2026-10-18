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
from dashboard.metrics import MISS_BUCKETS, card_details, miss_by_customer, miss_categories, miss_owner_split, overview_split, trend_windows
from dashboard.components import add_rule, add_section, detail_panel, donut, downloads, excel_bar_table, kpis, page_header
from dashboard.sections import render_customers, render_event_types, render_monthly_volume, render_nature, render_root_cause



def _card_triggers(details, keys, row):
    """A quiet strip under each row of four cards, opening that card's own breakdown.

    A Streamlit widget cannot live inside the CSS grid `kpis()` draws, so the triggers
    are their own four-column row directly beneath it, styled to read as part of the
    cards rather than as a control bolted under them. The container carries a `key`, so
    the stylesheet matches `.st-key-kpi-more-N` -- a documented, stable class, not one
    of Streamlit's hashed emotion names that are rewritten between releases.

    A card whose payload the filter emptied (no account on the page, too few months to
    compare) gets a disabled strip rather than a button that opens an empty panel.
    """
    with st.container(key=f"kpi-more-{row}"):
        for column, key in zip(st.columns(4), keys):
            card = details.get(key)
            with column:
                if st.button("Break it down", key=f"kpi-more-{key}", disabled=card is None,
                             help=None if card else "Not enough data in this filter"):
                    # `medium`, not `large`: at large the panel stretches past 1200px and
                    # the gloss under each row runs to a line nobody tracks back to its
                    # start. The decorator is applied here rather than at module level
                    # so the dialog's title is the card's own eyebrow instead of one
                    # generic heading on all eight.
                    st.dialog(card["eyebrow"], width="medium")(lambda c=card: detail_panel(c))()


def render(df, filtered, selected_page):
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
    # Owner-based, NOT `bucket(MISS_BUCKETS[2][0])`. Reading one bucket meant the card
    # counted only the sub-types that rule happens to name, so a People miss whose
    # sub-type moved out of it -- `Prioritization` becoming `Published Late`, `Review`
    # becoming `Analyst Review Miss` -- silently left the summary while still being a
    # miss on every other page. "Captured, but an analyst did not raise it" is true of
    # every People-rooted miss by definition, so selecting on the owner is both the
    # honest reading of the card and the one a new sub-type cannot go stale against.
    overlooked = int((flag.eq("Yes") & page.get("Root Cause", pd.Series(dtype=str))
                      .astype(str).str.strip().eq("People")).sum())
    rate, band = trend_windows(page)
    accounts = miss_by_customer(page)
    biggest = accounts.sort_values("Emails", ascending=False).head(1)
    # Eight cards in two rows of four, not eight across: eight in one row is 180px each
    # at the width this is read at, and the number -- the only part anyone reads from
    # across a meeting room -- is the first thing to shrink. Every card prints its own
    # denominator inside the number, because a bare percentage beside a bare count on
    # one screen is what made the last read-out of this page unreadable.
    details = {c["key"]: c for c in card_details(page)}
    kpis([("Customer emails", len(page), f"{complaints} complaints · {inquiries} inquiries", "#8ab4f8"),
          ("Complaints", f"{complaints} of {len(page)}", f"{complaints / total * 100:.0f}% of these emails", "#f6c177"),
          ("Confirmed misses", f"{missed} of {len(page)}", f"{missed / total * 100:.0f}% of these emails", "#f28b82"),
          ("Complaints, not a miss", f"{not_a_miss} of {max(complaints, 1)}",
           "we did report it; the issue was something else", "#80cbc4")], columns=4)
    _card_triggers(details, ("emails", "complaints", "misses", "notamiss"), "1")
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
    _card_triggers(details, ("nevercaptured", "overlooked", "trend", "account"), "2")

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
