"""Dynamic Source Discovery -- The source and keyword deep dive."""
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
from dashboard.metrics import count_table, long_pair_table
from dashboard.components import add_section, chart, downloads, excel_bar_table, page_header, styled_table



def render(df, filtered, selected_page):
    page_header(selected_page); page = filtered; filter_note(); disc = page[page["Standard Automation Focus"].astype(str).eq("Dynamic Source Discovery")] if "Standard Automation Focus" in page.columns else page.iloc[0:0]
    add_section("Source-miss meaning", "Dynamic Source Discovery identifies event types, customers, reasons, feeds, keywords, or source coverage patterns that current sources are missing or under-detecting.", "#80cbc4")
    for title, col in [("Event types missed by sources", "Event type"), ("Customers affected by source misses", "Customer"), ("Reasons linked to source misses", "Reason")]:
        if col in disc.columns: t = count_table(disc, col, base=max(len(page), 1)); add_section(title, f"Shows source-miss records by {col.lower()} with share of all selected records."); excel_bar_table(t, col); fig = chart(t, col, title=title); downloads(t, title.lower().replace(" ", "_"), fig)
    for first, second, name in [("Customer", "Event type", "Customer event-type source misses"), ("Event type", "Reason", "Event-type reason source misses"), ("Customer", "Reason", "Customer reason source misses")]:
        lt = long_pair_table(disc, first, second, base=max(len(page), 1))
        if not lt.empty: add_section(name, f"Readable detail table showing {first.lower()} and {second.lower()} as separate columns instead of a wide cross-tab.", "#a8dab5"); styled_table(lt, height=420); downloads(lt, name.lower().replace(" ", "_"))
    add_section("Complete Dynamic Source Discovery records", "All filtered records classified under Dynamic Source Discovery for detailed review.", "#b6beca"); styled_table(disc, height=420); downloads(disc, "dynamic_source_discovery_complete")
