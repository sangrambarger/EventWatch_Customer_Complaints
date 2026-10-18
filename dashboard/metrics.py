"""Every number the dashboard prints, computed once.

One implementation per business rule: `miss_bucket_series()` assigns the miss buckets,
`customer_exposure()` splits multi-customer rows, `customer_totals()` reconciles the one
table whose rows deliberately double-count. Pages call these; they never recompute.
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
from dashboard.taxonomy import CATEGORY_MEANING, DRIVER_OTHER, NEEDS_REVIEW, ROOT_OWNERSHIP, driver_of, failure_label, labels_for, owner_pills, plural, reason_category, shorten
from dashboard.filters import customer_names, names_match




def split_by_issue(frame, keys, index):
    """Complaint and Inquiry counts per key, so a total never hides its make-up."""
    out = pd.DataFrame(index=index)
    if "Issue Type" not in frame.columns:
        return out
    issue = frame["Issue Type"].fillna("").astype(str).str.strip()
    # Spelled out, not pluralised by concatenation -- "Inquiry" + "s" is "Inquirys",
    # which silently never matched the column the callers look for.
    for value, column in (("Complaint", "Complaints"), ("Inquiry", "Inquiries")):
        out[column] = keys[issue == value].value_counts().reindex(index).fillna(0).astype(int)
    return out


def count_table(df, col, base=None):
    """One row per value: the complaint/inquiry split, the confirmed misses, the total.

    `Misses` is here rather than on each page's own table because every tab has to state
    the same three bases the Executive Summary states. A count column on its own does not
    say whether those emails were a failure: `Process Clarification` is 13 emails of which
    2 were misses and `Review` is 23 of which 21 were, and a table showing only 13 and 23
    ranks them the wrong way round. It is a clean partition of `Records`, so the Total row
    adds up and `audit_pages.py` reconciles it like any other column.
    """
    cols = [col, "Complaints", "Inquiries", "Misses", "Reported timely", "Records", "% of Total"]
    if df.empty or col not in df.columns: return pd.DataFrame(columns=cols)
    keys = df[col].fillna("Blank").astype(str)
    t = keys.value_counts().reset_index()
    t.columns = [col, "Records"]
    parts = split_by_issue(df, keys, pd.Index(t[col]))
    for name in ("Complaints", "Inquiries"):
        if name in parts.columns:
            t[name] = parts[name].values
    if "Missed_Flag" in df.columns:
        missed = keys[df["Missed_Flag"].astype(str).str.strip().eq("Yes")].value_counts()
        t["Misses"] = t[col].map(missed).fillna(0).astype(int)
        # The remainder, named. Every row of every count table on the dashboard used to
        # read "25 emails, 24 misses" and leave the reader to wonder what the 25th was.
        # Records = Misses + Reported timely, on every row, with nothing unaccounted for.
        t["Reported timely"] = t["Records"] - t["Misses"]
    denom = max(base or len(df), 1)
    t["% of Total"] = (t["Records"] / denom * 100).round(1).astype(str) + "%"
    return t[[c for c in cols if c in t.columns]]


def long_pair_table(df, first, second, base=None):
    if df.empty or first not in df.columns or second not in df.columns: return pd.DataFrame(columns=[first, second, "Records", "% of Total"])
    out = df.groupby([first, second], dropna=False).size().reset_index(name="Records")
    out[first], out[second] = out[first].fillna("Blank").astype(str), out[second].fillna("Blank").astype(str)
    denom = max(base or int(out["Records"].sum()), 1)
    out["% of Total"] = (out["Records"] / denom * 100).round(1).astype(str) + "%"
    return out.sort_values(["Records", first, second], ascending=[False, True, True])


def category_table(df, total=True):
    """One row per category, carrying the customer wordings folded into it.

    The wordings column is the point: it turns the fold from something a reader has to
    trust into something they can check. Only the wordings present in the current filter
    are listed, most used first, so the column narrows with the date range rather than
    reciting all forty every time.
    """
    cols = ["Category", "What it means", "Their exact wordings",
            "Emails", "% of these", "Complaints", "Inquiries", "Misses"]
    if df.empty or "Reason" not in df.columns:
        return pd.DataFrame(columns=cols)
    frame = df.assign(_cat=reason_category(df))
    total = max(len(frame), 1)
    rows = []
    for name, group in frame.groupby("_cat"):
        wordings = group["Reason"].astype(str).str.strip().value_counts()
        missed = int((group.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip() == "Yes").sum())
        rows.append({
            "Category": name,
            "What it means": CATEGORY_MEANING.get(name, ""),
            "Their exact wordings": "\n".join(f"• {w} ({n})" for w, n in wordings.items()),
            "Emails": len(group),
            "% of these": f"{len(group) / total * 100:.0f}%",
            "Complaints": int((group.get("Issue Type", pd.Series(dtype=str)).astype(str) == "Complaint").sum()),
            "Inquiries": int((group.get("Issue Type", pd.Series(dtype=str)).astype(str) == "Inquiry").sum()),
            "Misses": f"{missed} ({missed / max(len(group), 1) * 100:.0f}%)",
        })
    out = pd.DataFrame(rows)[cols].sort_values("Emails", ascending=False).reset_index(drop=True)
    if total:
        # Built here rather than by a generic helper, because two of these columns are
        # formatted strings -- "62 (100%)" cannot be summed after the fact, only before.
        every = int((frame.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip() == "Yes").sum())
        out.loc[len(out)] = {
            "Category": "Total", "What it means": "", "Their exact wordings": "",
            "Emails": len(frame), "% of these": "100%",
            "Complaints": int((frame.get("Issue Type", pd.Series(dtype=str)).astype(str) == "Complaint").sum()),
            "Inquiries": int((frame.get("Issue Type", pd.Series(dtype=str)).astype(str) == "Inquiry").sum()),
            "Misses": f"{every} ({every / max(len(frame), 1) * 100:.0f}%)",
        }
    return out


def record_labels(frame):
    """Labels for the record picker, mapped back to the index they came from.

    Date, key, customer and a trimmed title -- enough to find a specific record among a
    hundred without opening each one. Duplicates are numbered rather than deduplicated,
    because two genuinely similar records must both stay selectable.
    """
    labels, seen = {}, {}
    for idx, row in frame.iterrows():
        raised = row.get("Email/JIRA Date")
        stamp = raised.strftime("%d-%b-%Y") if pd.notna(raised) and hasattr(raised, "strftime") else "undated"
        key = str(row.get("Jira Key") or "").strip() or "no key"
        label = f"{stamp} · {key} · {row.get('Customer', '')} · {shorten(row.get('Event/Bulletin Title', ''), 70)}"
        seen[label] = seen.get(label, 0) + 1
        if seen[label] > 1:
            label = f"{label} ({seen[label]})"
        labels[label] = idx
    return labels


# Why an event was missed, in the categories leadership actually asks about, plus the
# residue. Each bucket is a set of `Sub-type` values and optionally a set of `Root Cause`
# values, so the block is auditable against the tracker rather than being a hand-kept
# number on a slide.
#
# Analyst and model are two slices, not one. They were merged while the split was only a
# colour choice; they are not the same finding, because they have different owners. An
# item that reached a human reviewer and was not raised is EventWatch Ops' to fix; one
# the model did not identify is Product's. The taxonomy already separates them -- these
# are the same `Sub-type` values under a different `Root Cause` -- so merging them threw
# away the only part of the number that says who acts on it. Split, it reads 25 analyst
# against 13 model, which is a staffing conversation and a model conversation, not one
# undifferentiated 38.
#
# The last bucket is the honest part. The named categories do not cover the taxonomy --
# Mapping, Tagging, Visibility, Policy/Logic, Captured Late and WarRoom Creation are none
# of source, keyword, analyst or model, and neither is a Process-rooted Review -- and
# folding them into the analyst number to keep the picture tidy would overstate it by the
# size of the residue. It is shown as its own slice instead.
#
# Colour: Source and Keyword are one family in two steps of BLUE_RAMP, because both are
# "it never reached a person" and the eye should group them. Analyst and model take --red
# and --amber. --green is deliberately not used even though it measures clean against
# --red here (dE 9.7 deutan, 20.5 normal -- the dE 3.6 pair CLAUDE.md warns about is a
# saturated red/green, not these two tokens): every slice on this chart is a failure, and
# green would say one of them went well.
# Named in English rather than in the tracker's taxonomy, because these labels are read
# by people outside the team and "Source Miss" is not a phrase that tells anyone what
# happened. `audit_pages.py` recomputes them from the CSV under the same names, so a
# bucket renamed here without being renamed there fails the audit rather than quietly
# ceasing to be checked.
#
# These four are the ones where the OWNER changes the answer: the same sub-type reached
# a human on a People row and a model on a Product row, and merging them throws away the
# part of the number that says who acts on it. Every other missed email takes a bucket
# named after its own sub-type, generated in `miss_bucket_series()` -- there is no
# `Other`. A residue bucket is how eleven real failures (a supplier never linked, a
# WarRoom never created, a bulletin published but never shown) became one grey slice
# nobody could act on, and it also hides a sub-type added to the tracker tomorrow.
MISS_BUCKETS = (
    ("Source not in our vendor or monitoring network", ("Source Coverage",), (), "#8ab4f8",
     "The event never entered our system · Product"),
    ("Keyword Miss", ("Keyword Update",), (), "#4e7bb8",
     "A source we monitor carried it; no keyword matched · Product"),
    # These two are the only labels on the page that may name an actor, because the
    # owner is part of the rule that selects the rows rather than a property of the
    # sub-type: People on one, Product on the other.
    # `Event Identification` left these lists with the value itself, retired on the
    # owner's call. `Model Classification Defect` takes its place rather than the rule
    # losing a member: the Product rule exists to say "the model misjudged a captured
    # event", and that sub-type is now the only Product-rooted value that means it.
    ("An analyst let it through", ("Review", "Model Classification Defect", "Analyst Review Miss"), ("People",), "#f28b82",
     "An analyst saw this event and chose not to report it · EventWatch Ops"),
    ("The model did not spot it", ("Review", "Model Classification Defect", "Analyst Review Miss"), ("Product",), "#f6c177",
     "The model had this event and did not flag it as reportable · Product"),
)
MISS_COLOURS = [c for _, _, _, c, _ in MISS_BUCKETS]


def miss_bucket_series(df):
    """The bucket each row falls in, or "" for a row that is not a missed event.

    One implementation, so the cards, the ring, the per-account table and the monthly
    split cannot disagree about which bucket a record belongs to. Buckets are applied in
    order and are mutually exclusive by construction: non-misses start out claimed so
    they can never take a bucket, and the last bucket has no sub-types, so it sweeps up
    whatever the others left and the slices always sum to the missed count however the
    taxonomy grows.
    """
    out = pd.Series("", index=df.index, dtype=object)
    if df.empty or not {"Missed_Flag", "Sub-type", "Root Cause"} <= set(df.columns):
        return out
    missed = df["Missed_Flag"].astype(str).str.strip().eq("Yes")
    sub = df["Sub-type"].fillna("Blank").astype(str).str.strip()
    root = df["Root Cause"].fillna("Blank").astype(str).str.strip()
    claimed = ~missed
    for label, subs, roots, _, _ in MISS_BUCKETS:
        hit = sub.isin(subs)
        if roots:
            hit = hit & root.isin(roots)
        hit = hit & ~claimed
        out[hit] = label
        claimed = claimed | hit
    # Everything the four named rules did not take keeps its own sub-type, in English.
    # `plain()` falls back to the raw value, so a sub-type added to the tracker tomorrow
    # appears under its own name rather than disappearing into a bucket.
    rest = ~claimed
    out[rest] = [failure_label(r, s) for r, s in zip(root[rest], sub[rest])]
    return out


def miss_categories(df):
    """Missed events split by what actually failed. Counts every missed record once.

    Colour here fails the dataviz normal-vision floor at five categorical slots -- the
    grey residue against --blue scores dE 9.5 -- which is legal only with secondary
    encoding, so every slice and every card carries its own label, count and share, and
    nothing on this block rests on colour alone. CVD separation passes at dE 8.5 worst
    all-pairs and 10.7 worst adjacent. Introducing a hue from outside the app's tokens to
    clear the remaining check would break the one-palette rule the rest of the dashboard
    keeps, which is the worse trade.
    """
    cols = ["Category", "Records", "% of Total"]
    buckets = miss_bucket_series(df)
    total = int((buckets != "").sum())
    if total == 0:
        return pd.DataFrame(columns=cols)
    counts = buckets[buckets != ""].value_counts()
    named = [label for label, *_ in MISS_BUCKETS]
    order = named + [k for k in counts.index if k not in named]
    out = pd.DataFrame({"Category": order})
    out["Records"] = [int(counts.get(label, 0)) for label in out["Category"]]
    out["_named"] = [0 if label in named else 1 for label in out["Category"]]
    out = (out[out["Records"] > 0]
           .sort_values(["Records", "_named"], ascending=[False, True])
           .drop(columns="_named").reset_index(drop=True))
    out["% of Total"] = (out["Records"] / total * 100).round(1).astype(str) + "%"
    return out


def miss_colours(df, table):
    """A colour per bucket: the four named ones keep theirs, the rest take their owner's.

    Eleven buckets is far past where categorical colour carries meaning, so colour here
    says *who fixes it* rather than trying to give every bucket its own hue. Each bar
    still carries its own name, count and share, so nothing rests on colour alone.
    """
    fixed = {label: colour for label, _, _, colour, _ in MISS_BUCKETS}
    buckets = miss_bucket_series(df)
    root = df.get("Root Cause", pd.Series(dtype=str)).fillna("").astype(str).str.strip()
    out = {}
    for label in table["Category"]:
        if label in fixed:
            out[label] = fixed[label]
            continue
        owners = root[buckets == label].value_counts()
        owner = str(owners.index[0]).strip() if len(owners) else ""
        out[label] = ROOT_COLOURS.get(owner, "#b6beca")
    return out


def root_recent_note(df, window=3, span=6, move=5.0):
    """One line naming the last `window` months' root-cause mix when the view is wider.

    The cards are cumulative over whatever the filter spans, and a cumulative mix buries
    a quarter in which the mix changed. It has: read over nine months the source bucket
    is a third of the misses, but over the last three it is first, and the model bucket
    falls to nothing. A reader taking the cumulative picture as "the picture" gets the
    wrong two priorities, which is exactly the misread this line exists to stop -- it is
    how a claim that source misses had not moved survived review, when 11 of the 20 had
    landed in the previous three months.

    Only shown when the frame spans more than `span` months, because below that the two
    windows are mostly the same emails and the line says nothing, and only for roots that
    moved `move` points or more -- listing all three would restate the cards.
    """
    if df.empty or "Email/JIRA Date" not in df.columns:
        return None
    months = pd.to_datetime(df["Email/JIRA Date"], errors="coerce").dt.to_period("M")
    order = sorted(m for m in months.dropna().unique())
    if len(order) <= span:
        return None
    recent = root_summary(df[months.isin(order[-window:])])
    overall = root_summary(df)
    if not recent or not overall:
        return None
    base = {root: share for root, _, share, _, _ in overall}
    moved = [(root, share, base.get(root, 0.0)) for root, _, share, _, _ in recent
             if abs(share - base.get(root, 0.0)) >= move]
    if not moved:
        return None
    total = sum(n for _, n, *_ in recent)
    label = lambda m: pd.Period(m, freq="M").strftime("%b %Y")
    parts = ", ".join(f"{root} {now:.0f}% (all months {was:.0f}%)" for root, now, was in moved)
    return (f"The cards are all {len(order)} months. Over the last {window} "
            f"({label(order[-window])}–{label(order[-1])}, {total} misses): {parts}.")


def inquiry_table(df):
    """Inquiries only: what they asked about, and what went back to them.

    An inquiry is one where the customer asked how something works rather than asserting
    we failed, and the test that settles it is what we did next: an explanation means
    inquiry, a bulletin or a correction means we were at fault and it is a complaint.
    That distinction is invisible on a table that counts complaints and inquiries in one
    column, so they get a table of their own.
    """
    cols = ["Category", "What they asked about", "Their exact wordings",
            "Inquiries", "% of these", "How we answered", "Was a real miss"]
    if df.empty or "Issue Type" not in df.columns:
        return pd.DataFrame(columns=cols)
    frame = df[df["Issue Type"].astype(str) == "Inquiry"].copy()
    if frame.empty:
        return pd.DataFrame(columns=cols)
    frame["_cat"] = reason_category(frame)
    total = len(frame)
    rows = []
    for name, group in frame.groupby("_cat"):
        wordings = group["Reason"].astype(str).str.strip().value_counts()
        answered = group.get("Short Term Fix Status", pd.Series(dtype=str)).astype(str).value_counts()
        missed = int((group.get("Missed_Flag", pd.Series(dtype=str)).astype(str) == "Yes").sum())
        rows.append({
            "Category": name,
            "What they asked about": CATEGORY_MEANING.get(name, ""),
            "Their exact wordings": "\n".join(f"• {w} ({n})" for w, n in wordings.items()),
            "Inquiries": len(group),
            "% of these": f"{len(group) / total * 100:.0f}%",
            "How we answered": "\n".join(f"• {k} ({n})" for k, n in answered.items()),
            "Was a real miss": missed,
        })
    out = pd.DataFrame(rows)[cols].sort_values("Inquiries", ascending=False).reset_index(drop=True)
    every = frame.get("Short Term Fix Status", pd.Series(dtype=str)).astype(str).value_counts()
    out.loc[len(out)] = {
        "Category": "Total", "What they asked about": "", "Their exact wordings": "",
        "Inquiries": total, "% of these": "100%",
        "How we answered": "\n".join(f"• {k} ({n})" for k, n in every.items()),
        "Was a real miss": int((frame.get("Missed_Flag", pd.Series(dtype=str)).astype(str) == "Yes").sum()),
    }
    return out


def subtype_matrix(df):
    """Sub-type by Root Cause. The taxonomy calls Sub-type the category *beneath* Root
    Cause, but nothing ever showed the two together -- so the fact that the two biggest
    sub-types are a pure People failure and a pure Product failure was invisible."""
    if not {"Sub-type", "Root Cause"} <= set(df.columns) or df.empty:
        return pd.DataFrame()
    grid = pd.crosstab(labels_for(df), df["Root Cause"].astype(str).str.strip())
    grid.index.name = "Sub-type"
    if grid.empty:
        return grid
    return grid.loc[grid.sum(axis=1).sort_values(ascending=False).index]


def missed_rate(df):
    """Missed-event rate per month. The count of complaints tracks how many tickets were
    raised; the share that were genuine misses is the part that says whether we improved."""
    dates = pd.to_datetime(df.get("Email/JIRA Date"), errors="coerce")
    flag = df.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes")
    g = pd.DataFrame({"Month": dates.dt.to_period("M").astype(str), "Missed": flag}).dropna(subset=["Month"])
    if g.empty: return pd.DataFrame(columns=["Month", "Records", "Missed", "Missed %"])
    out = g.groupby("Month").agg(Records=("Missed", "size"), Missed=("Missed", "sum")).reset_index()
    out["Missed %"] = (out["Missed"] / out["Records"] * 100).round(0)
    return out.sort_values("Month")


def _share(frame, col, value):
    return (frame[col].astype(str).str.strip().eq(value).mean() * 100) if len(frame) else 0.0


def missed_verdict(rate, window=3, noise=5.0):
    """Say in words whether the miss rate is coming down, in a sentence a director reads.

    A grid of monthly percentages does not answer "are we getting better", and the
    honest answer here is no -- nine months in, the rate has not moved. Stating that
    is the point of the KPI; leaving the reader to eyeball nine numbers is how it went
    unnoticed.

    Compared on POOLED counts, not the mean of monthly percentages: a month with four
    emails would otherwise carry the same weight as one with eighteen. A move smaller
    than `noise` points is reported as flat rather than dressed up as a trend, and the
    latest month is flagged when it is too thin to lean on -- these are 10-20 emails a
    month, and reading a trend into that noise is worse than reading none.
    """
    if len(rate) < window * 2:
        return None
    recent, prior = rate.tail(window), rate.iloc[-window * 2:-window]
    now = recent["Missed"].sum() / max(recent["Records"].sum(), 1) * 100
    was = prior["Missed"].sum() / max(prior["Records"].sum(), 1) * 100
    delta = now - was
    label = lambda m: pd.Period(m, freq="M").strftime("%b %Y")
    span = (f"{label(recent['Month'].iloc[0])}–{label(recent['Month'].iloc[-1])} "
            f"against {was:.0f}% in {label(prior['Month'].iloc[0])}–{label(prior['Month'].iloc[-1])}")
    # One decimal on the gap and on both rates. Rounded to whole points, a 4.5-point
    # move printed as "a 5-point move ... which is noise" against a 5-point threshold,
    # which reads as the sentence contradicting itself.
    if delta <= -noise:
        verdict, colour = "Improving", "#a8dab5"
        sentence = f"down {abs(delta):.1f} points"
    elif delta >= noise:
        verdict, colour = "Getting worse", "#f28b82"
        sentence = f"up {delta:.1f} points"
    else:
        verdict, colour = "Not improving", "#f6c177"
        sentence = f"a {abs(delta):.1f}-point move, which is noise at this volume"
    detail = (f"{now:.0f}% of customer emails were confirmed misses in {span} — {sentence}. "
              f"{int(recent['Missed'].sum())} of {int(recent['Records'].sum())} emails.")
    thin = rate.iloc[-1]
    if thin["Records"] < 8:
        # `plural()`, because the first email of a new month makes this read "has only
        # 1 emails so far" on the Executive Summary -- which is exactly when a reader is
        # most likely to be looking at it.
        detail += f" {label(thin['Month'])} has only {plural(int(thin['Records']), 'email')} so far."
    return verdict, detail, colour, now


def customer_exposure(df, base=None):
    """Count a multi-customer row once for each customer named in it.

    `Ford/GM` is one incident but two affected accounts, and the Excel Dashboard's
    COUNTIFS matches the whole string, so a merged row drops out of both customers'
    totals and appears as its own category. This splits on the slash so "how many
    incidents touched Ford" has an answer. It deliberately differs from the canonical
    count above, which stays exact-match so the app and the workbook agree.
    """
    if df.empty or "Customer" not in df.columns:
        return pd.DataFrame(columns=["Customer", "Records", "% of Total"])
    exploded = (df.assign(_c=df["Customer"].fillna("Blank").astype(str).str.split("/"))
                  .explode("_c"))
    keys = exploded["_c"].str.strip().replace("", "Blank")
    t = keys.value_counts().reset_index()
    t.columns = ["Customer", "Records"]
    parts = split_by_issue(exploded, keys, pd.Index(t["Customer"]))
    for name in ("Complaints", "Inquiries"):
        if name in parts.columns:
            t[name] = parts[name].values
    denom = max(base or len(df), 1)
    t["% of Total"] = (t["Records"] / denom * 100).round(1).astype(str) + "%"
    return t[[c for c in ["Customer", "Complaints", "Inquiries", "Records", "% of Total"] if c in t.columns]]


def owner_accounts(root_df, page):
    """Which accounts this owner's failures actually land on, and what it costs them.

    This replaces a `long_pair_table(root_df, "Customer", "Reason")` dump, which printed
    one row per customer-and-wording pair -- forty wordings against thirty-three accounts,
    so the table was long, unranked, and said nothing the tables above it had not already
    said. The question a drill-down is for is "whose problem is this", and that needs the
    account's own base beside the count: 12 Product failures at Ford is a different fact
    from 12 at an account that only ever sent 12 emails.
    """
    cols = ["Customer", "Emails", "Misses", "Their total", "Share of theirs",
            "What went wrong most", "What they wrote about most"]
    if root_df.empty or "Customer" not in root_df.columns:
        return pd.DataFrame(columns=cols)
    rows = []
    for name in customer_names(root_df["Customer"]):
        here = root_df[names_match(root_df["Customer"], [name])]
        if here.empty:
            continue
        theirs = page[names_match(page["Customer"], [name])]
        # The label, not the raw sub-type, and read off each row's own owner rather
        # than a parameter this function does not take: `Mapping` means a different
        # failure under each owner, so the mode has to be taken over labels.
        sub = labels_for(here)
        sub = sub[sub.ne("") & sub.ne("nan") & sub.ne("Blank")]
        cat = reason_category(here)
        cat = cat[cat.ne("")]
        rows.append({
            "Customer": name,
            "Emails": len(here),
            "Misses": int(here.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes").sum()),
            "Their total": len(theirs),
            "Share of theirs": f"{len(here) / max(len(theirs), 1) * 100:.0f}%",
            "What went wrong most": sub.value_counts().index[0] if not sub.empty else "",
            "What they wrote about most": cat.value_counts().index[0] if not cat.empty else "",
        })
    if not rows:
        return pd.DataFrame(columns=cols)
    return pd.DataFrame(rows).sort_values(["Emails", "Misses"],
                                          ascending=False).reset_index(drop=True)[cols]


def owner_insight(root, root_df, page):
    """One computed sentence naming this owner's biggest failure and worst account."""
    if root_df.empty:
        return ""
    miss = root_df.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes")
    sub = root_df["Sub-type"].fillna("").astype(str).str.strip()
    sub = sub[sub.ne("") & sub.ne("nan")]
    first = (f"<b>{esc(root)}</b> carries {plural(len(root_df), 'customer email')}, "
             f"{int(miss.sum())} of them confirmed misses")
    if not sub.empty:
        top = sub.value_counts()
        first += (f", and {int(top.iloc[0])} of those emails are "
                  f"<b>{esc(failure_label(root, top.index[0]))}</b>")
    out = [first]
    accounts = owner_accounts(root_df, page)
    if not accounts.empty:
        worst = accounts.iloc[0]
        out.append(f"The account most exposed to it is <b>{esc(worst['Customer'])}</b> — "
                   f"{int(worst['Emails'])} of their "
                   f"{plural(int(worst['Their total']), 'email')} "
                   f"({worst['Share of theirs']})")
    return ". ".join(out) + "."


