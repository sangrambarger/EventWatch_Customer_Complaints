"""DETAIL · Event workload -- The summary's Event types block, which is the whole answer here."""
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
from dashboard.components import page_header
from dashboard.sections import render_event_types



def render(df, filtered, selected_page):
    page_header(selected_page); page = filtered; filter_note()
    # The Executive Summary's Event types block is the whole answer here; the generic
    # count-table-plus-chart pair this page used to draw said the same thing in weaker
    # words and with one base instead of two.
    render_event_types(page)
