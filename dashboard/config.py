"""Application configuration: titles, the page list and where the data lives.

No Streamlit calls and no imports from the rest of the package, so every other module
can read it without a cycle.
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


APP_TITLE = "EventWatch Executive Dashboard"
# Data file names, not locations. Where they are read from is resolved at runtime by
# data_sources() -- no owner, repo or branch is hardcoded anywhere in this file.
CSV_NAME = "customer_tracker.csv"
WORKBOOK_NAME = "EventWatch_Customer_Complaints_2026.xlsx"
# The directory the ENTRY POINT sits in, which is this package's parent -- not the
# package itself. `data_sources()` looks for the tracker beside `app.py`, which is
# the zero-config path a Streamlit Cloud deploy takes; a plain `parent` here points
# at `dashboard/`, finds nothing, and every page renders empty.
APP_DIR = Path(__file__).resolve().parent.parent

# Seven tabs became three on the owner's call. Each of the three now answers a
# different question, and nothing is on two of them:
#   Executive Summary   -- what a VP reads, month by month
#   All customer emails -- the records, and the vocabulary every figure is written in
#   Analysis            -- where a figure came from, for whoever is asked to prove it
#
# What went, and why. DETAIL Event workload rendered one Executive Summary block and
# nothing else. Monthly trend was the month chart -- which now lives on the summary --
# plus a miss-rate chart of a figure the summary already prints above every bar.
# Dynamic Source Discovery selected itself on `Standard Automation Focus`, a field this
# repository documents as deliberately spanning BOTH source gaps and keyword gaps, so
# the page could not answer the question in its own title. Root cause and Top customer
# complaints merged into Analysis; both already ran the summary's own renderers.
PAGES = [
    # All customer emails sits second on purpose: it is where the vocabulary every other
    # tab uses is defined, so a reader who stops on a category name anywhere else finds
    # its meaning one click away rather than at the bottom of a longer list.
    "Executive Summary", "All customer emails", "Analysis",
]

DESCRIPTIONS = {
    "Executive Summary": "What customers sent in, how much of it we got wrong, why, who it hit, and whether it is moving.",
    "All customer emails": "Every complaint and inquiry a customer sent in, with the category behind each one, downloads, and controlled manual-entry staging.",
    "Analysis": "Where the summary's figures come from: the full failure taxonomy, the sub-type heatmap, the per-owner drill-downs, one account at a time, and the customer's own words for what went wrong.",
}

# The pages fall into jobs, and the job -- not the page -- is what a colour can usefully
# say. A hue per page would be confetti, and repeating a hue across unrelated pages
# claims a kinship that is not there. At three pages the grouping earns little, and it
# stays because the rule is what matters: colour names the job. The index is derived from PAGES rather
# than written out, so reordering or renaming a page cannot leave a rule pointing at the
# wrong row.
NAV_GROUPS = {
    "Where you start": ("#8ab4f8", ("Executive Summary", "All customer emails")),
    "Where it comes from": ("#80cbc4", ("Analysis",)),
}


PAGE_KICKERS = {
    "Executive Summary": ("Overview", "#8ab4f8"),
    "All customer emails": ("The records", "#f28b82"),
    "Analysis": ("Drill-down", "#80cbc4"),
}


# ---------------------------------------------------------------------------
# The build stamp
#
# Streamlit Cloud's hot update path ("Pulling code changes -> Updated app!") pulls
# the new files but does not reliably re-import package modules, so the process can
# go on serving code that is days behind the repository. That happened here: three
# merges landed, the files were on the server, and the page kept drawing the commit
# the process had loaded. It cost an hour to diagnose, from the outside, by diffing
# rendered strings against `git log -S`.
#
# **The sha is read ONCE, at import, and that is the whole point.** Reading it when
# the sidebar draws would read the *disk*, which after a hot pull is the NEW commit
# while the running modules are old -- the stamp would then be freshest exactly when
# it is lying. `BUILD_SHA` is what this process loaded; `head_sha()` is what the
# checkout holds now; the two disagreeing is the fault, and that is what gets shown.
#
# Its one limit, stated rather than papered over: this module is the one whose import
# time is recorded, so a reload that refreshed `config` while leaving `sections` stale
# would read current and still be wrong. In the failure actually seen, nothing
# reloaded at all, which is the case it catches.
#
# No subprocess and no network -- `app.py` makes neither, and a build stamp is not the
# place to start. These are two small plain-text reads of files git maintains.
def head_sha():
    """The commit the checkout on disk points at now, or "" if there is no git dir."""
    git = APP_DIR / ".git"
    try:
        head = (git / "HEAD").read_text(encoding="utf-8").strip()
        if not head.startswith("ref:"):          # detached HEAD holds the sha itself
            return head[:40]
        ref = head.split(" ", 1)[1].strip()
        loose = git / ref
        if loose.exists():
            return loose.read_text(encoding="utf-8").strip()[:40]
        # A clone can keep its refs packed instead of as loose files.
        packed = git / "packed-refs"
        if packed.exists():
            for line in packed.read_text(encoding="utf-8").splitlines():
                if line.endswith(" " + ref):
                    return line.split(" ", 1)[0][:40]
    except OSError:
        pass
    return ""


BUILD_SHA = head_sha()


def build_note():
    """`(text, stale)` for the sidebar's build line.

    `stale` is True only when the process and the checkout disagree, which is the
    state a reader needs told: the page they are looking at is not the code that was
    merged, and only a restart fixes it.
    """
    if not BUILD_SHA:
        return ("Build unknown -- no git metadata in this checkout.", False)
    on_disk = head_sha()
    if on_disk and on_disk != BUILD_SHA:
        return (f"Showing build {BUILD_SHA[:7]}, but the repository is at "
                f"{on_disk[:7]}. Reboot the app to load it.", True)
    return (f"Build {BUILD_SHA[:7]}", False)
