"""The Executive Summary's sections, as functions the internal pages call too.

This is what stops the summary and Analysis drifting: Analysis runs the summary's own
`render_root_cause()`, `render_deeper_root_cause()` and `render_customers()`, so there
is one implementation of each rather than two that agree today. It mattered more when
seven pages shared these; at three pages the rule is the same and the surface is
smaller.
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

from dashboard.styles import CAT_SLATE, ROOT_COLOURS, esc
from dashboard.taxonomy import ROOT_OWNERSHIP, name_subtypes, plural
from dashboard.filters import customer_names, filter_note, names_match
from dashboard.metrics import MISS_BUCKETS, account_failures, bulletin_errors, account_headline, count_table, customer_totals, driver_table, event_type_flow, miss_by_customer, miss_categories, miss_colours, miss_trend, monthly_breakdown, monthly_note, monthly_table, nature_table, owner_accounts, owner_insight, root_drivers, root_frame, root_recent_note, root_summary, subtype_matrix, takeaway, trend_note, trend_windows
from dashboard.components import add_section, chart, downloads, driver_bar, fault_pills, excel_bar_table, flow_bar, grouped_bar, heatmap, kpis, monthly_stack, page_header, proportion_bar, stacked_bar, styled_table, trend_line




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
        failures = name_subtypes(count_table(root_df, "Sub-type"), root=root)
        excel_bar_table(failures, "Sub-type", label_head="Tracker value", value_head="Emails",
                        extras=["What it means", "Complaints", "Inquiries", "Misses",
                                "Reported timely"],
                        wrap=["What it means"], variant="wide roomy",
                        caption="**Emails = Confirmed misses + Reported timely** on every row.")
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


def source_page(title, df, col, key, primary=None, summary=True, header=True):
    """`primary` overrides how the main table is counted -- Customer needs a counter that
    credits every account named in a multi-customer row, not the whole string.

    `summary=False` drops the generic count-table-and-chart pair at the top. Where a
    page now renders the Executive Summary's own block for the same dimension, that pair
    was the same numbers a second time in weaker words, and two tables of one thing on
    one page is exactly the repetition this dashboard is being cleaned of.

    `header=False` suppresses the page heading and the filter line. Analysis calls this
    twice -- once for the Root Cause blocks and once for the Customer blocks -- and a
    page may only have one heading. It also fixes a real defect: the Root cause page
    called `render_root_cause()` before `source_page()`, so its own heading rendered
    three hundred lines down the page, under the section it was supposed to introduce.
    """
    if header:
        page_header(title); filter_note()
    page = df; label = col.replace("Standard Automation Focus", "Automation focus")
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


def _open_month(page, frame, month):
    """One month's own root-cause breakdown, in the figure the summary already draws.

    `width="large"` is a deliberate departure. Every other dialog here is `medium`,
    because at `large` a line of prose stretches past 1200px and nobody tracks it back
    to its start -- but this panel is cards and bars, which have no such problem, and
    two owner cards with their driver charts do not fit 700px.
    """
    part = page[page["Month Label"].astype(str) == month]
    if part.empty:
        return
    row = frame[frame["Month"] == month]
    head = ""
    if not row.empty:
        r = row.iloc[0]
        head = (f"<div class='pop-chain'><span>{int(r['Emails'])} emails</span> "
                f"<span class='pop-sep'>&rsaquo;</span> <span>{int(r['Complaints'])} complaints</span> "
                f"<span class='pop-sep'>&rsaquo;</span> <span class='pop-here'>"
                f"{int(r['Misses'])} misses</span></div>")
        # `plural()` for the same reason the driver hovers use it: a leadership panel
        # does not print "1 complaints".
        foot = (plural(int(r["Wrong"]),
                       "other complaint was reported in time with something wrong on it",
                       "other complaints were reported in time with something wrong on them")
                + ", and "
                + plural(int(r["Inquiries"]), "email was an inquiry", "emails were inquiries") + ".")

    def panel():
        if head:
            st.markdown(head, unsafe_allow_html=True)
        render_root_tier(part)
        if head:
            st.caption(foot)

    st.dialog(month, width="large")(panel)()


def render_monthly_breakdown(page, clickable=False):
    """Month by month: what came in, and where it failed.

    The Executive Summary is now its only caller -- Monthly trend drew it too until
    that page was cut -- so `clickable` has only one answer today. The parameter stays:
    it is what keeps the chart's widget key owned by exactly one page, and the day a
    second page draws these months that constraint is the whole of why it exists.

    It replaced a grouped complaint-against-inquiry pair that was volume only -- how
    many arrived, nothing about how many we got wrong, which is the whole of what a VP
    asks this block for. The bar now carries the failure split and the table carries it
    with both bases beside it.

    **`clickable` belongs to the page, not to the block.** Only one page may own the
    chart's widget key, or Streamlit hands both pages one piece of selection state and
    a month opened on one opens again on the other. The Executive Summary owns it; any
    future caller draws the same chart without the click.

    No descriptive paragraph under the heading, on the owner's call. The one line under
    the table is the hierarchy, which is a reconciliation rather than commentary: it is
    what stops a reader adding Complaints to Misses.
    """
    frame = monthly_breakdown(page)
    if frame.empty:
        st.info("Monthly breakdown requires Month/Reporting Month and Issue Type fields.")
        return
    add_section("Month by month: what came in, and where it failed", "", "#80cbc4")
    fig, month = monthly_stack(frame, key="monthly-stack" if clickable else None)
    table = monthly_table(frame)
    # A scroll box, not an expander. A collapsed expander lays out at zero height, so
    # `innerText` reads empty and `audit_pages.py` silently stops reconciling every row
    # it hides -- eleven rows and the Total among them. The box keeps the table in the
    # DOM, the sticky foot keeps the Total on screen, and the gate keeps working.
    #
    # `nowrap` on Month: a full-width table wrapped "Jan 2026" onto two lines and
    # doubled the height of every row.
    with st.expander("Show the numbers"):
        styled_table(table, variant="roomy stickytotal", height=420, total_row=True,
                     styles={"Month": "nowrap"})
    st.caption(monthly_note(frame))
    downloads(table, "monthly_breakdown", fig)
    # Open only on the run where the selection CHANGES, and never on a rerun that
    # merely inherits it.
    #
    # A plotly selection is sticky: `st.plotly_chart(on_select="rerun")` goes on
    # reporting the clicked month on every later rerun, for the life of the session.
    # So a month clicked once and then any card clicked afterwards opened two dialogs
    # in a single script run -- and Streamlit permits exactly one, raising
    # `StreamlitInvalidLayoutContextError: Only one dialog is allowed to be opened at
    # the same time`. That took the whole Executive Summary down, because the raise
    # happens inside `render()` and nothing below it draws.
    #
    # Remembering the month we last acted on fixes both halves: at most one dialog per
    # run (one widget reports one interaction, so the card and the chart can no longer
    # both fire), and a dismissed dialog stays dismissed instead of re-opening on the
    # next filter change. `None` is stored too, so clearing the selection re-arms the
    # same month for a second click.
    shown = "monthly-stack-opened"
    if clickable and month != st.session_state.get(shown):
        st.session_state[shown] = month
        if month:
            _open_month(page, frame, month)


def render_root_tier(page):
    """The owner cards and their driver bars -- the top tier of the root-cause block.

    Split out of `render_root_cause()` so the month dialog can draw the same thing for
    one month. It is the figure the owner asked that dialog to look like, and the only
    honest way to make a popup look like a page is to run the page's own code: a second
    implementation of these cards would be a second set of numbers waiting to disagree.
    """
    roots = root_summary(page)
    if not roots:
        st.info("No email in this view is flagged as a confirmed miss.")
        return
    missed = int(page.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes").sum())
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
    add_section("Why the events were missed", "", "#f28b82")
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
        render_root_tier(page)
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
        with st.expander("Show the numbers"):
            excel_bar_table(drivers, "Driver", value_col="Misses",
                            extras=["Owner", "What it means"], label_head="Failure driver",
                            value_head="Confirmed misses", variant="wide roomy",
                            wrap=["What it means"], raw=["Owner"], classes={"Owner": "owners"},
                            caption="Every driver behind the cards above, biggest first.")
        downloads(drivers, "miss_drivers")


def render_bulletin_errors(page):
    """The other half of the 103: complaints where the bulletin went out and was wrong.

    **"Why the events were missed" covers 86 records and stops.** The 17 complaints
    where the event DID reach the customer in time had no block of their own and
    appeared only behind a click on the fourth KPI card. Together the two sections are
    every complaint, which is why the caption prints the join rather than leaving a
    reader to subtract: `86 + 17 = 103`.

    **It is pills, not bars**, for the reason set out on `fault_pills()`. The failure
    names carry the short vocabulary -- `Incorrect geocode`, `Incorrect suppliers
    selected`, `Duplicate bulletins` -- and the sentence that used to be the label is
    the hover. `WRONG_GROUPS` is the one fold, shared with the card popup, so the 17
    cannot be told two different ways on one page.

    The accent is `CAT_SLATE` and not an owner hue, because these 17 are 9 Product,
    7 People and 1 Process -- the rule every mixed category here is held to.
    """
    data = bulletin_errors(page)
    add_section("Errors in the bulletins we sent", "", CAT_SLATE)
    if not data["total"]:
        st.info("No complaint in the current filter was reported and then found wrong.")
        return
    missed = int(page.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes").sum())
    n = data["total"]
    pills = data.get("pills", n)
    shared = pills - n
    extra = (f" Two account names on one email means two pills, so {pills} pills cover "
             f"{n} complaints." if shared else "")
    st.markdown(
        f"<div class='insight-box' style='--accent:{CAT_SLATE}'>"
        f"<b style='color:var(--ink)'>{n} complaints.</b> The event reached the customer "
        f"in time and the bulletin itself was wrong. One pill is one account on one "
        f"complaint; hover it for the date, the ticket and what went wrong.{extra} "
        f"<b style='color:var(--ink)'>{missed} missed + {n} wrong = {missed + n} "
        f"complaints.</b></div>", unsafe_allow_html=True)
    fault_pills(data["groups"], [(k, ROOT_COLOURS[k]) for k in ("Product", "People", "Process")])
    table = data["rows"].rename(columns={"Email/JIRA Date": "Date", "Failure": "What was wrong",
                                         "Owner": "Who fixes it"})[
        ["Date", "Customer", "What was wrong", "Who fixes it", "What happened"]]
    with st.expander("Show the numbers"):
        styled_table(table, variant="wide roomy", wrap=["What happened"])
    downloads(table, "bulletin_errors")


def render_customers(page):
    """Customers impacted: the stacked bar and every account, with reconciled totals."""
    accounts = miss_by_customer(page)
    cats = miss_categories(page)
    add_section("Customers impacted", "", "#f6c177")
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
        with st.expander("Show the numbers"):
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
    """Event types: one chart in the month chart's grammar, and one table under it."""
    add_section("Complaints by event type", "", "#f28b82")
    flow = event_type_flow(page)
    if flow.empty:
        st.info("No email in the current filter carries an event type.")
    else:
        # ONE chart, not two. This was a ranked bar of every email beside a ranked bar of
        # the confirmed misses -- the same twenty-odd labels down both axes in two
        # different orders, leaving the reader to join "nine misses" to "sixteen emails"
        # themselves. The page's owner said the block confused them, which is the right
        # reading of two rankings of one population drawn as though they were a
        # comparison.
        f_flow = flow_bar(flow, "Event type", x_title="Customer emails")
        # The table is the SAME columns the month table prints, from the same function.
        # It used to carry `Complaints / Inquiries / Emails / Misses` under a chart split
        # `Product / Analyst / Process / Wrong / Inquiry` -- a chart and the table beneath
        # one heading saying two different things, which is the fault this file keeps
        # recording. A reader who has learned the month block has now learned this one.
        table = monthly_table(flow, label_col="Event type")
        if not table.empty:
            with st.expander("Show the numbers"):
                excel_bar_table(table, "Event type", value_col="Misses",
                                extras=[c for c in table.columns
                                        if c not in ("Event type", "Misses")],
                                label_head="Event type", value_head="Confirmed misses",
                                variant="roomy", total_row=False, classes={"Event type": "nowrap"},
                                caption=monthly_note(flow, unit="event type"))
            downloads(table, "event_types", f_flow)


