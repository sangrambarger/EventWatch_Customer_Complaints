"""Executive Summary -- the story in seven sections, in reading order.

Two sections left on the owner's call and neither was replaced, because both were
saying something the page already said:

* **The two donuts** ("What customers sent us"). The left ring was the three-way
  split of the inbox, which the first row of cards prints as four figures with their
  bases; the right ring was the misses by owner, which the month chart below segments
  month by month and the root-cause cards state with their shares. Three tellings of
  one split. `overview_split()`, `miss_owner_split()`, `donut()`, `SPLIT_COLOURS` and
  `SPLIT_MEANING` went with it.
* **Nature of complaints** moved to Analysis, unchanged. It is the customer's own
  vocabulary folded onto the reason categories -- the thing a reader looks up when a
  figure surprises them, which is what Analysis is for, and not a thing a VP reads
  month by month.

Nothing was deleted to make the page shorter. The test applied to both was the one
`insights()` failed: a block that restates the page in different words is a block a
reader has to reconcile against the one above it.
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

from dashboard.filters import filter_note
from dashboard.metrics import card_details, inbox_rings, inbox_totals, trend_windows
from dashboard.components import add_rule, add_section, clickable_kpis, detail_panel, nested_donut, page_header
from dashboard.sections import render_customers, render_event_types, render_monthly_breakdown, render_root_cause, render_trend



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
    # One call, and the cards below are drawn from it as well as the two rings under
    # them.
    # These eight figures used to be computed inline here; a chart recomputing them
    # beside the cards would be a second implementation of the page's own headline
    # numbers, waiting to disagree with the first.
    f = inbox_totals(page)
    complaints, inquiries = f["complaints"], f["inquiries"]
    total = max(f["emails"], 1)
    missed, not_a_miss = f["missed"], f["wrong"]
    # The three stages a missed event can stop at, from `_miss_parts()` by way of
    # `inbox_totals()` -- the same `_miss_parts()` the popups use, so a card, the panel
    # it opens and the rings under it can never disagree.
    never, lost = f["never"], f["lost"]
    # Owner-based, NOT a bucket index. Reading one `MISS_BUCKETS` rule meant the card
    # counted only the sub-types that rule happens to name, so a People miss whose
    # sub-type moved out of it -- `Prioritization` becoming `Published Late`, `Review`
    # becoming `Analyst Review Miss` -- silently left the summary while still being a
    # miss on every other page. Every People-rooted miss is one an analyst had, by
    # definition, which is both the honest reading and the one a new sub-type cannot
    # go stale against.
    seen = f["seen"]
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
    opened = clickable_kpis([("Customer emails", f["emails"], f"{complaints} complaints · {inquiries} inquiries", "#8ab4f8"),
          ("Complaints", f"{complaints} of {f['emails']}",
           f"{complaints / total * 100:.0f}% of what customers sent us", "#f6c177"),
          ("Confirmed misses", f"{missed} of {f['emails']}",
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

    # The eight cards above are three nested splits, and the nesting is the part they
    # cannot show. **Two nested rings, side by side, and the three forms tried before
    # them are all recorded because each failed differently.** Three left-aligned
    # stacked bars were called a funnel and were a bar chart named after one: the join
    # between levels was real but implicit, something to be noticed rather than drawn.
    # A Sankey drew the join honestly and the owner's verdict, twice, was that it was
    # not worth looking at. A SINGLE donut was rejected on the arithmetic -- a ring
    # draws one whole split into parts, and this is three wholes nested inside each
    # other.
    #
    # **Two rings of two levels each is what covers the three levels.** Containment is
    # the join: 86 and 17 sit bodily inside the 103 beneath them, so nothing has to be
    # added up and nothing has to be spotted. The one join a reader still makes by hand
    # is between the rings, which is why the second ring's centre prints the first
    # ring's outer slice in words.
    rings = inbox_rings(f)
    add_section("How the numbers above fit together", "", "#8ab4f8")
    left, right = st.columns(2)
    with left:
        nested_donut(rings[0])
    with right:
        nested_donut(rings[1])
    # The equations are a caption and not a chart label, for the reason the card row's
    # own `42 + 9 + 35 = 86` line was removed: a line of bare arithmetic restating the
    # picture is the thing the picture failed to be. Here it is the receipt -- the rings
    # are what a reader reads, and this is what `audit_pages.py` checks them against.
    st.caption(f"**Every slice is a figure on a card above.** {rings[0]['equation']} "
               f"{rings[1]['equation']}")
    add_rule()
    # Section 2 on the owner's call, and the block this page is read for. "Is it
    # getting better?" (`render_trend`) left for Monthly trend and was deleted with it;
    # the replacement is an arrow above this chart that moves only when a month is
    # outside normal variation, not a percentage that wobbles every month.
    # `clickable` is still passed explicitly rather than defaulted: the chart's widget
    # key is one piece of session state and exactly one page may own it.
    render_monthly_breakdown(page, clickable=True)

    # The order is the owner's, and it is a reading order rather than a granularity one:
    # what arrived and when it failed, why we missed, who it hit, and what kind of event
    # it was. A pure coarse-to-fine sort was tried and put
    # Customers impacted at the foot of the page on the width of its table; the owner's
    # call is that it is the section a reader comes here for, so it sits fourth, directly
    # under the failure analysis it belongs to. `render_deeper_root_cause` is NOT on this page --
    # it is the taxonomy at full depth and lives on Root cause, which already renders
    # the same function beneath this page's own root-cause block.
    add_rule()
    # The one question a VP asks monthly, and until now the only view of it was a
    # percentage printed on top of each bar of the chart above -- ten numbers for the
    # reader to compare in their head. It is the dashboard's first time-series chart.
    render_trend(page)

    add_rule()
    render_root_cause(page)

    add_rule()
    render_customers(page)

    add_rule()
    render_event_types(page)
