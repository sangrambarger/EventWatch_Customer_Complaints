"""Monthly trend -- Volume by month, then the summary's own trend block."""
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
from dashboard.components import add_rule, page_header
from dashboard.sections import render_monthly_breakdown, render_trend



def render(df, filtered, selected_page):
    page_header(selected_page); page = filtered; filter_note()
    render_monthly_breakdown(page)
    add_rule()
    # The same block the Executive Summary carries, from the same function. This page
    # used to draw its own miss-rate line from `missed_rate()` while the summary drew
    # `trend_chart()` from pooled windows -- two charts of one number, disagreeing on
    # which months were being compared, and a reader moving between the tabs had no way
    # to tell which was the real one.
    render_trend(page)
