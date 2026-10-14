"""The vocabulary: what a failure is called, in the tracker's words and in plain English.

`PLAIN_SUBTYPE`, `OWNED_SUBTYPE`/`failure_label`, `DRIVERS` and `REASON_CATEGORIES` live
here together because they are one subject -- how a record's classification is named --
and because `validate.py` and `audit_pages.py` import from here rather than from `app.py`,
so a gate no longer has to execute the whole Streamlit app to read a map.
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

from dashboard.styles import ROOT_COLOURS, esc




# The Complaint Tracker's reading columns, in the order a reader scans them: when it
# happened, who raised it, what it was, how it was classified, where it stands. The eight
# left out are either derived (Month, Number of Customers, Month_Sort), near-constant
# (Improvement VS Bug is `Improvement` on 110 of 111 rows), or prose too long for a grid.
# Forty distinct `Reason` strings for about seven real things, and every page inherits
# the mess: "Missed Event", "Missed insolvency alert" and "WarRoom should have been
# created but was not" are one category written three ways, so no chart of Reason can
# rank anything. This maps every value in the tracker onto a reusable category.
#
# It is **derived, not stored**. `Reason` keeps the customer's own words -- "Turkish
# keyword miss", "Missing Automotive industry tag" -- because that wording is the record
# of what they actually wrote, and a category is a reading of it. Storing it would mean a
# 27th column, a rewritten Data sheet, a wider `ComplaintTracker` ref and three scripts
# changed, for something every page can compute in a millisecond.
#
# `validate.py`'s `reason_categories` fails if a Reason value in the tracker is missing
# from this map, so a new wording cannot quietly fall into an "Uncategorised" bucket and
# go unnoticed -- which is exactly how forty values accumulated in the first place.
REASON_CATEGORIES = {
    # An event we should have reported was not reported at all.
    "Missed Event": "Event missed",
    "Missed insolvency alert": "Event missed",
    "Missed insolvency event": "Event missed",
    "Missed alert / event not captured": "Event missed",
    "Missed WarRoom": "Event missed",
    "Missed WarRoom / No notification": "Event missed",
    "Missed Relevant Event": "Event missed",
    "Missed severe weather alert": "Event missed",
    "Missed / Delayed Event": "Event missed",
    "Missed + Delayed Reporting": "Event missed",
    "Missing Resilinc alert / insolvency not captured": "Event missed",
    "Missing EventWatch coverage / feeds not captured": "Event missed",
    "WarRoom should have been created but was not": "Event missed",
    "WarRoom not created despite nationwide disruption": "Event missed",
    "SEC notification not captured/provided on time": "Event missed",
    # We reported it, but after the customer had already heard.
    "Delayed Event": "Reported late",
    "Delayed WarRoom": "Reported late",
    "Delayed alert / WarRoom created late": "Reported late",
    "Delayed / Missing WarRoom": "Reported late",
    "Delay in creating separate WarRoom / delayed escalation": "Reported late",
    # We reported it; the classification on it was wrong.
    "Wrong Relevancy": "Classified wrongly",
    "Incorrect Action": "Classified wrongly",
    "Incorrect Industry selection": "Classified wrongly",
    "Missing Automotive industry tag (customer tracking missed it)": "Classified wrongly",
    "Geographic Misclassification": "Classified wrongly",
    "Severity / consolidation handling concern": "Classified wrongly",
    # Published, but the customer's own supplier was never linked to it.
    "Impacted Supplier Missing": "Supplier not included",
    "Supplier Impact Mapping Clarification": "Supplier not included",
    "Event not triggered / not notified": "Supplier not included",
    # Published and linked, but the customer could not see it on their portal.
    "WarRoom not visible in customer profile": "Published but not visible",
    "News dashboard visibility gap": "Published but not visible",
    # Published, linked and visible -- the customer's own profile filter excluded
    # Resilinc as a source, so nothing was hidden by us. Kept out of the category above
    # because that one is named for our failures, and one of four being a customer-side
    # setting would overstate it by a quarter.
    "WarRoom visibility affected by customer profile filters": "Published but not visible",
    # One event published twice.
    "Duplicate WarRooms": "Duplicate published",
    # A question about how coverage works, not a report of a failure.
    "Coverage Verification Request": "Question about coverage",
    "Geographic Coverage Clarification": "Question about coverage",
    "Monitoring Strategy RFI": "Question about coverage",
    "Customer Requested Verification": "Question about coverage",
    "Customer Terminology Preference": "Question about coverage",
    "WarRoom Timing/Trigger Criteria Clarification": "Question about coverage",
    "Intelligence/Advisory Request": "Question about coverage",
}
# What each category means, in the words a reader who has never seen the tracker would
# need. These are read off the records, not invented, and each one says what happened
# rather than naming a field: "Supplier not included" is the Caterpillar case where the
# WarRoom existed and Dana Holding was left off its impacted list.
#
# `Hidden by the customer's own filter` was folded into `Published but not visible` on
# the owner's instruction. It was a category of its own so that a bucket named for our
# failures did not carry a customer-side setting; the owner's framing is that the bucket
# is "we published it correctly and the customer did not see it", and on that definition
# the reason the portal hid it -- our industry tag, a fault, or their own source
# preference -- does not change what happened to them. The cost of the fold is that the
# bucket now mixes our settings with theirs, so it can no longer be read as a pure
# measure of our failure. The meaning below says so.
CATEGORY_MEANING = {
    "Event missed": "We never reported it. The customer found out some other way.",
    "Reported late": "We reported it, but only after the customer had written to us. "
                     "It was captured and the bulletin was still being worked on.",
    "Question about coverage": "They asked how coverage works, or challenged a judgement. "
                               "No reporting failure was found in any of these.",
    "Classified wrongly": "We did report it, and got a field on it wrong \u2014 how relevant "
                          "it was, which industry, which geography, or how severe.",
    "Supplier not included": "The WarRoom existed, and their supplier was left off its "
                             "impacted list, so nothing reached them.",
    "Published but not visible": "We reported it correctly and it never appeared on their "
                                 "portal \u2014 an industry not selected, a fault, or their own "
                                 "source preference. The cause sits on either side.",
    "Duplicate published": "One event published twice, as two separate WarRooms.",
}


UNCATEGORISED = "Uncategorised"


def reason_category(df):
    """The reusable category behind each email's `Reason`, as a Series."""
    if df.empty or "Reason" not in df.columns:
        return pd.Series(dtype=str, index=df.index)
    return (df["Reason"].fillna("").astype(str).str.strip()
            .map(lambda v: REASON_CATEGORIES.get(v, UNCATEGORISED)))


