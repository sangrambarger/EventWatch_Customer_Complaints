"""Top customer complaints -- The summary's Customers impacted block, then one account at a time."""
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

from dashboard.metrics import count_table, customer_exposure
from dashboard.components import add_rule, add_section, downloads, styled_table
from dashboard.sections import render_customers, source_page



def render(df, filtered, selected_page):
    page = source_page(selected_page, filtered, "Customer", "top_customers",
                       primary=customer_exposure, summary=False)
    # The Executive Summary's Customers impacted block, unchanged, so the account
    # numbers on the two tabs come from one computation.
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
