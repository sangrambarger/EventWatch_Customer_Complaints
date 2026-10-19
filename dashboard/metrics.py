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
# One anatomy on all eight, cut to the bone on the owner's call: the chain that says
# where the figure sits in the funnel, the question, the figure with its base, ONE
# short sentence, a rule, a row of stat cards, a rule, one footer line. The panels this
# replaced carried a paragraph of gloss under every row and a stack of note boxes under
# that; the reader's complaint was the right one -- the number was stranded at the right
# edge of a bullet while the words did the talking. A stat card puts the number first
# and its own label underneath it, which is the only arrangement where the figure is
# what you read.
#
# Colour carries one thing on these panels and nothing else: who fixes it. Product is
# `--blue`, EventWatch Ops `--red`, a delivered bulletin that was wrong `--amber`, and
# a row that belongs to nobody takes `--muted`. Nothing is shaded by its own size --
# fading a card by its value spends the only free channel restating the number printed
# on it. Every card carries its name and count, so nothing rests on colour alone.
#
# `proof` is the visible `N + M = T` line, and it is the whole reason a panel prints
# one: the panels are only in the DOM once a reader clicks, so the scrape that
# reconciles every rendered figure never sees them. `audit_pages.card_detail_problems()`
# checks the equation against the cards of every block marked `partition`, which is why
# a block that is context rather than a split (card 8's second row) carries
# `partition=False` -- checking the equation against those would compare an owner split
# with a list of other accounts and call a correct panel wrong.
# ---------------------------------------------------------------------------------

POP_MUTED = "#515a68"
POP_NEUTRAL = "#b6beca"


def _stat(value, label, note="", colour=POP_MUTED):
    """One stat card: the number, two to four words naming it, a tiny qualifier."""
    return {"value": str(value), "label": label, "note": note, "colour": colour}


def _block(items, cols=None, partition=False):
    """A row of stat cards laid out on a `cols`-wide grid.

    The grid is fixed-column rather than flexed so a trailing short row keeps the card
    width of the row above it -- five cards over three columns reads as 3 + 2 of equal
    width, where a flex row would stretch the last two to half the panel each and make
    the small numbers look like the big ones.
    """
    items = [i for i in items if i]
    return {"cols": cols or min(len(items), 3), "items": items, "partition": partition}


def _equation(items, total):
    """The visible arithmetic under a partition block."""
    return " + ".join(str(i["value"]) for i in items) + f" = {total}"


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


# A group whose note is `NAME_THEM` prints the records' own defects instead of a
# category line. "A confirmed software bug" appears on two panels -- Harman's impact
# requests that never went to four Tier 2 sites, and Hitachi's Disruption Agent
# returning only Tier 1 suppliers -- and an ELT reading "a confirmed software bug"
# twice learns nothing it can act on. The two are different defects with different
# outcomes: one stopped delivery, the other followed a bulletin that landed.
#
# **It is set on the bug groups and nowhere else, deliberately.** It reads the record's
# own `Event/Bulletin Title`, which on a Platform Bug row names what the platform did
# and on most other rows names the EVENT -- applied to the clustering group it would
# print "Fire at the Isselguss GmbH Facility" as the explanation of a defect, which is
# worse than the generic line it replaced. Check what the titles actually say before
# putting this on another group.
NAME_THEM = object()


def defect_name(title):
    """The defect a record's own title names, stripped of event and customer.

    The house title convention is `<event> - <what went wrong> (<Customer>)`, so the
    customer is dropped and the clause after the dash is the defect. Where there is no
    dash the title leads with the defect and trails with the event it was found on, so
    the first `for` ends it. `shorten()` catches anything neither rule fits.
    """
    text = re.sub(r"\s*\([^()]*\)\s*$", "", str(title)).strip()
    for dash in ("\u2013", "\u2014", " - "):
        if dash in text:
            tail = text.split(dash, 1)[1].strip()
            if len(tail) > 12:
                return shorten(tail, 58)
    head = text.split(" for ", 1)[0].strip()
    return shorten(head if len(head) > 12 else text, 58)


