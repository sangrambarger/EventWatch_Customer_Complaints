"""The Executive Summary's sections, as functions the internal pages call too.

This is what stops the summary and an internal page drifting: Monthly trend runs
`render_trend()`, Root cause runs `render_deeper_root_cause()`, and there is one
implementation of each rather than two that agree today.
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

from dashboard.styles import esc
from dashboard.taxonomy import ROOT_OWNERSHIP, name_subtypes, plural
from dashboard.filters import customer_names, filter_note, names_match
from dashboard.metrics import MISS_BUCKETS, account_failures, account_headline, all_event_types, count_table, customer_totals, driver_table, event_type_note, event_type_pairs, miss_by_customer, miss_categories, miss_colours, missed_event_types, missed_verdict, nature_table, owner_accounts, owner_insight, root_drivers, root_frame, root_recent_note, root_summary, subtype_matrix, takeaway, trend_table, trend_windows
from dashboard.components import add_section, chart, downloads, driver_bar, excel_bar_table, grouped_bar, heatmap, kpis, page_header, proportion_bar, stacked_bar, styled_table, trend_chart




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
                        caption="Every row adds up: **Emails = Confirmed misses + Reported "
                                "timely.** Tracker value is the Sub-type on the record; "
                                "What it means is the same failure in the words the rest of "
                                "the dashboard uses.")
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


def source_page(title, df, col, key, primary=None, summary=True):
    """`primary` overrides how the main table is counted -- Customer needs a counter that
    credits every account named in a multi-customer row, not the whole string.

    `summary=False` drops the generic count-table-and-chart pair at the top. Where a
    page now renders the Executive Summary's own block for the same dimension, that pair
    was the same numbers a second time in weaker words, and two tables of one thing on
    one page is exactly the repetition this dashboard is being cleaned of.
    """
    page_header(title); page = df; filter_note(); label = col.replace("Standard Automation Focus", "Automation focus")
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


def render_monthly_volume(page):
    """Complaint and inquiry volume by month: the source table and the grouped bars.

    On the Executive Summary and on Monthly trend, from one function, for the same
    reason every other shared block is: two pages drawing the same months from two
    copies is how they end up disagreeing. It carries no miss rate -- that is
    `render_trend()`, which lives on Monthly trend alone.
    """
    if "Month Label" not in page.columns or "Issue Type" not in page.columns:
        st.info("Monthly volume requires Month/Reporting Month and Issue Type fields.")
        return
    monthly = page.groupby("Month Label", dropna=False)["Issue Type"].value_counts().unstack(fill_value=0).reset_index()
    monthly["Month Date"] = pd.to_datetime(monthly["Month Label"], format="%b %Y", errors="coerce")
    monthly = monthly.sort_values("Month Date")
    monthly["Total"] = monthly.drop(columns=["Month Label", "Month Date"]).sum(axis=1)
    display_monthly = monthly.drop(columns=["Month Date"], errors="ignore")
    add_section("Monthly breakdown of all customer emails", "Complaint and inquiry counts "
                "by reporting month, in calendar order. This is volume only — how many "
                "emails arrived, not how many of them we got wrong.", "#80cbc4")
    fig = px.bar(monthly, x="Month Label", y=[c for c in ["Complaint", "Inquiry"] if c in monthly.columns],
                 barmode="group", text_auto=True, color_discrete_sequence=["#8ab4f8", "#80cbc4"])
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=13), margin=dict(l=20, r=30, t=30, b=40),
                      height=430, legend_title_text="")
    fig.update_xaxes(categoryorder="array", categoryarray=monthly["Month Label"].tolist(),
                     tickfont=dict(color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_yaxes(tickfont=dict(color="#f3f4f6"), gridcolor="#303846", title="Customer emails")
    st.plotly_chart(fig, width="stretch")
    styled_table(display_monthly, total_row=True)
    downloads(display_monthly, "monthly_volume", fig)


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
    add_section("Why the events were missed", "Two tiers. The cards are the three root causes the "
                "tracker records, with who owns each one; under each card sit that root cause's "
                "biggest failure drivers, in EventWatch's own terms — hover any bar for what the "
                "term means. Everything is keyed on the Root Cause and Sub-type fields on the "
                "record, never on how the customer worded it, and a pair that does not map to a "
                "known driver is shown as Needs Review rather than talked into the nearest "
                "heading.", "#f28b82")
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
        excel_bar_table(drivers, "Driver", value_col="Misses",
                        extras=["Owner", "What it means"], label_head="Failure driver",
                        value_head="Confirmed misses", variant="wide roomy",
                        wrap=["What it means"], raw=["Owner"], classes={"Owner": "owners"},
                        caption="Every driver behind the three cards above, biggest first. "
                                "Owner is the root cause on the record itself, so a driver "
                                "that occurs under two owners shows both with their counts "
                                "rather than being filed under whichever is larger.")
        downloads(drivers, "miss_drivers")


def render_customers(page):
    """Customers impacted: the stacked bar and every account, with reconciled totals."""
    accounts = miss_by_customer(page)
    cats = miss_categories(page)
    add_section("Customers impacted", "Every account in the filter. Emails is every email that named "
                "the account, complaints and inquiries together; the columns after it count only the "
                "confirmed misses, split by what failed. Both bases sit on the row, because 44 on its "
                "own does not say 44 of what. Accounts are split on the slash, so an email naming two "
                "of them appears on both rows — the rows therefore add to more than the tracker holds, "
                "and the Total row is the distinct count, not the column sum.", "#f6c177")
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
    """Event types: every email, the confirmed misses, and one table carrying both."""
    add_section("Complaints by event type", "What kind of event customers write to us about. "
                "The left chart is every email they sent; the right one is only the confirmed "
                "misses, because nine misses is a different fact depending on whether ten "
                "emails named that event type or forty. The table underneath carries one "
                "split and one subset, and says which is which.", "#f28b82")
    types, everything = missed_event_types(page), all_event_types(page)
    if types.empty and everything.empty:
        st.info("No email in the current filter carries an event type.")
    else:
        left, right = st.columns(2)
        with left:
            st.markdown("**Every email, by event type**")
            f_all = chart(everything, "Event type", title="", x_title="Customer emails") \
                if not everything.empty else None
        with right:
            st.markdown("**Only the confirmed misses**")
            f_types = chart(types, "Event type", title="", x_title="Confirmed misses") \
                if not types.empty else None
        pairs = event_type_pairs(page)
        if not pairs.empty:
            excel_bar_table(pairs, "Event type", value_col="Misses",
                            extras=["Complaints", "Inquiries", "Emails"],
                            label_head="Event type", value_head="Confirmed misses",
                            variant="roomy",
                            caption="**Emails = Complaints + Inquiries** on every row. "
                                    "**Confirmed misses counts only the complaints where the "
                                    "event never reached the customer in time** — it is a "
                                    "subset of the complaints column, not a third part of the "
                                    "split. " + event_type_note(page))
            downloads(pairs, "event_types", f_types or f_all)


def render_nature(page):
    """Nature of complaints: the seven categories, split on whether we got it wrong."""
    missed = int(page.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes").sum())
    add_section("Nature of complaints", "What the customer actually wrote about, folded onto the "
                "eight categories the All customer emails tab defines. Each bar is split: the "
                "darker part is the emails in that category that turned out to be a confirmed "
                "miss, the lighter part the ones where the event did reach them. That split is "
                "the answer to the question this block always raised — why the Event missed row "
                "does not equal the miss count at the top of the page.", "#8ab4f8")
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
        excel_bar_table(nature, "Category", label_head="What they wrote about",
                        value_head="Emails", variant="wide roomy",
                        extras=["What it means", "Complaints", "Inquiries", "Misses",
                                "Reported timely"],
                        wrap=["What it means"],
                        caption="Every row adds up: **Emails = Confirmed misses + Reported "
                                "timely.** The same categories, with the same meanings, are "
                                "listed on All customer emails with every customer wording "
                                "folded into each one.")
        top = split.sort_values("Misses", ascending=False)
        others = top[top["Category"] != "Event missed"]
        elsewhere = int(others["Misses"].sum())
        named = ", ".join(f"{int(r['Misses'])} {r['Category'].lower()}"
                          for _, r in others[others["Misses"] > 0].iterrows())
        here = int(top.loc[top["Category"] == "Event missed", "Misses"].sum())
        st.caption(
            f"**Event missed carries {here} confirmed misses, not the {missed} on the cards "
            f"above, and that is not an error.** This column counts what the customer wrote "
            f"about; the miss count counts whether the event reached them in time. The other "
            f"{elsewhere} confirmed miss(es) sit in categories where the event was reported and "
            f"something else went wrong — {named}. "
            f"{here} + {elsewhere} = {here + elsewhere}.")
        downloads(split, "nature_of_complaints", f_nature)


def render_trend(page):
    """Is it getting better: the verdict sentence, the monthly bars and the table."""
    rate, band = trend_windows(page)
    add_section("Is it getting better?", "One bar per month: the share of that month's emails that "
                "turned out to be a confirmed miss, with its percentage printed on it. The last "
                "three months are blue and the three before them grey, and the sentence above the "
                "chart states the comparison rather than leaving it to be read off the bars. Both "
                "figures are pooled on counts, so a month with four emails does not weigh the same "
                "as one with eighteen.", "#f6c177")
    if rate.empty:
        st.info("No dated email in the current filter.")
    else:
        verdict = missed_verdict(rate)
        if verdict:
            headline, detail, colour, _ = verdict
            st.markdown(f"<div class='insight-box' style='--accent:{colour}'>"
                        f"<b style='color:{colour}'>{esc(headline)}.</b> {esc(detail)}</div>",
                        unsafe_allow_html=True)
        f_rate = trend_chart(rate, band, title="Confirmed misses as a share of each month's emails")
        months = trend_table(rate, band)
        styled_table(months, total_row=True)
        if band:
            st.caption(f"The comparison rests on {band['older']['emails']} emails and "
                       f"{band['recent']['emails']} emails. A single thin month moves it several "
                       f"points, so read it as a direction rather than a result.")
        else:
            st.caption("Fewer than six months of emails in this filter — too short to compare two windows.")
        downloads(months, "missed_event_rate", f_rate)


def render_deeper_root_cause(page):
    """The deeper root cause: every failure with both bases and its owner."""
    add_section("The deeper root cause", "Every failure in the taxonomy, in plain words, with the "
                "tracker's own value beside it in the table. Two bars on each row: how many emails "
                "named that failure at all, and how many of those we confirmed as a miss — so a "
                "failure we mostly get away with is told apart from one that costs us every time. "
                "Nothing is folded into an Other, however few emails carry it.", "#f28b82")
    roots = root_frame(page)
    if roots.empty:
        st.info("No email in the current filter carries a root cause.")
    else:
        f_root = grouped_bar(roots, "What went wrong", ["Emails", "Misses"],
                             {"Emails": "#b6beca", "Misses": "#f28b82"},
                             title="Every failure: emails raised, and how many were confirmed misses")
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