def account_failures(frame):
    """One account's failures at full granularity: owner, what went wrong, both bases.

    "Customer root-cause patterns" used to be Product / People / Process and nothing
    else, which names the team and not the problem -- "Ford: Product 34" tells a reader
    who to go and see and nothing about what to say when they get there. This keys on the
    (Root Cause, Sub-type) pair, so the owner is still there and the failure sits beside
    it in the words the rest of the dashboard uses.
    """
    cols = ["What went wrong", "Owner", "Emails", "Misses", "Reported timely", "% of Total"]
    if frame.empty or not {"Root Cause", "Sub-type"} <= set(frame.columns):
        return pd.DataFrame(columns=cols)
    work = pd.DataFrame({
        "What went wrong": labels_for(frame),
        "_owner": frame["Root Cause"].fillna("Blank").astype(str).str.strip(),
        "_miss": frame.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes"),
    })
    rows = []
    for label, group in work.groupby("What went wrong"):
        misses = int(group["_miss"].sum())
        rows.append({"What went wrong": label,
                     "Owner": owner_pills(group["_owner"].value_counts()),
                     "Emails": len(group), "Misses": misses,
                     "Reported timely": len(group) - misses})
    out = pd.DataFrame(rows).sort_values(["Emails", "Misses"], ascending=False).reset_index(drop=True)
    out["% of Total"] = (out["Emails"] / max(int(out["Emails"].sum()), 1) * 100).round(1).astype(str) + "%"
    return out[cols]