# What a People-rooted miss says the analyst actually did, and what was wrong with a
# bulletin that did go out in time. Both are keyed on tracker sub-types with a
# fall-through, so a value added tomorrow appears under its own name rather than
# vanishing into a residue row -- the same rule `miss_bucket_series()` follows for the
# miss buckets. The labels are two to four words because they sit under a 28px number
# on a card a third of the panel wide; the sentence that used to explain each one is
# gone on the owner's call.
ANALYST_ACTIONS = (
    ("They judged it not impactful", MISS_BUCKETS[2][1], "Closed at review, so nothing went out"),
    ("They notified it late", ("Published Late", "Captured Late", "Prioritization"),
     "Published, but not in time to act on"),
    ("They tagged the wrong industry", ("Tagging", "Industry selection"),
     "It stayed off this customer's portal"),
    ("They missed a supplier", ("Supplier Selection Miss", "Mapping"),
     "On file, never selected, so no WarRoom"),
)

WRONG_GROUPS = (
    ("The supplier list was wrong", ("Supplier Selection Miss", "Mapping", "Mapping / Routing Defect"),
     "It went out naming the wrong suppliers"),
    ("They could not see it", ("Visibility", "Industry selection", "Tagging"),
     "Published, and not on their portal"),
    ("We called the event wrong", ("Review", "Relevancy", "Model Classification Defect"),
     "The scope or the impact was wrong"),
    ("Sent twice, or merged wrong", ("Duplication", "Strategy", "Clustering / Duplication Defect"),
     "One event, two bulletins"),
    ("No WarRoom was raised", ("WarRoom Creation",), "The bulletin went out on its own"),
    ("A confirmed software bug", ("Platform Bug", "Alerting Gap"), NAME_THEM),
)

# The one short name for a cause, in the words the stat cards use. A popup that names
# a cause names it from here -- card 8's owner cards read "no monitored source 12 ·
# keywords missed it 7" rather than the 46-character plain label, and rather than the
# "4 failures · biggest 12" they read first, which told a reader nothing they could act
# on. Keyed on the sub-type, with the owner-aware overrides `OWNED_SUBTYPE` already
# makes elsewhere: `Review` under Product is the model deciding and under People is a
# person deciding, which is the whole reason `MISS_BUCKETS` splits it in two.
LOST_GROUPS = (
    ("The model judged it not impactful", ("Model Classification Defect", "Review", "Relevancy"),
     "No person was asked to look again"),
    ("It never surfaced to an analyst", ("Alerting Gap", "Visibility"),
     "Captured, and never put in front of anyone"),
    ("Grouped under the wrong story", ("Clustering / Duplication Defect",),
     "Filed with a cluster nobody worked"),
    ("A confirmed software bug", ("Platform Bug",), NAME_THEM),
)

SHORT_CAUSE = {
    "Source Coverage": "no monitored source",
    "Keyword Update": "keywords missed it",
    "Model Classification Defect": "the model judged it not impactful",
    "Relevancy": "the model judged it not relevant",
    "Alerting Gap": "it never surfaced to an analyst",
    "Platform Bug": "a confirmed software bug",
    "Clustering / Duplication Defect": "grouped under the wrong story",
    "Visibility": "published, not visible",
    "Mapping / Routing Defect": "sent to the wrong place",
    "Review": "an analyst judged it not impactful",
    "Analyst Review Miss": "an analyst judged it not impactful",
    "Published Late": "notified late",
    "Captured Late": "notified late",
    "Prioritization": "notified late",
    "Tagging": "wrong industry tag",
    "Industry selection": "wrong industry tag",
    "Supplier Selection Miss": "a supplier was missed",
    "Mapping": "supplier not on file",
    "WarRoom Creation": "no WarRoom raised",
    "Duplication": "sent twice",
    "Process Clarification": "we clarified the rule",
    "Strategy": "how we group events",
    "Deliberate Rule": "the rule applied",
}
SHORT_OWNED = {
    ("Product", "Review"): "the model judged it not impactful",
    ("People", "Mapping"): "a supplier was missed",
    ("Process", "Mapping"): "they asked about mapping",
}