def _volume_caveat(trend):
    """Say when the test can only ever fire one way, and why.

    Three sigma above a ~68% base rate lands past 100% on a month of 4 to 19 emails, so
    the upper limit is the ceiling and no month can register as WORSE however badly it
    runs. A reader watching an arrow that only ever points down deserves to be told that
    rather than left to infer it, and a dashboard that quietly runs a one-sided test is
    the kind of thing this file exists to prevent. Computed, so it corrects itself the
    month volumes grow enough to make the test two-sided again.
    """
    pinned, span = trend.get("pinned", 0), trend.get("span", 0)
    if not span or not pinned:
        return ""
    if pinned == span:
        return ("**One limit only:** at this many emails a month the band reaches 100%, so "
                "it can flag an improvement but never a worsening.")
    return (f"**One limit only on {pinned} of {span} months:** their band reaches 100%, so "
            f"for those it can flag an improvement but never a worsening.")


def render_trend(page):
    """Is it getting better: the verdict, the months, and the numbers behind them."""
    trend = miss_trend(page)
    latest = trend.get("latest")
    arrow = {"worse": ("▲", "#f28b82"), "better": ("▼", "#a8dab5")}.get(
        (latest or {}).get("direction", "flat"), ("▬", "#8a94a8"))
    add_section("Is it getting better", "", "#8ab4f8")
    if latest:
        # The arrow and one sentence are the whole answer for a reader who stops here.
        st.markdown(
            f"<div style='display:flex;align-items:baseline;gap:14px;margin:2px 0 10px'>"
            f"<span style='font-size:42px;line-height:1;color:{arrow[1]}'>{arrow[0]}</span>"
            f"<span style='font-size:15px;color:#b6beca'>{esc(trend_note(trend))}</span>"
            f"</div>", unsafe_allow_html=True)
    trend_line(trend)
    # **One sentence teaches the whole chart.** A control chart is unreadable to anyone
    # who has not met one, and the owner said so: they did not understand the timeline.
    # This says what the band is for in the words a reader already has, and says nothing
    # about sigma, pooling or p-charts -- that reasoning is in CLAUDE.md, where the next
    # person to change the threshold will look for it.
    st.caption("The shaded band is how much this number normally bounces about. "
               "A month inside it means nothing changed; only a month outside is news. "
               + _volume_caveat(trend))
    months = trend["months"]
    if not months.empty:
        table = months[["Month", "Emails", "Misses", "Rate"]].copy()
        table.columns = ["Month", "Emails", "Confirmed misses", "Miss rate"]
        table["Miss rate"] = table["Miss rate"].map(lambda v: f"{v:.0f}%")
        with st.expander("Show the numbers"):
            excel_bar_table(table, "Month", value_col="Confirmed misses",
                            extras=["Emails", "Miss rate"], label_head="Month",
                            value_head="Confirmed misses", variant="roomy", total_row=False)