def account_headline(name, frame, page):
    """What this account's numbers actually say, in one computed sentence."""
    if frame.empty:
        return ""
    miss = int(frame.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes").sum())
    rate = miss / max(len(frame), 1) * 100
    whole = len(page.get("Customer", pd.Series(dtype=str)))
    out = [f"<b>{esc(name)}</b> sent {plural(len(frame), 'email')} — "
           f"{len(frame) / max(whole, 1) * 100:.0f}% of everything in this filter — "
           f"and {miss} of them ({rate:.0f}%) were confirmed misses"]
    fails = account_failures(frame)
    second = ""
    if not fails.empty:
        top = fails.iloc[0]
        second = (f"Their biggest single failure is <b>{esc(top['What went wrong'])}</b>, "
                  f"{int(top['Emails'])} of their {len(frame)} emails")
    cats = reason_category(frame)
    cats = cats[cats.ne("")]
    if not cats.empty:
        top_cat = cats.value_counts()
        tail = (f"what they wrote about most is <b>{esc(top_cat.index[0])}</b> "
                f"({int(top_cat.iloc[0])})")
        second = f"{second}, and {tail}" if second else tail[0].upper() + tail[1:]
    if second:
        out.append(second)
    return ". ".join(out) + "."


def overview_split(df):
    """Every email in three mutually exclusive parts: a failure, a complaint that was
    not one, and a question.

    This is the first thing a reader needs and no chart said it: not every complaint is
    a miss, and not every email is a complaint.
    """
    cols = ["Category", "Records", "% of Total"]
    if df.empty or not {"Issue Type", "Missed_Flag"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    issue = df["Issue Type"].astype(str).str.strip()
    missed = df["Missed_Flag"].astype(str).str.strip().eq("Yes")
    out = pd.DataFrame([
        {"Category": "Confirmed misses", "Records": int(missed.sum())},
        {"Category": "Complaints, not a miss", "Records": int((issue.eq("Complaint") & ~missed).sum())},
        {"Category": "Inquiries", "Records": int(issue.eq("Inquiry").sum())},
    ])
    out["% of Total"] = (out["Records"] / max(len(df), 1) * 100).round(1).astype(str) + "%"
    return out


def root_summary(df):
    """Confirmed misses per root cause, biggest first, with each one's share.

    Rows are [(root, misses, share, ownership, colour)]. Only roots that actually carry
    a miss in the current filter appear, so a filtered view does not print a card whose
    number is zero.
    """
    if df.empty or not {"Root Cause", "Missed_Flag"} <= set(df.columns):
        return []
    missed = df[df["Missed_Flag"].astype(str).str.strip().eq("Yes")]
    if missed.empty:
        return []
    counts = missed["Root Cause"].fillna("Blank").astype(str).str.strip().value_counts()
    total = max(int(counts.sum()), 1)
    return [(root, int(n), n / total * 100,
             ROOT_OWNERSHIP.get(root, "Ownership not defined"),
             ROOT_COLOURS.get(root, "#b6beca"))
            for root, n in counts.items()]


def root_drivers(df, root, top=4):
    """The failure drivers behind one root cause's confirmed misses, biggest first.

    Only the top `top` are named; the rest collapse into one `Other` row whose own
    hover lists what is in it, so the fold can be checked rather than trusted.
    `Needs Review` never folds -- it is a data-quality signal, and burying it in Other
    is how a mis-filed row stays mis-filed.
    """
    cols = ["Driver", "What it means", "Misses", "% of Total"]
    if df.empty or not {"Root Cause", "Sub-type", "Missed_Flag"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    missed = df[(df["Missed_Flag"].astype(str).str.strip().eq("Yes"))
                & (df["Root Cause"].fillna("").astype(str).str.strip().eq(root))]
    if missed.empty:
        return pd.DataFrame(columns=cols)
    named = [driver_of(root, v) for v in missed["Sub-type"].fillna("").astype(str)]
    frame = pd.DataFrame({"Driver": [t for t, _ in named], "What it means": [m for _, m in named]})
    grouped = (frame.groupby(["Driver", "What it means"]).size()
                    .reset_index(name="Misses").sort_values("Misses", ascending=False))
    review = grouped[grouped["Driver"] == NEEDS_REVIEW]
    rest = grouped[grouped["Driver"] != NEEDS_REVIEW]
    keep, tail = rest.head(top), rest.iloc[top:]
    # An `Other` holding one driver hides a name to save no space -- "Other: 1 smaller
    # driver: Industry Selection (1)" is longer than "Industry Selection". Fold only when
    # there are at least two to fold.
    if len(tail) == 1:
        keep, tail = rest.head(top + 1), rest.iloc[top + 1:]
    rows = keep.to_dict("records")
    if not tail.empty:
        # The fold names itself. `Other` on a leadership chart is only honest if the
        # reader can find out what is in it without leaving the chart, so the row carries
        # every driver it swallowed, with each one's count, on its own hover.
        inside = ", ".join(f"{r['Driver']} ({int(r['Misses'])})" for _, r in tail.iterrows())
        rows.append({"Driver": DRIVER_OTHER,
                     "What it means": f"{plural(len(tail), 'smaller driver')}: {inside}",
                     "Misses": int(tail["Misses"].sum())})
    rows += review.to_dict("records")
    out = pd.DataFrame(rows)
    total = max(int(out["Misses"].sum()), 1)
    out["% of Total"] = (out["Misses"] / total * 100).round(1).astype(str) + "%"
    return out[cols].reset_index(drop=True)


def driver_table(df):
    """Every driver on one table, one row each, with the root causes that produced it.

    Grouped by driver rather than by root-and-driver, because a driver that occurs under
    two roots -- `Needs Review` does, on the current data -- would otherwise appear as
    two rows carrying the same name and different numbers, which reads as a duplicate and
    gives `audit_pages.py` two counts for one label. The roots ride in their own column
    with their counts, the way `root_frame()` carries owners.
    """
    cols = ["Driver", "Owner", "What it means", "Misses", "% of Total"]
    rows = []
    for root, _, _, _, _ in root_summary(df):
        for _, r in root_drivers(df, root, top=99).iterrows():
            rows.append({"Driver": r["Driver"], "Owner": root,
                         "What it means": r["What it means"], "Misses": int(r["Misses"])})
    if not rows:
        return pd.DataFrame(columns=cols)
    frame = pd.DataFrame(rows)
    out = []
    for driver, group in frame.groupby("Driver"):
        roots = group.groupby("Owner")["Misses"].sum().sort_values(ascending=False)
        # The column is named Owner rather than Root cause because that is the question
        # it answers on a leadership page, and it renders as one pill per owner for the
        # same reason the deeper-root-cause table does: two names and two numbers run
        # together in one string is not a column anybody reads.
        out.append({"Driver": driver,
                    "Owner": owner_pills(roots),
                    "What it means": group["What it means"].iloc[0],
                    "Misses": int(group["Misses"].sum())})
    table = pd.DataFrame(out).sort_values("Misses", ascending=False).reset_index(drop=True)
    total = max(int(table["Misses"].sum()), 1)
    table["% of Total"] = (table["Misses"] / total * 100).round(1).astype(str) + "%"
    return table[cols]


def takeaway(df):
    """One sentence, every figure in it computed from the frame on screen.

    Named the largest root cause and its two biggest drivers, or says plainly when there
    is not enough in the filter to name them -- a takeaway that invents a finding when
    the data has none is the horoscope problem in one line.
    """
    summary = root_summary(df)
    if not summary:
        return None
    root, misses, share, _, colour = summary[0]
    drivers = root_drivers(df, root, top=99)
    drivers = drivers[~drivers["Driver"].isin([DRIVER_OTHER, NEEDS_REVIEW])]
    if drivers.empty:
        return (f"Most confirmed misses are concentrated in <b>{esc(root)}</b> "
                f"({misses} of {int(sum(n for _, n, *_ in summary))}, {share:.0f}%).", colour)
    top_two = drivers.head(2)
    named = ", ".join(f"{r['Driver']} ({int(r['Misses'])})" for _, r in top_two.iterrows())
    total = int(sum(n for _, n, *_ in summary))
    return (f"Most confirmed misses are concentrated in <b>{esc(root)}</b> — "
            f"{misses} of {total}, {share:.0f}% — primarily driven by <b>{esc(named)}</b>.",
            colour)


def miss_owner_split(df):
    """The confirmed misses by who has to fix them, as the second ring.

    Named `Product` / `People` / `Process`, the tracker's own values, so the ring and the
    three cards below it speak one vocabulary -- it briefly read "The platform / Our
    analysts / How we work" here and the tracker's names in the section underneath, which
    is two words for one thing on one page. The ownership line rides on each slice's
    hover instead, which is where the plain English belongs.
    """
    cols = ["Category", "Records", "% of Total"]
    if df.empty or not {"Missed_Flag", "Root Cause"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    missed = df[df["Missed_Flag"].astype(str).str.strip().eq("Yes")]
    if missed.empty:
        return pd.DataFrame(columns=cols)
    out = missed["Root Cause"].fillna("Blank").astype(str).str.strip().value_counts().reset_index()
    out.columns = ["Category", "Records"]
    out["% of Total"] = (out["Records"] / max(len(missed), 1) * 100).round(1).astype(str) + "%"
    return out


def miss_by_customer(df):
    """One row per account: emails and what they were, then the misses by what failed.

    The email columns exist because "44" on its own does not say 44 of what. `Emails` is
    every email that named the account, complaints and inquiries together, and the two
    columns beside it break that down; `Misses` and the failure columns count only the
    confirmed misses, which is a smaller number from a different base. Both bases are on
    the row rather than left to a caption.

    Accounts are split on the slash, the same rule `customer_exposure()` uses, so a
    `Ford/GM` email counts for both and the email totals agree with every other page.
    That also means the Emails column sums to more than the tracker holds -- a merged
    email is counted once per account it names -- which the total row shows honestly
    rather than hiding.
    """
    if df.empty or "Customer" not in df.columns:
        return pd.DataFrame(columns=["Customer", "Emails", "Complaints", "Inquiries", "Misses"])
    frame = df.assign(_bucket=miss_bucket_series(df))
    # explode() repeats the source index, and crosstab cannot reindex a duplicated axis,
    # so the exploded frame gets a fresh one.
    exploded = (frame.assign(_c=frame["Customer"].fillna("Blank").astype(str).str.split("/"))
                     .explode("_c").reset_index(drop=True))
    exploded["_c"] = exploded["_c"].str.strip().replace("", "Blank")
    issue = exploded.get("Issue Type", pd.Series(dtype=str)).astype(str).str.strip()
    emails = exploded["_c"].value_counts()
    grid = pd.crosstab(exploded["_c"], exploded["_bucket"])
    labels = [c for c in miss_categories(df)["Category"] if c in grid.columns]
    out = pd.DataFrame({"Customer": list(emails.index), "Emails": list(emails.values)})
    for name, value in (("Complaints", "Complaint"), ("Inquiries", "Inquiry")):
        counts = exploded["_c"][issue.eq(value)].value_counts()
        out[name] = [int(counts.get(c, 0)) for c in out["Customer"]]
    for label in labels:
        out[label] = [int(grid.loc[c, label]) if c in grid.index else 0 for c in out["Customer"]]
    out["Misses"] = out[labels].sum(axis=1) if labels else 0
    # Against the tracker's own miss count, NOT the sum of this column: the column
    # double-counts every email that names two accounts, so a share taken from it would
    # be a share of a number that appears nowhere else on the dashboard.
    total = max(int((miss_bucket_series(df) != "").sum()), 1)
    out["% of Total"] = (out["Misses"] / total * 100).round(1).astype(str) + "%"
    cols = ["Customer", "Emails", "Complaints", "Inquiries"] + labels + ["Misses", "% of Total"]
    return out[cols].sort_values(["Misses", "Emails"], ascending=False).reset_index(drop=True)


def customer_totals(df):
    """The true column totals for `miss_by_customer()`, and how far its rows overshoot.

    Returns `(totals, overshoot)`. The per-account rows deliberately double-count: an
    email naming `Ford/GM` is one email in the tracker and a row on both accounts, which
    is the rule the whole app uses so that "how many emails touched Ford" has an answer.
    Adding the columns up therefore prints 120 emails against a tracker of 115 -- a
    number that appears nowhere else on the dashboard, and the first thing a reader
    challenges. The total row carries these figures instead, and `overshoot` is what the
    caption needs to explain the gap rather than leave it to be noticed.
    """
    issue = df.get("Issue Type", pd.Series(dtype=str)).astype(str).str.strip()
    buckets = miss_bucket_series(df)
    totals = {"Emails": len(df),
              "Complaints": int(issue.eq("Complaint").sum()),
              "Inquiries": int(issue.eq("Inquiry").sum()),
              "Misses": int((buckets != "").sum())}
    for label, n in buckets[buckets != ""].value_counts().items():
        totals[label] = int(n)
    shared = df["Customer"].fillna("").astype(str).str.contains("/") if "Customer" in df.columns else pd.Series(dtype=bool)
    overshoot = {"emails": int(shared.sum()),
                 "misses": int((shared & (buckets != "")).sum())}
    return totals, overshoot


def missed_event_types(df):
    """What kinds of event we actually miss -- fires, insolvencies, port disruption.

    Counted over the confirmed misses only. The block that used to sit here was titled
    "Missed event types" and counted every email, misses and non-misses alike, so it
    answered a different question from the one its own heading asked.
    """
    cols = ["Event type", "Records", "% of Total"]
    if df.empty or not {"Event type", "Missed_Flag"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    missed = df[df["Missed_Flag"].astype(str).str.strip().eq("Yes")]
    if missed.empty:
        return pd.DataFrame(columns=cols)
    out = missed["Event type"].fillna("Blank").astype(str).str.strip().value_counts().reset_index()
    out.columns = ["Event type", "Records"]
    out["% of Total"] = (out["Records"] / max(len(missed), 1) * 100).round(1).astype(str) + "%"
    return out


def all_event_types(df):
    """Every email by event type, with the complaint/inquiry split on the row.

    The miss table beside it answers "what do we fail to report"; this answers "what do
    customers write to us about at all", and neither is readable without the other -- a
    9-miss event type is a different fact depending on whether 10 emails named it or 40.
    Same shape as `count_table`, so the Complaints and Inquiries columns are the ones
    every other page carries.
    """
    cols = ["Event type", "Complaints", "Inquiries", "Records", "% of Total"]
    if df.empty or "Event type" not in df.columns:
        return pd.DataFrame(columns=cols)
    return count_table(df, "Event type")


def event_type_pairs(df):
    """Event type by emails AND confirmed misses on one row, with the miss rate.

    The two tables on their own leave the reader subtracting: this is the column that
    says which event types we are actually bad at, as against the ones we merely get a
    lot of. The rate carries its own base, because 100% of one email is not a finding.
    """
    # ONE split per table. This carried `Reported timely` and a `Miss rate` as well, so
    # a reader met two different partitions of the same 16 emails -- 14 complaints + 2
    # inquiries, and 13 misses + 3 reported timely -- and tried to reconcile 14 against
    # 13, which do not reconcile because they are not the same cut. The page owner read
    # it as broken arithmetic, which is the correct reading of two partitions printed as
    # one table. Emails = Complaints + Inquiries, and the misses column is named in the
    # caption as a SUBSET of the complaints rather than a third part of the split.
    cols = ["Event type", "Complaints", "Inquiries", "Emails", "Misses", "% of Total"]
    if df.empty or not {"Event type", "Missed_Flag"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    frame = df.copy()
    frame["Event type"] = frame["Event type"].fillna("Blank").astype(str).str.strip()
    frame["_miss"] = frame.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes")
    issue = frame.get("Issue Type", pd.Series("", index=frame.index)).astype(str).str.strip()
    rows = []
    for value, group in frame.groupby("Event type"):
        misses = int(group["_miss"].sum())
        rows.append({"Event type": value, "Emails": len(group),
                     "Complaints": int(issue.loc[group.index].eq("Complaint").sum()),
                     "Inquiries": int(issue.loc[group.index].eq("Inquiry").sum()),
                     "Misses": misses})
    out = pd.DataFrame(rows).sort_values(["Misses", "Emails"], ascending=False).reset_index(drop=True)
    total = max(int(out["Misses"].sum()), 1)
    out["% of Total"] = (out["Misses"] / total * 100).round(1).astype(str) + "%"
    return out[cols]


def nature_table(df):
    """The reusable categories behind what customers actually wrote.

    The same fold, the same words and now the same meaning text the All customer emails
    tab defines -- so a reader who stops on a category name here reads one sentence
    about it, not a different one on each tab.
    """
    if df.empty or "Reason" not in df.columns:
        return pd.DataFrame(columns=["Category", "What it means", "Complaints", "Inquiries",
                                     "Misses", "Reported timely", "Records", "% of Total"])
    frame = df.copy()
    frame["Category"] = reason_category(df)
    out = count_table(frame, "Category")
    out.insert(1, "What it means", out["Category"].map(CATEGORY_MEANING).fillna(""))
    return out


def trend_windows(df, window=3):
    """The monthly miss rate, plus the pooled rate of the last `window` months and the
    `window` before them.

    Pooled on counts, never on the mean of the monthly percentages: a month with 4
    emails must not weigh the same as one with 18. Returns `(rate, band)` with band None
    when there are not two full windows to compare, because two averages drawn over
    four months of data is a shape, not a finding.
    """
    rate = missed_rate(df)
    if len(rate) < window * 2:
        return rate, None
    def pooled(part):
        emails, misses = int(part["Records"].sum()), int(part["Missed"].sum())
        # `missed` rides along so a caller can print "31 of 45" rather than reverse the
        # percentage back into a count, which rounds and can land a record off.
        return {"months": list(part["Month"]), "emails": emails, "missed": misses,
                "value": misses / max(emails, 1) * 100}
    return rate, {"older": pooled(rate.iloc[-window * 2:-window]), "recent": pooled(rate.tail(window))}


def trend_table(rate, band):
    """The monthly series as a table, with a total whose share is pooled, not averaged."""
    if rate.empty:
        return pd.DataFrame(columns=["Month", "Emails", "Confirmed misses", "Miss rate"])
    out = pd.DataFrame({
        "Month": [pd.Period(m, freq="M").strftime("%b %Y") for m in rate["Month"]],
        "Emails": rate["Records"].astype(int).values,
        "Confirmed misses": rate["Missed"].astype(int).values,
    })
    out["Miss rate"] = (out["Confirmed misses"] / out["Emails"].clip(lower=1) * 100).round(0).astype(int).astype(str) + "%"
    emails, misses = int(out["Emails"].sum()), int(out["Confirmed misses"].sum())
    out.loc[len(out)] = {"Month": "Total", "Emails": emails, "Confirmed misses": misses,
                         "Miss rate": f"{misses / max(emails, 1) * 100:.0f}%"}
    return out


def root_frame(df):
    """One row per failure: how many emails named it, and how many of those were misses.

    Both numbers on one row is the point -- `Review` is 22 emails of which 19 were
    confirmed misses, `Process Clarification` is 13 emails of which 2 were. A table of
    misses alone cannot say which failures we mostly get away with.

    Keyed on the failure, not on failure-and-owner: the same sub-type sits under two
    owners on several rows, and a chart whose y axis repeats a label silently merges the
    two. The owners are kept as a column that names them with their counts, so nothing is
    lost -- and the four buckets on "Why the events were missed" already split the ones
    where the owner changes the answer.
    """
    cols = ["What went wrong", "Owner", "Tracker value", "Emails", "Misses",
            "Reported timely", "% of Total"]
    if df.empty or not {"Root Cause", "Sub-type"} <= set(df.columns):
        return pd.DataFrame(columns=cols)
    frame = pd.DataFrame({
        "_value": df["Sub-type"].fillna("Blank").astype(str).str.strip(),
        "_owner": df["Root Cause"].fillna("Blank").astype(str).str.strip(),
        "_miss": df.get("Missed_Flag", pd.Series(dtype=str)).astype(str).str.strip().eq("Yes"),
    })
    # Grouped on the LABEL, not on the sub-type. Two pairs of tracker values deliberately
    # share a label (`Prioritization`/`Captured Late`, `Tagging`/`Industry selection`), and
    # grouping on the value would draw two bars carrying the same name -- which a y axis
    # silently merges, and which gives `audit_pages.py` two counts for one label. Both
    # tracker values ride in the `Tracker value` column, so nothing is hidden by the fold.
    frame["What went wrong"] = labels_for(df)
    rows = []
    misses_total = max(int(frame["_miss"].sum()), 1)
    for label, group in frame.groupby("What went wrong"):
        owners = group["_owner"].value_counts()
        values = group["_value"].value_counts()
        rows.append({
            "What went wrong": label,
            "Owner": owner_pills(owners),
            "Tracker value": " · ".join(values.index) if len(values) > 1 else values.index[0],
            "Emails": len(group),
            "Misses": int(group["_miss"].sum()),
            "Reported timely": len(group) - int(group["_miss"].sum()),
        })
    out = pd.DataFrame(rows)
    out["% of Total"] = (out["Misses"] / misses_total * 100).round(1).astype(str) + "%"
    return out[cols].sort_values(["Misses", "Emails"], ascending=False).reset_index(drop=True)


def event_type_note(df):
    """One worked example under the event-type table, every figure computed.

    "The fourteenth was reported, and the customer wrote in about something else on it"
    was the wording before, and the page's owner asked the obvious question: what else?
    A caption that waves at a category without naming it is the thing it was written to
    prevent. This takes the biggest event type, splits its complaints into the ones that
    were confirmed misses and the ones that were not, and **names what the rest were
    actually about** -- the reason category the customer's own wording folds onto.
    Computed, so it follows the filter and cannot go stale.
    """
    if df.empty or not {"Event type", "Issue Type", "Missed_Flag"} <= set(df.columns):
        return ""
    pairs = event_type_pairs(df)
    if pairs.empty:
        return ""
    top = pairs.sort_values("Emails", ascending=False).iloc[0]
    name = top["Event type"]
    block = df[df["Event type"].fillna("Blank").astype(str).str.strip().eq(name)]
    complaints = int(top["Complaints"]); misses = int(top["Misses"])
    rest = complaints - misses
    line = (f"**{esc(name)}** reads {plural(int(top['Emails']), 'email')} — "
            f"{plural(complaints, 'complaint')} and {plural(int(top['Inquiries']), 'inquiry', 'inquiries')}. "
            f"{misses} of those complaints were confirmed misses")
    if rest <= 0:
        return line + ", and there were no others."
    others = block[block["Issue Type"].astype(str).str.strip().eq("Complaint")
                   & block["Missed_Flag"].astype(str).str.strip().ne("Yes")]
    # The customer's OWN wording, not the folded category: "Classified wrongly" is still
    # a bucket name, and the question asked of the old caption was what, specifically.
    # Here that is "Incorrect Industry selection" -- we reported the fire and the
    # Automotive tag was missing, which is a different complaint from not reporting it.
    reasons = others["Reason"].fillna("").astype(str).str.strip()
    reasons = reasons[reasons.ne("")].value_counts()
    were = "is not a miss" if rest == 1 else "are not misses"
    if reasons.empty:
        return f"{line}, and the other {plural(rest, 'complaint')} we did report."
    shown = [r if n == 1 else f"{r} ({n})" for r, n in list(reasons.items())[:3]]
    more = len(reasons) - len(shown)
    named = ", ".join(shown) + (f", and {plural(more, 'other reason')}" if more else "")
    return (f"{line}. The other {plural(rest, 'complaint')} {were} — "
            f"**we did report the event**, and what the customer raised was: {named}.")


# ---------------------------------------------------------------------------------
# The card popups.
#
# Every figure a popup prints is computed here, off the frame on screen, and from the
# same functions the cards and the charts already use. The eight mockups these came
# from went stale inside three days because their numbers were typed into the markup,
# which is the fault this file exists to prevent: a popup that recomputes a figure its
# own card already shows is a second implementation waiting to disagree with the first.
#
# Colour carries one thing on these panels and nothing else: who fixes it. Product is
# `--blue`, EventWatch Ops `--red`, a delivered bulletin that was wrong `--amber`, and
# a row that belongs to nobody takes `--muted`. Nothing is shaded by its own size --
# fading a bar by its value spends the only free channel restating the bar's length,
# and the dataviz check calls it out as a value ramp on nominal categories. Every row
# carries its name and count, so nothing rests on colour alone, which is also what
# relieves the grey rows of the contrast floor.
# ---------------------------------------------------------------------------------

POP_MUTED = "#515a68"
POP_NEUTRAL = "#b6beca"


def _named_tail(counts, top=5, noun="failure", nouns=None):
    """The `top` biggest entries, then one row naming everything left over.

    The same bargain `root_drivers()` strikes: a tail row on a leadership panel is only
    honest if the reader can see what went into it without leaving the panel, so the
    row carries every name it swallowed. A tail of exactly one is shown by its own name
    instead, because "1 smaller failure: Industry Selection (1)" is longer than
    "Industry Selection" and hides a name to save no space.
    """
    items = [(str(k), int(v)) for k, v in counts.items() if int(v) > 0]
    items.sort(key=lambda kv: (-kv[1], kv[0]))
    if len(items) <= top + 1:
        return items, None
    head, tail = items[:top], items[top:]
    names = ", ".join(f"{k} ({v})" for k, v in tail)
    return head, (plural(len(tail), f"smaller {noun}", f"smaller {nouns or noun + 's'}"),
                  sum(v for _, v in tail), names)


def _miss_parts(df):
    """The three stages a missed story can stop at, and the rows behind each.

    Keyed on exactly what the two Executive Summary cards key on, so the popup can
    never disagree with the card that opened it: the first stage is the two capture
    buckets from `MISS_BUCKETS`, the third is every People-rooted miss (the owner rule,
    not a bucket index), and the middle is the remainder. The three are a partition by
    construction, so they always sum to the miss count however the taxonomy grows.
    """
    buckets = miss_bucket_series(df)
    missed = buckets != ""
    root = df.get("Root Cause", pd.Series(dtype=str)).reindex(df.index).fillna("").astype(str).str.strip()
    source = buckets == MISS_BUCKETS[0][0]
    keyword = buckets == MISS_BUCKETS[1][0]
    analyst = missed & root.eq("People")
    platform = missed & ~source & ~keyword & ~analyst
    return {"missed": missed, "source": source, "keyword": keyword,
            "analyst": analyst, "platform": platform}


# What a People-rooted miss says the analyst actually did. The keys are tracker
# sub-types; anything not named here keeps its own plain label, so a value added
# tomorrow appears under its own name rather than vanishing into a residue row -- the
# same rule `miss_bucket_series()` follows for the miss buckets.
ANALYST_ACTIONS = (
    ("They judged it not impactful", MISS_BUCKETS[2][1],
     "The story was closed at review, so no alert and no WarRoom were ever raised"),
    ("They sent it, too late to act on", ("Published Late", "Captured Late", "Prioritization"),
     "The customer had already heard it elsewhere by the time we published"),
    ("They tagged the wrong industry", ("Tagging", "Industry selection"),
     "We published it, and the tag kept it off this customer's portal"),
    ("They missed the supplier entirely", ("Supplier Selection Miss", "Mapping"),
     "The supplier was on file and was not selected, so no WarRoom was created"),
)


def _analyst_actions(df, mask):
    """The People-rooted misses grouped by what the analyst did, biggest first."""
    sub = df.get("Sub-type", pd.Series(dtype=str)).reindex(df.index).fillna("").astype(str).str.strip()
    rows, claimed = [], pd.Series(False, index=df.index)
    for name, subs, gloss in ANALYST_ACTIONS:
        hit = mask & sub.isin(subs) & ~claimed
        if int(hit.sum()):
            rows.append((name, int(hit.sum()), gloss))
        claimed = claimed | hit
    rest = mask & ~claimed
    if int(rest.sum()):
        for label, count in labels_for(df[rest]).value_counts().items():
            rows.append((str(label), int(count), "A People-rooted miss outside the four actions above"))
    return sorted(rows, key=lambda r: -r[1])


def card_details(df):
    """One payload per Executive Summary card, in card order.

    A payload is data, not markup: `components.detail_panel()` draws it. Keeping the
    two apart is the same split the rest of this package keeps -- a panel can be
    restyled without touching a total, and a total cannot be changed by a styling edit.

    Every panel carries the same seven parts, because eight panels that each invent
    their own shape are eight things a reader has to learn: where the figure sits in
    the funnel, the question it answers, the figure with its base, one computed
    finding, the breakdown with a plain-English line under every row, the arithmetic
    that proves the breakdown sums, and the caveat that stops the obvious misreading.
    """
    total = len(df)
    if total == 0:
        return []
    issue = df.get("Issue Type", pd.Series(dtype=str)).reindex(df.index).astype(str).str.strip()
    complaints = int(issue.eq("Complaint").sum())
    inquiries = int(issue.eq("Inquiry").sum())
    part = _miss_parts(df)
    missed = int(part["missed"].sum())
    never = int(part["source"].sum()) + int(part["keyword"].sum())
    source, keyword = int(part["source"].sum()), int(part["keyword"].sum())
    analyst, platform = int(part["analyst"].sum()), int(part["platform"].sum())
    not_a_miss = complaints - missed
    pct = lambda n, d: f"{n / max(d, 1) * 100:.0f}%"

    chain_emails = f"{total} emails"
    chain_complaints = f"{complaints} complaints"
    chain_misses = f"{missed} misses"

    # 1 -- what came in, and what it was about.
    # `miss_by_customer()` rather than a fresh count: it is the frame the Customers
    # impacted table is already drawn from, so the panel and that table cannot disagree
    # about how many emails named an account.
    exposure = miss_by_customer(df) if "Customer" in df.columns else pd.DataFrame()
    exposure = exposure.sort_values("Emails", ascending=False) if not exposure.empty else exposure
    top_accounts = exposure.head(5) if not exposure.empty else pd.DataFrame()
    accounts_n = len(exposure)
    top_sum = int(top_accounts["Emails"].sum()) if not top_accounts.empty else 0
    biggest_name = str(top_accounts["Customer"].iloc[0]) if not top_accounts.empty else ""
    biggest_mail = int(top_accounts["Emails"].iloc[0]) if not top_accounts.empty else 0
    second_mail = int(top_accounts["Emails"].iloc[1]) if len(top_accounts) > 1 else 0
    reasons, reason_tail = _named_tail(reason_category(df).value_counts(), top=5,
                                       noun="category", nouns="categories")
    first = pd.to_datetime(df.get("Email/JIRA Date"), dayfirst=True, errors="coerce").min()
    since = f"emails since {first:%b %Y}" if pd.notna(first) else "emails in this view"
    cards = [{
        "key": "emails", "eyebrow": "Customer emails", "accent": ROOT_COLOURS["Product"],
        "question": "Who writes in, and what about?",
        "chain": [(chain_emails, True)],
        "hero": f"{total}", "base": since,
        "finding": (f"{esc(biggest_name)} sends {pct(biggest_mail, total)} of everything we receive"
                    + (f", and {biggest_mail / max(second_mail, 1):.1f} times the next account" if second_mail else "")
                    + f". Five of {accounts_n} accounts carry {pct(top_sum, total)} of the book."
                    if biggest_name else "No customer is recorded on these emails."),
        "rows_head": f"Who writes in — top five of {accounts_n} accounts",
        "rows": [{"name": esc(str(r["Customer"])), "value": int(r["Emails"]),
                  "colour": POP_NEUTRAL, "gloss": ""} for _, r in top_accounts.iterrows()],
        "grid_head": "What they write about — their own words, folded",
        "grid": [(label, count) for label, count in reasons]
                + ([(reason_tail[0].capitalize(), reason_tail[1])] if reason_tail else []),
        "notes": [f"<strong>{complaints}</strong> of these asserted we failed. "
                  f"The other <strong>{inquiries}</strong> asked how something works."]
                 + ([f"The folded row holds {esc(reason_tail[2])}."] if reason_tail else []),
        "foot": "An email naming two accounts counts for both.",
    }]

    # 2 -- the complaints, split on whether anything reached the customer.
    cards.append({
        "key": "complaints", "eyebrow": "Complaints", "accent": ROOT_COLOURS["People"],
        "question": "What did the complaints turn out to be?",
        "chain": [(chain_emails, False), (chain_complaints, True)],
        "hero": f"{complaints}", "base": f"of {total} emails",
        "finding": f"{pct(missed, complaints)} of them are events we never got to the customer. "
                   "The rest were reported in time, and something about what we sent was wrong.",
        "stack": [(missed, ROOT_COLOURS["People"]), (not_a_miss, POP_MUTED)],
        "rows": [
            {"name": "We did not notify the customer", "value": missed, "colour": ROOT_COLOURS["People"],
             "gloss": "Events the customer raised that we never reported, or reported too late for them to act on"},
            {"name": "We notified them, and it was wrong", "value": not_a_miss, "colour": POP_MUTED,
             "gloss": "Wrong suppliers, wrong scope, a wrong severity call, sent twice, or hard to find on their portal"},
        ],
        "bars": False,
        "proof": (f"{missed} + {not_a_miss} = {complaints}", "every complaint is in one of the two"),
        "notes": [f"The other <strong>{inquiries}</strong> emails were questions, not complaints, "
                  "so none of them counts as a failure."],
        "foot": "A complaint is not automatically a miss.",
    })

    # 3 -- where the story stopped. The one panel that names an owner per row.
    plat_counts = labels_for(df[part["platform"]]).value_counts() if platform else pd.Series(dtype=int)
    plat_gloss = ", ".join(f"{esc(str(k).lower())} ({int(v)})" for k, v in plat_counts.items())
    recent = _recent_shape(df, part)
    severity = df.get("Severity", pd.Series(dtype=str)).reindex(df.index).fillna("").astype(str).str.strip()
    sev = severity[part["missed"]].value_counts()
    sev_line = ", ".join(f"{int(v)} {esc(str(k))}" for k, v in sev.items())
    cards.append({
        "key": "misses", "eyebrow": "Confirmed misses", "accent": ROOT_COLOURS["Product"],
        "question": "Where did the story stop?",
        "chain": [(chain_emails, False), (chain_complaints, False), (chain_misses, True)],
        "hero": f"{missed}", "base": f"of {complaints} complaints",
        "finding": f"{pct(never, missed)} of them never reached the portal at all. "
                   "Almost all of the rest reached a person and stopped at their desk.",
        "stack": [(never, ROOT_COLOURS["Product"]), (platform, ROOT_COLOURS["Product"]),
                  (analyst, ROOT_COLOURS["People"])],
        "legend": [("Product fixes it", ROOT_COLOURS["Product"]),
                   ("EventWatch Ops fixes it", ROOT_COLOURS["People"])],
        "rows": [
            {"name": "It never reached the portal", "value": never, "colour": ROOT_COLOURS["Product"],
             "gloss": f"No monitored source carried it ({source}), or a monitored source did and our "
                      f"search terms missed it ({keyword}). There was never anything to work on."},
            {"name": "It reached the portal and was lost there", "value": platform, "colour": ROOT_COLOURS["Product"],
             "gloss": (f"Behind it: {plat_gloss}." if plat_gloss else "No miss stopped here.")},
            {"name": "It reached an analyst and was not sent", "value": analyst, "colour": ROOT_COLOURS["People"],
             "gloss": "A person had the story on the portal, and it did not go out, or went out too "
                      "late for the customer to act on."},
        ],
        "bars": False,
        "proof": (f"{never} + {platform} + {analyst} = {missed}", "a story stops once, in one place"),
        "notes": ([recent] if recent else []),
        "foot": (f"Of the {missed}: {sev_line}." if sev_line else "Product owns the first two stages, Ops the third."),
    })

    # 4 -- reported in time, and wrong anyway.
    wrong = df[issue.eq("Complaint") & ~part["missed"]]
    wrong_rows, wrong_tail = _named_tail(labels_for(wrong).value_counts(), top=5) if not wrong.empty else ([], None)
    cards.append({
        "key": "notamiss", "eyebrow": "Complaints, not a miss", "accent": ROOT_COLOURS["Process"],
        "question": "We reported it. What was wrong with it?",
        "chain": [(chain_emails, False), (chain_complaints, False),
                  (f"{not_a_miss} reported, but wrong", True)],
        "hero": f"{not_a_miss}", "base": f"of {complaints} complaints",
        "finding": "The bulletin went out in time. What the customer raised was who or what was on "
                   "it, the call we made, or where it ended up afterwards.",
        "rows": [{"name": esc(name), "value": count, "colour": ROOT_COLOURS["Process"], "gloss": ""}
                 for name, count in wrong_rows]
                + ([{"name": wrong_tail[0].capitalize(), "value": wrong_tail[1],
                     "colour": POP_MUTED, "gloss": esc(wrong_tail[2])}] if wrong_tail else []),
        "proof": (" + ".join(str(c) for _, c in wrong_rows)
                  + (f" + {wrong_tail[1]}" if wrong_tail else "") + f" = {not_a_miss}",
                  "nothing is folded into an Other bucket") if wrong_rows else None,
        "notes": ["Every one of these reached the customer in time, so none of them counts "
                  "as a miss. The failure is in what was sent, not whether it was sent."],
        "foot": "Delivered in time, so none of these is a miss.",
    })

    # 5 -- the capture gap, which is the number Product sizes investment against.
    acct_never = _account_share(df, part["source"] | part["keyword"])
    cards.append({
        "key": "nevercaptured", "eyebrow": "Never captured by us", "accent": ROOT_COLOURS["Product"],
        "question": "Why did we never find these?",
        "chain": [(chain_complaints, False), (chain_misses, False),
                  (f"{never} never reached the portal", True)],
        "hero": f"{never}", "base": f"of {missed} misses<br>{pct(never, missed)}",
        "finding": "Two reasons, and no third. Nothing reached the portal, so no analyst and no "
                   "model ever had the chance to see these stories.",
        "rows": [
            {"name": "No monitored source carried it", "value": source, "colour": ROOT_COLOURS["Product"],
             "gloss": "The outlet is not in our vendor or monitoring network, or its feed never "
                      "arrived. Product buys the coverage."},
            {"name": "A monitored source carried it, our terms missed it", "value": keyword,
             "colour": ROOT_COLOURS["Product"],
             "gloss": "The article came through, worded in a way our keywords did not match. "
                      "Product widens the terms."},
        ],
        "proof": (f"{source} + {keyword} = {never}", "the two have the same symptom and different fixes"),
        "notes": ["<strong>One question splits these two rows:</strong> was the carrying outlet "
                  "monitored. Ask it before filing either, because nothing in the system looks "
                  "different from the outside."]
                 + ([acct_never] if acct_never else []),
        "foot": "Both rows are Product's to fix.",
    })

    # 6 -- the story reached a person and stopped.
    actions = _analyst_actions(df, part["analyst"])
    cards.append({
        "key": "overlooked", "eyebrow": "Seen, but overlooked", "accent": ROOT_COLOURS["People"],
        "question": "What did the analyst do with it?",
        "chain": [(chain_complaints, False), (chain_misses, False),
                  (f"{analyst} reached an analyst", True)],
        "hero": f"{analyst}", "base": f"of {missed} misses<br>{pct(analyst, missed)}",
        "finding": "Every one was a story we already had on the portal."
                   + (f" {pct(actions[0][1], analyst)} of them died on one decision: {actions[0][0].lower()}."
                      if actions else ""),
        "rows": [{"name": esc(name), "value": count, "colour": ROOT_COLOURS["People"], "gloss": gloss}
                 for name, count, gloss in actions],
        "proof": (" + ".join(str(c) for _, c, _ in actions) + f" = {analyst}",
                  "the tracker files the top row under more than one name; one failure, one row")
                 if actions else None,
        "bullets": ("What the team is working against", [
            "100+ events captured every day, by a team that has not grown",
            "150+ events can be waiting in the rework queue",
            "Nine steps run at once, from research through to publishing",
            "Better filtering means more events need a real look, not a quick no",
            "Peer review is the same people doing the first pass",
        ], "Operating context from EventWatch Ops. These five are not measured in the tracker."),
        "notes": [],
        "foot": f"All {analyst} are EventWatch Ops to fix.",
    })

    # 7 -- the one panel about movement rather than composition.
    rate, band = trend_windows(df)
    cards.append(_trend_card(rate, band, total, chain_emails))

    # 8 -- the account that dominates the page.
    cards.append(_account_card(df, part, exposure, total, chain_emails, never))
    return [c for c in cards if c]


def _recent_shape(df, part, window=3):
    """How the three stages split over the last `window` months, when that differs.

    The cumulative panel is the whole year, and reading it as "the picture" gets the
    priorities wrong -- the same trap `miss_recent_note()` exists for on the miss ring.
    Printed only when the frame spans more than twice the window, because two windows
    drawn over four months of data is a shape rather than a finding.
    """
    dates = pd.to_datetime(df.get("Email/JIRA Date"), dayfirst=True, errors="coerce")
    months = dates.dt.to_period("M")
    span = months.dropna().unique()
    if len(span) <= window * 2:
        return ""
    recent = months.isin(sorted(span)[-window:])
    n = int((recent & part["missed"]).sum())
    if n == 0:
        return ""
    a = int((recent & (part["source"] | part["keyword"])).sum())
    b = int((recent & part["platform"]).sum())
    c = int((recent & part["analyst"]).sum())
    return (f"<strong>Over the last {window} months</strong> the {plural(n, 'miss', 'misses')} "
            f"split <strong>{a} / {b} / {c}</strong> across the same three stages.")


def _account_share(df, mask):
    """Which account carries most of a masked subset, and how that subset splits for them.

    Named rather than generic because "Ford carries 19 of the 42" is the line a reader
    asks for next, and a panel that makes them open another tab to get it has sent them
    away from the question it just answered.
    """
    if "Customer" not in df.columns or not int(mask.sum()):
        return ""
    names = customer_names(df.loc[mask, "Customer"])
    if not names:
        return ""
    counts = {n: int(names_match(df.loc[mask, "Customer"], [n]).sum()) for n in names}
    top = max(counts, key=lambda n: counts[n])
    return (f"{esc(top)} carries <strong>{counts[top]}</strong> of the {int(mask.sum())}, "
            f"more than any other account.")


def _trend_card(rate, band, total, chain_emails, window=3, months=6):
    """The movement panel: the last `months` months with each month's own base beside it.

    The base is on every row because a rate without one invites a reader to lean on a
    month that will move: October at 78% is seven emails, and the three-month windows
    moved the day it opened. A move under the noise threshold is named as noise rather
    than dressed up as a trend, which is the rule `missed_verdict()` already applies.
    """
    if rate.empty:
        return None
    tail = rate.tail(months)
    recent_months = set(rate.tail(window)["Month"])
    emails = int(rate["Records"].sum())
    rows = []
    for _, r in tail.iterrows():
        n, d = int(r["Missed"]), int(r["Records"])
        live = r["Month"] in recent_months
        rows.append({"name": pd.Period(r["Month"], freq="M").strftime("%b"),
                     "value": f"{n / max(d, 1) * 100:.0f}%", "note": f"{n}/{d}",
                     "width": n / max(d, 1) * 100,
                     "colour": ROOT_COLOURS["Product"] if live else POP_MUTED})
    if band:
        move = band["recent"]["value"] - band["older"]["value"]
        hero = f"{band['recent']['value']:.0f}%"
        finding = (f"<strong>{'Not improving, and no worse.' if abs(move) < 5 else 'Moving.'}</strong> "
                   f"{band['recent']['missed']} of {band['recent']['emails']} emails, against "
                   f"{band['older']['missed']} of {band['older']['emails']} in the {window} months "
                   f"before. The rate moved by {abs(move):.1f} points.")
        chain = [(chain_emails, False),
                 (f"{band['recent']['emails']} in the last {window} months", False),
                 (f"{band['recent']['missed']} misses", True)]
        notes = [f"A move under 5 points is read here as noise, not as a trend. "
                 f"This one is <strong>{abs(move):.1f}</strong>."]
    else:
        hero, finding = "—", "Two full windows of months are needed before a comparison means anything."
        chain, notes = [(chain_emails, True)], []
    last = tail.iloc[-1]
    thin = (f"The latest month holds <strong>{plural(int(last['Records']), 'email', 'emails')}</strong> "
            "so far. A thin month moves a long way on one record, which is why the base "
            "sits beside every rate.")
    return {"key": "trend", "eyebrow": f"Last {window} months", "accent": ROOT_COLOURS["Process"],
            "question": "Are we getting better?", "chain": chain,
            "hero": hero,
            "base": (f"of {band['recent']['emails']} emails<br>in the last {window} months"
                     if band else f"of the last {window} months"),
            "finding": finding, "rows_head": "Miss rate by month, with the emails behind it",
            "rows": rows, "bars": True, "scale": 100,
            "notes": notes + [thin],
            "foot": "Pooled on counts, not an average of monthly rates."}


def _account_card(df, part, exposure, total, chain_emails, never):
    """The biggest account, cut by owner first because that is who has to act.

    The flat cause list this replaced mixed owners inside single rows, so colour could
    not carry the owner and "who do I take this to" had no answer on the panel that
    exists to raise the question.
    """
    if exposure.empty or "Customer" not in df.columns:
        return None
    name = str(exposure["Customer"].iloc[0])
    emails = int(exposure["Emails"].iloc[0])
    mine = names_match(df["Customer"], [name])
    mask = mine & part["missed"]
    hit = int(mask.sum())
    if not hit:
        return None
    root = df.get("Root Cause", pd.Series(dtype=str)).reindex(df.index).fillna("").astype(str).str.strip()
    rows, stack = [], []
    for owner, who in (("Product", "Product fixes it"), ("People", "EventWatch Ops fixes it"),
                       ("Process", "Process fixes it")):
        owned = mask & root.eq(owner)
        n = int(owned.sum())
        if not n:
            continue
        colour = ROOT_COLOURS[owner]
        stack.append((n, colour))
        rows.append({"group": True, "name": who, "value": n, "colour": colour})
        for label, count in labels_for(df[owned]).value_counts().items():
            rows.append({"name": esc(str(label)), "value": int(count), "colour": colour, "gloss": ""})
    clean = [f"{esc(c)} {int(m)} of {int(m)}" for c, m in
             zip(exposure["Customer"], exposure["Misses"])
             if int(m) == int(exposure.loc[exposure["Customer"] == c, "Emails"].iloc[0])
             and int(m) >= 3 and str(c) != name][:2]
    book = int(part["missed"].sum())
    notes = []
    if clean:
        notes.append("Accounts that run hotter on much smaller volume: "
                     + ", ".join(clean) + " were all misses.")
    share = int((mine & (part["source"] | part["keyword"])).sum())
    if share:
        notes.append(f"{esc(name)} carries <strong>{share}</strong> of the {never} that "
                     "never reached the portal.")
    return {"key": "account", "eyebrow": "One customer's share", "accent": ROOT_COLOURS["Product"],
            "question": f"Why is {esc(name)} so high?",
            "chain": [(chain_emails, False), (f"{emails} from {esc(name)}", False), (f"{hit} misses", True)],
            "hero": f"{emails}", "base": f"of {total} emails<br>{emails / max(total, 1) * 100:.0f}%",
            "finding": f"{esc(name)} sends {emails / max(total, 1) * 100:.0f}% of everything we receive, and "
                       f"<strong>{hit} of their {emails}</strong> were misses — "
                       f"{hit / max(emails, 1) * 100:.0f}% against "
                       f"{book / max(total, 1) * 100:.0f}% across the book. "
                       "Volume alone does not explain that gap.",
            "stack": stack, "rows": rows, "bars": True,
            "proof": (" + ".join(str(n) for n, _ in stack) + f" = {hit}", "every miss has exactly one owner"),
            "notes": notes,
            "foot": "Accounts are split on the slash, so a merged email counts for both."}
