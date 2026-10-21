"""Analysis -- the one drill-down tab: why we missed, and who it happened to.

Seven tabs became three on the owner's call. This page is the merge of what were Root
cause and Top customer complaints, in that order and with their blocks unchanged. It
exists for the reader who is asked where a figure on the Executive Summary came from
and has to show their working; it is not a leadership page and should not be written
like one.

**One heading, drawn here.** Both halves call `source_page(..., header=False)` so the
page cannot grow a second one. That also closes a defect the merge exposed: the old
Root cause page ran `render_root_cause()` before `source_page()`, so its own heading
and filter line rendered three hundred lines down, beneath the section they introduce.

**Both halves run the Executive Summary's own renderers** -- `render_root_cause()` and
`render_customers()` -- for the reason every shared block here does: two tabs drawing
one figure from two copies is how they end up disagreeing, and this is the tab whose
whole job is to agree with the summary.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from dashboard.filters import filter_note
from dashboard.metrics import count_table, customer_exposure
from dashboard.components import add_rule, add_section, downloads, page_header, styled_table
from dashboard.sections import (render_customers, render_deeper_root_cause,
                                render_root_cause, source_page)


def render(df, filtered, selected_page):
    page_header(selected_page); page = filtered; filter_note()

    # ---- was the Root cause page, in its own order -------------------------------
    # The summary's root-cause block, then the deeper taxonomy the summary no longer
    # carries, then the cuts that never fitted a summary at all: the sub-type heatmap
    # with its own customer selector, and the per-owner drill-downs.
    render_root_cause(page)
    add_rule()
    render_deeper_root_cause(page)
    add_rule()
    source_page(selected_page, page, "Root Cause", "root_cause", summary=False, header=False)

    add_rule()
    # ---- was the Top customer complaints page, in its own order -------------------
    # `source_page` first, as that page had it: the per-account miss-rate bars and the
    # one-account-at-a-time dropdown view, then Customers impacted beneath them.
    source_page(selected_page, page, "Customer", "top_customers",
                primary=customer_exposure, summary=False, header=False)
    render_customers(page)
    add_rule()
    complaints = page[page["Issue Type"].astype(str).eq("Complaint")] if "Issue Type" in page.columns else page
    multi = int(complaints["Customer"].astype(str).str.contains("/").sum()) if "Customer" in complaints.columns else 0
    exact = count_table(complaints, "Customer")
    add_section("As the Excel Dashboard counts it", f"The workbook differs on two counts: it includes complaint "
                f"records only, and it matches the Customer field as a whole string, so each of the {multi} "
                f"multi-customer complaint row(s) becomes its own category instead of being added to either "
                f"account. Kept here so the two artefacts can be reconciled. The table above is the one that "
                f"answers how many emails and questions a customer sent in.", "#b6beca")
    styled_table(exact, height=420); downloads(exact, "top_customers_exact")
