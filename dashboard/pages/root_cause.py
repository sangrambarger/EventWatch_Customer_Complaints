"""Root cause -- The summary's root-cause block, the deeper taxonomy, the heatmap and the per-owner drill-downs."""
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

from dashboard.components import add_rule
from dashboard.sections import render_deeper_root_cause, render_root_cause, source_page



def render(df, filtered, selected_page):
    # The Executive Summary's root-cause section, then the deeper one the summary no
    # longer carries -- the owner moved `render_deeper_root_cause` here, where it was
    # already running, because the full taxonomy is a drill-down and not a summary --
    # then the cuts that never fitted on a summary at all: the sub-type heatmap and the
    # per-owner drill-downs. The first block is the same code the summary runs, so the
    # two tabs cannot disagree about a driver's count or call one failure two things.
    render_root_cause(filtered)
    add_rule()
    render_deeper_root_cause(filtered)
    add_rule()
    source_page(selected_page, filtered, "Root Cause", "root_cause", summary=False)