def short_cause(root, subtype):
    """The short name for one cause, owner-aware, falling back to the plain label."""
    key = (str(root).strip(), str(subtype).strip())
    if key in SHORT_OWNED:
        return SHORT_OWNED[key]
    return SHORT_CAUSE.get(key[1]) or failure_label(key[0], key[1]).lower()


def named_causes(df, mask, top=2):
    """The causes under `mask`, biggest first, as "name N · name N · and K more"."""
    root = df.get("Root Cause", pd.Series(dtype=str)).reindex(df.index).fillna("").astype(str)
    sub = df.get("Sub-type", pd.Series(dtype=str)).reindex(df.index).fillna("").astype(str)
    counts = {}
    for r, t in zip(root[mask], sub[mask]):
        name = short_cause(r, t)
        counts[name] = counts.get(name, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    shown = ranked[:top]
    line = " · ".join(f"{esc(n)} {v}" for n, v in shown)
    rest = sum(v for _, v in ranked[top:])
    return line + (f" · and {rest} more" if rest else "")


def _grouped(df, mask, groups, colour, tail_colour=POP_MUTED):
    """Stat cards for `mask`, folded onto `groups` in order, with a named fall-through.

    Groups apply in order and each claims only what the ones before it did not, so the
    cards always sum to the masked count however the taxonomy grows. A sub-type outside
    every group keeps its own plain label and its own card rather than landing in an
    `Other` bucket, which is how a mis-filed row stays mis-filed.
    """
    sub = df.get("Sub-type", pd.Series(dtype=str)).reindex(df.index).fillna("").astype(str).str.strip()
    cards, claimed = [], pd.Series(False, index=df.index)
    for name, subs, note in groups:
        hit = mask & sub.isin(subs) & ~claimed
        if int(hit.sum()):
            shown = note
            if note is NAME_THEM:
                names = [defect_name(t) for t in df.loc[hit, "Event/Bulletin Title"]]
                shown = (esc(" · ".join(names[:2])) if len(names) <= 2
                         else esc(f"{names[0]} · and {len(names) - 1} more"))
            cards.append((int(hit.sum()), _stat(int(hit.sum()), name, shown, colour)))
        claimed = claimed | hit
    rest = mask & ~claimed
    if int(rest.sum()):
        for label, count in labels_for(df[rest]).value_counts().items():
            cards.append((int(count), _stat(int(count), esc(shorten(str(label), 34)), "", tail_colour)))
    return [c for _, c in sorted(cards, key=lambda c: -c[0])]


def card_details(df):
    """One payload per Executive Summary card, in card order.

    A payload is data, not markup: `components.detail_panel()` draws it. Keeping the
    two apart is the same split the rest of this package keeps -- a panel can be
    restyled without touching a total, and a total cannot be changed by a styling edit.
    """
    total = len(df)
    if total == 0:
        return []
    issue = df.get("Issue Type", pd.Series(dtype=str)).reindex(df.index).astype(str).str.strip()
    complaints = int(issue.eq("Complaint").sum())
    inquiries = int(issue.eq("Inquiry").sum())
    part = _miss_parts(df)
    missed = int(part["missed"].sum())
    source, keyword = int(part["source"].sum()), int(part["keyword"].sum())
    never = source + keyword
    analyst, platform = int(part["analyst"].sum()), int(part["platform"].sum())
    not_a_miss = complaints - missed
    pct = lambda n, d: f"{n / max(d, 1) * 100:.0f}%"
    blue, red, amber = ROOT_COLOURS["Product"], ROOT_COLOURS["People"], ROOT_COLOURS["Process"]

    chain_emails = f"{total} emails"
    chain_complaints = f"{complaints} complaints"
    chain_misses = f"{missed} misses"
    cards = []

    # 1 -- what came in. `miss_by_customer()` rather than a fresh count: it is the frame
    # the Customers impacted table is drawn from, so the panel and that table cannot
    # disagree about how many emails named an account.
    exposure = miss_by_customer(df) if "Customer" in df.columns else pd.DataFrame()
    exposure = exposure.sort_values("Emails", ascending=False) if not exposure.empty else exposure
    accounts_n = len(exposure)
    top = exposure.head(4)
    top5 = int(exposure.head(5)["Emails"].sum()) if not exposure.empty else 0
    first = pd.to_datetime(df.get("Email/JIRA Date"), dayfirst=True, errors="coerce").min()
    if not top.empty:
        biggest, biggest_n = str(top["Customer"].iloc[0]), int(top["Emails"].iloc[0])
        second_n = int(top["Emails"].iloc[1]) if len(top) > 1 else 0
        lead = (f"{esc(biggest)} sends {pct(biggest_n, total)} of everything"
                + (f", {biggest_n / max(second_n, 1):.1f} times the next account." if second_n else "."))
        items = [_stat(int(r["Emails"]), esc(str(r["Customer"])),
                       f"{pct(int(r['Emails']), total)} of all email" if i == 0 else pct(int(r["Emails"]), total),
                       blue if i == 0 else POP_MUTED) for i, (_, r) in enumerate(top.iterrows())]
        # These four do not add up to the hero and never can: an email naming two
        # accounts is counted for both, so the account column sums past the tracker.
        # The Customers impacted table carries the same overshoot and explains it in
        # its own caption; a panel that leaves a reader to discover it by adding four
        # numbers is the arithmetic complaint that table was fixed for.
        foot_left = (f"Top {len(items)} of {accounts_n} accounts. The top "
                     f"{min(5, accounts_n)} carry {pct(top5, total)} of everything.")
        shared = int(df["Customer"].astype(str).str.contains("/").sum())
        foot_right = (f"{plural(shared, 'email', 'emails')} name two accounts, so these "
                      f"add to {int(exposure['Emails'].sum())}, not {total}."
                      if shared else "One account per email.")
    else:
        lead, items, foot_left = "No customer is recorded on these emails.", [], ""
        foot_right = "An email naming two accounts counts for both."
    cards.append({
        "key": "emails", "eyebrow": "Customer emails", "accent": blue,
        "question": "Who writes in?",
        "chain": [(f"{total} customer emails", True)],
        "hero": f"{total}",
        "base": (f"emails since<br>{first:%b %Y}" if pd.notna(first) else "emails in this view"),
        "lead": lead,
        "blocks": [_block(items, cols=4)],
        "proof": None, "foot_left": foot_left, "foot_right": foot_right,
    })

    # 2 -- the complaints, split on whether anything reached the customer.
    split = [_stat(missed, "We did not notify them", "Never sent, or sent too late to act on", red),
             _stat(not_a_miss, "We notified them, and it was wrong",
                   "Scope, impact, visibility or follow-up", POP_MUTED)]
    cards.append({
        "key": "complaints", "eyebrow": "Complaints", "accent": red,
        "question": "What did the complaints turn out to be?",
        "chain": [(chain_emails, False), (chain_complaints, True)],
        "hero": f"{complaints}", "base": f"of {total} emails",
        "lead": f"{pct(missed, complaints)} were events we did not report, or did not report in time.",
        "stack": [(missed, red), (not_a_miss, POP_MUTED)],
        "blocks": [_block(split, cols=2, partition=True)],
        "proof": _equation(split, complaints),
        "foot_left": _equation(split, complaints),
        "foot_right": f"{inquiries} more emails were questions, not complaints.",
    })

    # 3 -- where the story stopped. The one panel that names an owner per card.
    stages = [_stat(never, "Never reached us at all",
                    f"no monitored source {source} · keywords missed it {keyword}", blue),
              _stat(platform, "Lost before an analyst", named_causes(df, part["platform"]), blue),
              _stat(analyst, "An analyst saw it", named_causes(df, part["analyst"]), red)]
    recent = _recent_shape(df, part)
    cards.append({
        "key": "misses", "eyebrow": "Confirmed misses", "accent": blue,
        "question": "Where did the story stop?",
        "chain": [(chain_emails, False), (chain_complaints, False), (chain_misses, True)],
        "hero": f"{missed}", "base": f"of {complaints} complaints",
        "lead": f"{pct(never, missed)} never reached us at all. Most of the rest stopped with an analyst.",
        "stack": [(never, blue), (platform, blue), (analyst, red)],
        # `Routed To`'s own two values. "Product fixes it" was the first wording and the
        # owner's question -- what does that mean -- is the right one: it names no team a
        # reader could take the number to.
        "legend": [("Product & Platform investigate these", blue),
                   ("EventWatch Ops investigate these", red)],
        "blocks": [_block(stages, cols=3, partition=True)],
        "proof": _equation(stages, missed),
        "foot_left": _equation(stages, missed),
        "foot_right": recent or "Product owns the first two steps, EventWatch Ops the third.",
    })

    # 4 -- reported in time, and wrong anyway.
    wrong = _grouped(df, issue.eq("Complaint") & ~part["missed"], WRONG_GROUPS, amber)
    cards.append({
        "key": "notamiss", "eyebrow": "Complaints, not a miss", "accent": amber,
        "question": "We reported it. What was wrong?",
        "chain": [(chain_emails, False), (chain_complaints, False),
                  (f"{not_a_miss} reported, but wrong", True)],
        "hero": f"{not_a_miss}", "base": f"of {complaints} complaints",
        "lead": "Delivered on time. The content, or its reach, was wrong.",
        "blocks": [_block(wrong, cols=3, partition=True)],
        "proof": _equation(wrong, not_a_miss) if wrong else None,
        "foot_left": _equation(wrong, not_a_miss) if wrong else "",
        "foot_right": "None of these is a miss.",
    })

    # 5 -- the capture gap, which is the number Product sizes investment against.
    gap = [_stat(source, "No monitored source carried it", "Product buys the coverage", blue),
           _stat(keyword, "Our keywords missed it", "Product widens the terms", blue)]
    cards.append({
        "key": "nevercaptured", "eyebrow": "Never reached us", "accent": blue,
        "question": "Why did we never find these?",
        "chain": [(chain_complaints, False), (chain_misses, False),
                  (f"{never} never reached us", True)],
        "hero": f"{never}", "base": f"of {missed} misses<br>{pct(never, missed)}",
        "lead": "Nothing reached us, so no analyst and no model ever saw them.",
        "blocks": [_block(gap, cols=2, partition=True)],
        "proof": _equation(gap, never),
        "foot_left": _equation(gap, never),
        "foot_right": "One test splits them: was the outlet monitored.",
    })

    # 6 -- the story reached a person and stopped.
    actions = _grouped(df, part["analyst"], ANALYST_ACTIONS, red)
    cards.append({
        "key": "overlooked", "eyebrow": "An analyst saw it", "accent": red,
        "question": "An analyst had it. What did they do?",
        "chain": [(chain_complaints, False), (chain_misses, False),
                  (f"{analyst} an analyst had", True)],
        "hero": f"{analyst}", "base": f"of {missed} misses<br>{pct(analyst, missed)}",
        "lead": (f"{pct(int(actions[0]['value']), analyst)} stopped on one call: "
                 f"{actions[0]['label'].lower()}." if actions else "No miss stopped with an analyst."),
        "blocks": [_block(actions, cols=2, partition=True)],
        "proof": _equation(actions, analyst) if actions else None,
        "foot_left": _equation(actions, analyst) if actions else "",
        "foot_right": f"All {analyst} go to EventWatch Ops.",
    })

    # 7 -- the middle stage of the miss ladder, and the reason this card exists at all.
    # The KPI row showed 42 never captured and 35 seen by an analyst against a headline
    # of 86, so a reader adding the two got 77 and had nine misses with nowhere to be.
    # The three stages are a partition by construction; the row now prints all three.
    lost = _grouped(df, part["platform"], LOST_GROUPS, blue)
    cards.append({
        "key": "lostinside", "eyebrow": "Lost before an analyst", "accent": blue,
        "question": "We had the story. What happened to it?",
        "chain": [(chain_complaints, False), (chain_misses, False),
                  (f"{platform} lost before an analyst", True)],
        "hero": f"{platform}", "base": f"of {missed} misses<br>{pct(platform, missed)}",
        "lead": "It reached our system and no person ever got to see it.",
        "blocks": [_block(lost, cols=2, partition=True)],
        "proof": _equation(lost, platform) if lost else None,
        "foot_left": _equation(lost, platform) if lost else "",
        "foot_right": f"All {platform} go to Product & Platform.",
    })

    # 8 -- the one panel about movement rather than composition.
    rate, band = trend_windows(df)
    cards.append(_trend_card(rate, band, chain_emails))
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
    span = sorted(months.dropna().unique())
    if len(span) <= window * 2:
        return ""
    live = span[-window:]
    recent = months.isin(live)
    n = int((recent & part["missed"]).sum())
    if n == 0:
        return ""
    a = int((recent & (part["source"] | part["keyword"])).sum())
    b = int((recent & part["platform"]).sum())
    c = int((recent & part["analyst"]).sum())
    return (f"In {live[0].strftime('%b')} to {live[-1].strftime('%b')} the same three "
            f"read {a} / {b} / {c}.")


def _trend_card(rate, band, chain_emails, window=3, months=6):
    """The movement panel: the last `months` months with each month's own base beside it.

    The base is on every row because a rate without one invites a reader to lean on a
    month that will move: a month of seven emails swings a long way on one record, and
    the three-month windows moved the day October opened. A move under the noise
    threshold is named as noise rather than dressed up as a trend, which is the rule
    `missed_verdict()` already applies.
    """
    if rate.empty:
        return None
    tail = rate.tail(months)
    live = set(rate.tail(window)["Month"])
    bars = []
    for _, r in tail.iterrows():
        n, d = int(r["Missed"]), int(r["Records"])
        bars.append({"name": pd.Period(r["Month"], freq="M").strftime("%b"),
                     "value": f"{n / max(d, 1) * 100:.0f}%", "note": f"{n}/{d}",
                     "width": n / max(d, 1) * 100,
                     "colour": ROOT_COLOURS["Product"] if r["Month"] in live else POP_MUTED})
    span = lambda w: f"{pd.Period(w['months'][0], freq='M').strftime('%b')} to " \
                     f"{pd.Period(w['months'][-1], freq='M').strftime('%b')}"
    if band:
        move = band["recent"]["value"] - band["older"]["value"]
        items = [_stat(f"{band['recent']['value']:.0f}%", span(band["recent"]),
                       f"{band['recent']['missed']} of {band['recent']['emails']}", ROOT_COLOURS["Product"]),
                 _stat(f"{band['older']['value']:.0f}%", span(band["older"]),
                       f"{band['older']['missed']} of {band['older']['emails']}", POP_MUTED),
                 _stat(f"{abs(move):.1f}", "Points moved",
                       "Under 5 reads as noise" if abs(move) < 5 else "A real move", POP_MUTED)]
        hero = f"{band['recent']['value']:.0f}%"
        lead = (f"{'No change.' if abs(move) < 5 else 'Moving.'} "
                f"{band['recent']['missed']} of {band['recent']['emails']}, against "
                f"{band['older']['missed']} of {band['older']['emails']} before.")
        chain = [(chain_emails, False),
                 (f"{band['recent']['emails']} in {span(band['recent'])}", False),
                 (f"{band['recent']['missed']} misses", True)]
        base = f"of {band['recent']['emails']} emails<br>in {span(band['recent'])}"
    else:
        items, hero, base = [], "—", f"of the last {window} months"
        lead = "Two full windows of months are needed before a comparison means anything."
        chain = [(chain_emails, True)]
    last = tail.iloc[-1]
    return {"key": "trend", "eyebrow": "Last three months", "accent": ROOT_COLOURS["Process"],
            "question": "Are we getting better?", "chain": chain,
            "hero": hero, "base": base, "lead": lead,
            "blocks": [_block(items, cols=3)] if items else [],
            "bars": bars, "proof": None,
            "foot_left": "Pooled on counts, never averaged.",
            "foot_right": (f"{pd.Period(last['Month'], freq='M').strftime('%b')} holds "
                           f"{plural(int(last['Records']), 'email', 'emails')} so far.")}
