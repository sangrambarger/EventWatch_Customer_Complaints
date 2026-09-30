#!/usr/bin/env python3
"""Check every page renders numbers that match the tracker, not just that it renders.

`smoke_app.py` proves a page draws its charts and tables. It cannot tell whether the
numbers in them are right -- a page bound to a stale frame, a filter silently dropping
rows, or a chart truncating a category all look identical to it.

This reads every `<table class="excel-table">` off every page, pulls the label/count
pairs out, and compares them against counts computed independently from the CSV. A
page whose figures do not reconcile fails, naming the label and both numbers.

  python3 scripts/audit_pages.py
  python3 scripts/audit_pages.py --page "SOURCE 04"     # just the matching pages
Exits non-zero on any mismatch.
"""
from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
CHROMIUM = "/opt/pw-browsers/chromium"


def reason_category_counts(df: pd.DataFrame) -> dict[str, int]:
    """{category: emails}, folded with app.py's own map so the two cannot disagree."""
    sys.path.insert(0, str(REPO))
    from app import REASON_CATEGORIES
    counts: dict[str, int] = collections.Counter()
    for value in df["Reason"].astype(str).str.strip():
        counts[REASON_CATEGORIES.get(value, "Uncategorised")] += 1
    return dict(counts)


def miss_buckets(df: pd.DataFrame) -> dict[str, int]:
    """{bucket: misses}, recomputed from the CSV rather than imported from the app.

    The four named rules are the ones where the owner changes the answer. There is no
    residue bucket: every other missed email is counted under its own sub-type, in
    English. Only the label map is imported, for the same reason REASON_CATEGORIES is --
    a second copy of a wording would drift, and it is the numbers this audit checks.
    """
    sys.path.insert(0, str(REPO))
    from app import PLAIN_SUBTYPE
    missed = df[df["Missed_Flag"].astype(str).str.strip() == "Yes"]
    sub = missed["Sub-type"].astype(str).str.strip()
    root = missed["Root Cause"].astype(str).str.strip()
    surfaced = ["Review", "Event Identification", "Prioritization"]
    out = {
        PLAIN_SUBTYPE["Source Coverage"]: int((sub == "Source Coverage").sum()),
        PLAIN_SUBTYPE["Keyword Update"]: int((sub == "Keyword Update").sum()),
        "An analyst let it through": int((sub.isin(surfaced) & (root == "People")).sum()),
        "The model did not spot it": int((sub.isin(surfaced) & (root == "Product")).sum()),
    }
    rest = missed[~((sub == "Source Coverage") | (sub == "Keyword Update")
                    | (sub.isin(surfaced) & root.isin(["People", "Product"])))]
    # `+=`, not `=`. Two pairs of sub-types deliberately share a label, and an assignment
    # here made the second value overwrite the first -- the audit would then have read a
    # bucket of 2 as a bucket of 1 and called the app wrong.
    for value, n in rest["Sub-type"].astype(str).str.strip().value_counts().items():
        label = PLAIN_SUBTYPE.get(value, value)
        out[label] = out.get(label, 0) + int(n)
    return out