def with_failure_label(df):
    """Add the plain failure label beside the tracker Sub-type, for the record grid."""
    if df.empty or "Sub-type" not in df.columns:
        return df
    out = df.copy()
    out["What went wrong"] = labels_for(out)
    return out


def with_reason_category(df):
    """The frame with `Reason Category` inserted directly before `Reason`."""
    if df.empty or "Reason" not in df.columns or "Reason Category" in df.columns:
        return df
    out = df.copy()
    out.insert(out.columns.get_loc("Reason"), "Reason Category", reason_category(df))
    return out


TRACKER_COLUMNS = ["Month Label", "Email/JIRA Date", "Jira Key", "Customer", "Event type",
                   "Event/Bulletin Title", "Issue Type", "Reason Category", "Reason",
                   "Root Cause", "Sub-type", "What went wrong",
                   "Missed_Flag", "Short Term Fix Status", "Resolution Date", "RCA Requested",
                   "Severity", "Standard Automation Focus", "Routed To", "Comments"]

# Free-text columns, which wrap inside a bounded width in the grid rather than being cut.
# They were briefly truncated with an ellipsis, on the reasoning that the full text sat one
# click away in the record card. It does, but 68 of 114 Comments run past 110 characters,
# so nearly every row showed a sentence that stopped mid-thought and the column a reader
# most wants to read was the one least readable. Wrapping costs row height, which is the
# honest price of showing the whole value; `white-space:nowrap` still holds every other
# column to one line, so only these get tall.
# One extra cell class for the tracker grid: dates as tabular figures so they line up
# down the column, the Jira key monospaced so EAO-9 and EAO-48 read as the same shape.
# Column names a reader sees, where the tracker's own is a field name rather than words.
# `Missed_Flag` is the only one that really reads as a database column; the rest are
# already English and renaming them would only make the grid disagree with the CSV a
# reader downloads from the same page.
DISPLAY_NAMES = {"Missed_Flag": "Confirmed miss"}