def render_nature(page):
    """Nature of complaints: the seven categories, split on whether we got it wrong."""
    missed = int(page.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes").sum())
    add_section("Nature of complaints", "", "#8ab4f8")
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
        with st.expander("Show the numbers"):
            excel_bar_table(nature, "Category", label_head="What they wrote about",
                            value_head="Emails", variant="wide roomy",
                            extras=["What it means", "Complaints", "Inquiries", "Misses",
                                    "Reported timely"],
                            wrap=["What it means"],
                            caption="**Emails = Confirmed misses + Reported timely** on every row.")
        top = split.sort_values("Misses", ascending=False)
        others = top[top["Category"] != "Event missed"]
        elsewhere = int(others["Misses"].sum())
        named = ", ".join(f"{int(r['Misses'])} {r['Category'].lower()}"
                          for _, r in others[others["Misses"] > 0].iterrows())
        here = int(top.loc[top["Category"] == "Event missed", "Misses"].sum())
        st.caption(
            f"**{here} + {elsewhere} = {here + elsewhere}.** Event missed carries {here}, not "
            f"the {missed} in this filter: this counts what the customer wrote about, the miss "
            f"count counts whether the event reached them in time. The other {elsewhere} are "
            f"{named}.")
        downloads(split, "nature_of_complaints", f_nature)


def render_deeper_root_cause(page):
    """The deeper root cause: every failure with both bases and its owner."""
    add_section("The deeper root cause", "", "#f28b82")
    roots = root_frame(page)
    if roots.empty:
        st.info("No email in the current filter carries a root cause.")
    else:
        f_root = grouped_bar(roots, "What went wrong", ["Emails", "Misses"],
                             {"Emails": "#b6beca", "Misses": "#f28b82"},
                             title="Every failure: emails raised, and how many were confirmed misses")
        with st.expander("Show the numbers"):
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