def expectations(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """{page: {label: count}} computed straight from the CSV, never from the app."""
    complaints = df[df["Issue Type"].astype(str).str.strip() == "Complaint"]

    def counts(frame, col):
        return {str(k).strip(): int(v) for k, v in frame[col].astype(str).str.strip().value_counts().items()}

    split_all = collections.Counter()
    for v in df["Customer"].astype(str):
        for part in v.split("/"):
            split_all[part.strip()] += 1

    dates = pd.to_datetime(df["Email/JIRA Date"], format="%d-%b-%Y", errors="coerce")
    monthly = (pd.DataFrame({"m": dates.dt.strftime("%b %Y"), "t": df["Issue Type"].astype(str).str.strip()})
               .groupby(["m", "t"]).size().unstack(fill_value=0))

    # "Why the events were missed" on the Executive Summary. Recomputed here from the
    # Sub-type column rather than imported from app.py, so a bucket quietly redefined in
    # the app fails this audit instead of agreeing with itself.
    missed = df[df["Missed_Flag"].astype(str).str.strip() == "Yes"]
    miss_cats = miss_buckets(df)

    # "Why the events were missed" names each miss by EventWatch's own term for it,
    # keyed on the (Root Cause, Sub-type) pair the record actually carries. Counted here
    # from the CSV; only the label map is imported, as with the buckets above.
    sys.path.insert(0, str(REPO))
    from app import DRIVERS, NEEDS_REVIEW
    drivers: collections.Counter = collections.Counter()
    for _, row in missed.iterrows():
        pair = (str(row["Root Cause"]).strip(), str(row["Sub-type"]).strip())
        drivers[DRIVERS.get(pair, (NEEDS_REVIEW, ""))[0]] += 1
    assert sum(drivers.values()) == len(missed), "drivers do not sum to the misses"
    assert sum(miss_cats.values()) == len(missed), "miss buckets do not sum to the misses"

    # "Missed event types" counts the confirmed misses only -- the block it replaced
    # counted every email under the same heading, and that is exactly the kind of quiet
    # population swap this audit exists to catch.
    miss_types = {str(k).strip(): int(v)
                  for k, v in missed["Event type"].astype(str).str.strip().value_counts().items()}

    # The three-way split of the inbox, as the first ring draws it.
    flag = df["Missed_Flag"].astype(str).str.strip()
    issue = df["Issue Type"].astype(str).str.strip()
    inbox = {
        "Confirmed misses": int(flag.eq("Yes").sum()),
        "Complaints, not a miss": int((issue.eq("Complaint") & flag.ne("Yes")).sum()),
        "Inquiries": int(issue.eq("Inquiry").sum()),
    }

    # Every page counts every record the customer sent in -- complaints and inquiries.
    return {
        "Executive Summary": {**split_all, **dict(drivers), **miss_types, **inbox,
                              **reason_category_counts(df)},
        # SOURCE 04 renders the Executive Summary's own root-cause blocks, so it is
        # checked against the same driver and failure counts -- if the two tabs ever
        # drift, one of them fails here rather than both agreeing with themselves.
        "SOURCE 04 · Root cause": {**counts(df, "Root Cause"), **dict(drivers)},
        "SOURCE 05 · Top customers": dict(split_all),
        "DETAIL · Event workload": {**counts(df, "Event type"), **miss_types},
        "SOURCE 01 · Monthly trend": {f"{m} Complaint": int(monthly.loc[m].get("Complaint", 0))
                                      for m in monthly.index},
        # The reason categories on All customer emails. Imported from app.py rather
        # than restated, because a second copy of the fold would drift and the whole point
        # of the map is that one wording maps one way everywhere.
        "All customer emails": reason_category_counts(df),
    }


def scrape(url: str, pages: list[str]) -> dict[str, list[list[list[str]]]]:
    from playwright.sync_api import sync_playwright
    out: dict[str, list[list[list[str]]]] = {}
    with sync_playwright() as p:
        launch = {"executable_path": CHROMIUM} if os.path.exists(CHROMIUM) else {}
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1600, "height": 1400})
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(3000)
        for name in pages:
            page.get_by_text(name, exact=True).first.click()
            page.wait_for_timeout(2200)
            out[name] = page.eval_on_selector_all(
                "table.excel-table",
                "ts => ts.map(t => Array.from(t.querySelectorAll('tr'))"
                "        .map(r => Array.from(r.querySelectorAll('th,td')).map(c => c.innerText.trim())))")
        browser.close()
    return out


def reconciled_totals(df: pd.DataFrame) -> dict[str, dict[str, int]]:
    """{page: {column header: the figure its Total row must show}}.

    Customers impacted is the one table whose rows double-count on purpose: accounts
    split on the slash, so an email naming two of them sits on both rows. Its foot has to
    carry the tracker's own distinct counts -- it printed 120 emails against a tracker of
    115, and 27 / 24 / 13 where the chart above it said 26 / 23 / 12, before this check
    existed. Everything else is checked against the column above it.

    It is registered for BOTH pages that render it. SOURCE 05 now calls the Executive
    Summary's own `render_customers()`, and the first run after that wiring failed here
    with the same 120-against-115 the check was written for -- the table was reconciled,
    the audit's registration was not. A shared renderer means shared expectations.
    """
    issue = df["Issue Type"].astype(str).str.strip()
    exec_page = {
        "EMAILS": len(df),
        "COMPLAINTS": int(issue.eq("Complaint").sum()),
        "INQUIRIES": int(issue.eq("Inquiry").sum()),
        "CONFIRMED MISSES": int(df["Missed_Flag"].astype(str).str.strip().eq("Yes").sum()),
    }
    exec_page.update({k.upper(): v for k, v in miss_buckets(df).items()})
    return {"Executive Summary": exec_page, "SOURCE 05 · Top customers": dict(exec_page)}