def shorten(value, limit=110):
    """One line of a long field, cut on a word boundary so it does not end mid-word."""
    text = "" if pd.isna(value) else str(value).strip()
    if len(text) <= limit:
        return text
    head = text[:limit].rsplit(" ", 1)[0]
    return f"{head or text[:limit]}\u2026"


# ---------------------------------------------------------------------------
# Executive Overview
#
# Everything from here to the page dispatch serves one page. It is grouped rather
# than scattered because the page is a story told in sections, and these functions
# only make sense as that story's parts.
# ---------------------------------------------------------------------------

# The tracker's taxonomy, read out in English. `Root Cause` and `Sub-type` are the
# vocabulary of the people who file the records, and on a leadership page they say
# nothing: "Event Identification" and "Prioritization" are not categories a reader
# outside the team can rank, and "Review" -- the single largest People bucket -- is
# the vaguest word in the file. The tracker keeps its own wording, because that is
# the record; only the chart label is translated, and the original travels with it
# in the table beside the chart so an analyst can tie any slice back to a field.
# Two pairs deliberately share a label, which is what "club them" means: they are one
# failure to a reader and two values to the tracker. `Prioritization` and `Captured Late`
# both end with the customer hearing about an event we already had, late; `Tagging` and
# `Industry selection` are both the industry being wrong or missing at publication. The
# tracker keeps both values -- they travel in the `Tracker value` column beside the label
# -- and every block that aggregates on the label (`root_frame`, the miss-bucket tail,
# `audit_pages.miss_buckets`) has to sum into the label rather than key on the sub-type,
# or the second value silently overwrites the first.
#
# What is deliberately NOT in these labels is the actor, wherever the tracker puts the
# same sub-type under more than one owner. `Event Identification` is 5 People and 4
# Product, `Review` is 21 People and 2 Product, `Relevancy`'s one record is Product --
# so a label reading "an analyst did X" is a false statement on every Product row. The
# owner is carried beside the label, by `root_frame`'s Owner column and by the two
# owner-split buckets in `MISS_BUCKETS`, which is the only place it can be said and be
# true on every row.
PLAIN_SUBTYPE = {
    "Source Coverage": "Source not in our vendor or monitoring network",
    "Keyword Update": "Keyword Miss",
    "Review": "We saw it and chose not to report it",
    "Event Identification": "Classified as not impactful, wrongly",
    "Prioritization": "Captured, but notified late",
    "Captured Late": "Captured, but notified late",
    "Mapping": "Supplier was not mapped by the customer",
    "Alerting Gap": "Captured, but never reached the analyst portal",
    "Visibility": "Published, but not visible to the customer",
    "Policy/Logic": "Our scoring or rules got it wrong",
    "Process Clarification": "We had to clarify the reporting guidelines",
    "Duplication": "The same event published twice",
    "Tagging": "Incorrect industry selection",
    "Industry selection": "Incorrect industry selection",
    "Relevancy": "Judged not relevant to this customer",
    "WarRoom Creation": "WarRoom Missed",
    "Strategy": "How we group events",
    # The V1 cause taxonomy. No label names an actor on a sub-type the tracker puts
    # under more than one owner; these ten each sit under exactly one today, and the
    # two that do name one (the model, the look we took) are single-owner for that
    # reason. `plain()` still falls back to the raw value, so an eleventh added
    # tomorrow appears as itself rather than vanishing.
    "Published Late": "Captured and reviewed, but published late",
    "Methodology Weakness": "Our reporting criteria were not strong enough",
    "Deliberate Rule": "Worked as our published rule intends",
    "Platform Bug": "A confirmed platform defect",
    "Mapping / Routing Defect": "Wrong data sent it to the wrong place",
    "Supplier / Site Not Shared": "The site was never shared with us",
    "Analyst Review Miss": "We saw it and closed it without a careful look",
    "Supplier Selection Miss": "Supplier left off the WarRoom at creation",
    "Clustering / Duplication Defect": "Stories grouped or duplicated wrongly",
    "Model Classification Defect": "The model classified it wrongly",
}

# `Mapping` is the one sub-type whose meaning CHANGES WITH ITS OWNER, and the two
# meanings are not variants of each other -- they are different failures, with different
# owners and different fixes:
#
#   Product   the supplier is not in the customer's mapped supply chain at all. They
#             never shared the company with Resilinc, so there was nothing for the event
#             to match against. Not our failure. (Ford, CSV 17: "company not mapped as
#             Ford supplier".)
#   People    the supplier WAS mapped, and an analyst left it off the WarRoom or its
#             geofence when the WarRoom was built. Entirely ours. (Caterpillar EAO-6,
#             "Dana Holding Corporation was not included in impacted supplier selection";
#             META EAO-49, the Delta Electronics site added only by a later update.)
#   Process   neither: the customer asked why the mapping behaved as it did, and a
#             clarification went back.
#
# `PLAIN_SUBTYPE` is keyed on the sub-type alone and cannot tell them apart, so one
# label -- "Supplier was not mapped by the customer" -- was printed over all three, and
# it is a **false statement** on the People rows: it blames the customer for a supplier
# they had mapped. This is the same rule the file already states for `Review`: no label
# names an actor where the tracker puts that sub-type under more than one owner. The
# fix is not to find a wording that covers both; it is to stop pretending they are one
# failure. `DRIVERS` already had this right (`Supplier Impact / Mapping` against
# `Supplier Selection`), and only the sub-type label lagged.
OWNED_SUBTYPE = {
    ("People", "Mapping"): "Supplier mapped, but left off the WarRoom",
    ("Process", "Mapping"): "Supplier mapping queried by the customer",
}


def failure_label(root, subtype):
    """The plain label for a failure, owner-aware wherever the owner changes the meaning.

    Every block that knows the owner of a row goes through this rather than `plain()`.
    The handful that genuinely cannot -- a table already grouped on the sub-type alone --
    keep `plain()`, and they are the ones where the owner is a column beside the label.
    """
    key = (str(root).strip(), str(subtype).strip())
    if key in OWNED_SUBTYPE:
        return OWNED_SUBTYPE[key]
    return plain(subtype, PLAIN_SUBTYPE)


def labels_for(frame, subtype_col="Sub-type", root_col="Root Cause"):
    """`failure_label` across a frame, row by row, so each row gets its own owner."""
    if frame.empty or subtype_col not in frame.columns:
        return pd.Series(dtype=object, index=frame.index)
    roots = (frame[root_col] if root_col in frame.columns
             else pd.Series("", index=frame.index)).fillna("").astype(str)
    subs = frame[subtype_col].fillna("Blank").astype(str)
    return pd.Series([failure_label(r, s) for r, s in zip(roots, subs)], index=frame.index)

# What each slice of the left ring means, for its hover.
SPLIT_MEANING = {
    "Confirmed misses": "The event did not reach the customer in time, and the "
                        "investigation agreed it was our failure",
    "Complaints, not a miss": "The customer asserted we failed; we did report it, and the "
                              "issue turned out to be something else",
    "Inquiries": "The customer asked how something works rather than asserting we failed",
}


def plain(value, mapping):
    """A taxonomy value in English, or the value itself if nothing maps it.

    Falling back to the original matters: a term added to the tracker tomorrow shows
    up as itself rather than vanishing from a chart or landing in an "Other" nobody
    asked for.
    """
    return mapping.get(str(value).strip(), str(value).strip())