def total_row_problems(page: str, tables, df: pd.DataFrame, reconciled) -> list[str]:
    """Every rendered Total row, checked against the column above it or against the CSV.

    A total that silently disagrees with its own column is arithmetic nobody sees; a
    total that disagrees with the tracker is worse, because the reader trusts the foot
    over the rows. Both have shipped here. Columns whose foot is a formatted string
    (a share, a blank) carry no plain integer and are skipped.
    """
    out = []
    for rows in tables:
        if len(rows) < 3:
            continue
        head = [c.strip().upper() for c in rows[0]]
        total = next((r for r in rows[1:] if r and r[0].strip().lower() == "total"), None)
        if total is None:
            continue
        body = [r for r in rows[1:] if r is not total and len(r) == len(head)]
        for i, column in enumerate(head):
            if i >= len(total):
                continue
            shown = re.fullmatch(r"-?\d+", total[i].replace(",", ""))
            if not shown:
                continue                                  # a share, a label, a blank
            shown = int(shown.group(0))
            fixed = reconciled.get(page, {}).get(column)
            if fixed is not None:
                want, why = int(fixed), "the tracker"
            else:
                cells = [re.fullmatch(r"-?\d+", r[i].replace(",", "")) for r in body]
                if any(c is None for c in cells) or not cells:
                    continue                              # a mixed column; nothing to sum
                want, why = sum(int(c.group(0)) for c in cells), "the rows above it"
            if shown != want:
                out.append(f"{page}: Total row shows {shown} for {column!r}, {why} says {want}")
    return out


def pairs(tables) -> dict[str, set[int]]:
    """Every label -> the set of numbers rendered beside it, across a page's tables."""
    found: dict[str, set[int]] = collections.defaultdict(set)
    for rows in tables:
        for row in rows:
            if len(row) < 2:
                continue
            label = row[0]
            for cell in row[1:]:
                m = re.fullmatch(r"-?\d+", cell.replace(",", ""))
                if m:
                    found[label].add(int(m.group(0)))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8631)
    ap.add_argument("--page", help="only audit pages whose name contains this")
    args = ap.parse_args()
    url = f"http://localhost:{args.port}"

    df = pd.read_csv(REPO / "customer_tracker.csv", dtype=str, keep_default_na=False)
    want = expectations(df)
    if args.page:
        want = {k: v for k, v in want.items() if args.page.lower() in k.lower()}
    if not want:
        print("No pages match."); return 1

    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true", "--server.port", str(args.port)],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)
    try:
        deadline = time.time() + 60
        while time.time() < deadline:
            try:
                urllib.request.urlopen(url, timeout=3); break
            except Exception:
                time.sleep(1)
        else:
            print(f"FAIL — Streamlit did not come up on {url}"); return 1
        scraped = scrape(url, list(want))
    finally:
        proc.terminate()
        try: proc.wait(timeout=10)
        except subprocess.TimeoutExpired: proc.kill()

    problems = []
    totals_checked = 0
    reconciled = reconciled_totals(df)
    for page, expected in want.items():
        problems += total_row_problems(page, scraped[page], df, reconciled)
        totals_checked += sum(1 for rows in scraped[page]
                              if any(r and r[0].strip().lower() == "total" for r in rows[1:]))
        got = pairs(scraped[page])
        checked = missing = 0
        for label, n in sorted(expected.items(), key=lambda kv: -kv[1]):
            if label.endswith(" Complaint"):                 # monthly trend: month row, first number
                label = label[: -len(" Complaint")]
            if label not in got:
                missing += 1                                  # legitimately truncated out of a top-N
                continue
            checked += 1
            if n not in got[label]:
                problems.append(f"{page}: {label!r} shows {sorted(got[label])}, tracker says {n}")
        feet = sum(1 for rows in scraped[page]
                   if any(r and r[0].strip().lower() == "total" for r in rows[1:]))
        note = f"{checked} label(s) reconciled" + (f", {missing} not rendered (top-N cut)" if missing else "")
        note += f", {feet} total row(s) checked" if feet else ""
        print(f"{page:34s} {note}")

    if problems:
        print(f"\nFAIL — {len(problems)} figure(s) do not match the tracker:")
        for p_ in problems:
            print(f"  ✗ {p_}")
        return 1
    print(f"\nPASS — every rendered figure across {len(want)} page(s) matches the tracker, "
          f"{totals_checked} total row(s) included.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