# EventWatch's own name for each failure, keyed on `(Root Cause, Sub-type)` -- the two
# fields the tracker actually stores, never on the display wording of `Reason`. A pair
# that is not in this map counts as `Needs Review` rather than being talked into the
# nearest term: two of the three roots carry rows whose taxonomy and evidence disagree
# (a Product row whose Comments describe a WarRoom that was never created, a People row
# about an SEC notification that arrived late), and quietly filing those under a
# plausible heading is how a taxonomy stops meaning anything.
#
# Each entry is (internal term, the same thing in plain English). The term is what the
# chart prints, the plain English rides on the hover and fills a column of the table, so
# the page reads to a VP without costing an analyst the word they file records under.
DRIVERS = {
    # -- Product: detection and system coverage -----------------------------------
    ("Product", "Source Coverage"): ("Source Miss", "The source is not in our vendor or monitoring network"),
    ("Product", "Keyword Update"): ("Keyword Miss", "Monitored source, but retrieval logic missed the article"),
    ("Product", "Event Identification"): ("Model Miss", "Incorrect automated classification or routing"),
    ("Product", "Review"): ("Model Miss", "The model had it and did not flag it as reportable"),
    ("Product", "Prioritization"): ("Model Miss", "Incorrect automated classification or routing"),
    ("Product", "Relevancy"): ("Model Miss", "Incorrect automated classification or routing"),
    ("Product", "Mapping"): ("Supplier Impact / Mapping", "The supplier was not mapped to the impacted event"),
    ("Product", "Visibility"): ("Portal Visibility Issue", "Published, but not visible to the customer"),
    ("Product", "Policy/Logic"): ("System Limitation", "A platform rule or scoring threshold held it back"),
    ("Product", "Industry selection"): ("Industry Tagging", "Incorrect industry selection, or the industry was missed"),
    ("Product", "Tagging"): ("Industry Tagging", "Incorrect industry selection, or the industry was missed"),
    ("Product", "Alerting Gap"): ("Alerting Gap",
     "Captured by us, but it never reached the analyst portal in time"),
    # `Captured Late` is a DIFFERENT failure from `Alerting Gap` and must not share its
    # label: Alerting Gap is "we had it, the analyst never saw it", Captured Late is "our
    # first usable capture came late". They briefly both printed "Alerting Gap" here, which
    # would have folded the Suntory row into the Alerting Gap count on Root cause.
    ("Product", "Captured Late"): ("Product Captured Late",
     "Our first usable capture of the story came late"),
    # -- People: analyst assessment and review ------------------------------------
    ("People", "Review"): ("People / Analyst Miss", "An analyst read it and decided not to report it"),
    ("People", "Event Identification"): ("Event Identification", "Seen by an analyst and classified as not impactful"),
    ("People", "Prioritization"): ("Prioritization", "Ranked too low to raise, so the customer heard late"),
    ("People", "Relevancy"): ("Impact Misclassification", "Judged not relevant to the customer, wrongly"),
    ("People", "Duplication"): ("Duplicate Assessment Error", "The same event assessed and published twice"),
    ("People", "Mapping"): ("Supplier Selection", "An impacted supplier was left off the WarRoom"),
    ("People", "Tagging"): ("Industry Selection", "Incorrect industry selection, or the industry was missed"),
    ("People", "Industry selection"): ("Industry Selection", "Incorrect industry selection, or the industry was missed"),
    ("People", "Policy/Logic"): ("Incorrect Action", "The wrong action was taken on the event"),
    # `Delayed Notification` is a Process-list term used under People on purpose: the
    # People vocabulary has no word for lateness. No row carries this pair today -- the
    # one that briefly did turned out to be an analyst who overlooked the story, which is
    # `Review` -- but the pair is plausible and mapping it keeps it out of Needs Review.
    # A term is a label, not a claim about the owner; the owner is the key it hangs on.
    ("People", "Captured Late"): ("Delayed Notification", "Captured, but the customer was told too late"),
    # -- Process: workflow and control ---------------------------------------------
    ("Process", "Process Clarification"): ("SOP Unclear", "Reporting guidelines had to be clarified to the customer"),
    ("Process", "Captured Late"): ("Delayed Notification", "Captured, but the customer was told too late"),
    ("Process", "WarRoom Creation"): ("WarRoom Issue", "A required WarRoom was missing, delayed, duplicated, or not visible"),
    ("Process", "Visibility"): ("WarRoom Issue", "A required WarRoom was missing, delayed, duplicated, or not visible"),
    ("Process", "Duplication"): ("Duplicate WarRoom", "One event published as two separate WarRooms"),
    ("Process", "Strategy"): ("Severity / Consolidation Handling", "How events are grouped, or the severity set on them"),
    ("Process", "Policy/Logic"): ("Severity / Consolidation Handling", "How events are grouped, or the severity set on them"),
    ("Process", "Review"): ("Peer Review Missing", "No second pair of eyes before it went out"),
    # Display mapping only. This pair predates the V1 taxonomy and the row behind it --
    # the Ford Sandy Fire mapping clarification -- is correctly classified; it rendered
    # as `Needs Review` for want of a label, not for want of a decision, which is the
    # one thing `Needs Review` must never mean.
    ("Process", "Mapping"): ("Mapping Clarification",
     "Customer asked how supplier-impact mapping or geofencing logic was applied"),
    # -- The V1 cause taxonomy -----------------------------------------------------
    # Every pair migrated in Commit 2, so no migrated row renders as `Needs Review`.
    # Terms are reused where the failure is the same one under a new sub-type --
    # `People / Analyst Miss`, `Supplier Selection` and `Model Miss` each already
    # existed -- because `root_frame()` groups on the TERM, so a new term splits a bar
    # that should stay whole.
    ("People", "Published Late"): ("Published Late", "Captured and reviewed, but published too late"),
    ("People", "Analyst Review Miss"): ("People / Analyst Miss", "A person had it and closed it without a careful look"),
    ("People", "Supplier Selection Miss"): ("Supplier Selection", "An impacted supplier was left off the WarRoom"),
    ("Process", "Methodology Weakness"): ("Methodology Weakness", "Our reporting criteria were not strong enough"),
    ("Process", "Deliberate Rule"): ("Worked as Designed", "Our published rule applied, and the customer queried it"),
    ("Process", "Supplier / Site Not Shared"): ("Customer Data Gap", "The site was never shared with us, so nothing matched"),
    ("Product", "Platform Bug"): ("Platform Bug", "A confirmed platform or data-processing defect"),
    ("Product", "Mapping / Routing Defect"): ("Mapping / Routing Defect", "Wrong data routed it to the wrong customer or site"),
    ("Product", "Clustering / Duplication Defect"): ("Clustering / Duplication Defect", "Stories grouped, split or duplicated wrongly"),
    ("Product", "Model Classification Defect"): ("Model Miss", "The model classified the story wrongly"),
}

NEEDS_REVIEW = "Needs Review"
DRIVER_OTHER = "Other"

# Who owns each root cause, in one line, as leadership reads it.
ROOT_OWNERSHIP = {
    "Product": "Detection and system coverage",
    "People": "Analyst assessment and review",
    "Process": "Workflow and control",
}


def name_subtypes(frame, col="Sub-type", head="What it means", root=None):
    """Put the plain-English label beside a tracker Sub-type, on any tab.

    The Executive Summary translates the taxonomy and the source pages did not, so the
    same failure read "Source Coverage" on one tab and "Source not in our vendor or
    monitoring network" on another -- two vocabularies for one thing, which is the fault
    `PLAIN_SUBTYPE` exists to fix. The tracker value stays in its own column because it
    is the record; the label is inserted next to it, never over it.

    `root` is the owner of every row in the frame, where the caller knows it -- the
    per-owner drill-downs do. Without it `Mapping` would print the Product wording on
    the People drill-down, which is the exact false statement `failure_label` exists to
    stop.
    """
    if frame is None or frame.empty or col not in frame.columns:
        return frame
    out = frame.copy()
    out.insert(list(out.columns).index(col) + 1, head,
               out[col].map(lambda v: failure_label(root, v) if root else plain(v, PLAIN_SUBTYPE)))
    return out


def owner_pills(counts):
    """The owner column as one pill per owner, in that owner's own colour.

    It was the string "Product 12 · People 3", which reads as a single value and makes
    the reader parse two names and two numbers out of one run of text -- on the widest
    table on the page, where the owner is the column a VP actually looks for. One pill
    each, name and count set apart, coloured with the same three hues the root-cause
    cards and both donuts use, so the owner is recognised before it is read.

    This is the one place in `excel_bar_table` that writes HTML into a cell, and the
    strings are built here from `ROOT_COLOURS` keys -- never from anything a customer or
    an analyst typed, which still goes through `esc()`.
    """
    out = []
    for owner, n in counts.items():
        colour = ROOT_COLOURS.get(owner, "#b6beca")
        out.append(f"<span class='owner-pill' style='--c:{colour}'>{esc(owner)} <b>{int(n)}</b></span>")
    return "".join(out)


def plural(n, one, many=None):
    """"1 miss" / "2 misses" -- a leadership page does not write "miss(es)"."""
    return f"{n} {one if n == 1 else (many or one + 's')}"


def driver_of(root, subtype):
    """The internal term and its plain English, or Needs Review for an unmapped pair."""
    return DRIVERS.get((str(root).strip(), str(subtype).strip()),
                       (NEEDS_REVIEW, "The root cause and sub-type on this email do not map "
                                      "to a known failure driver"))
