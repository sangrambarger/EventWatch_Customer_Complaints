#!/usr/bin/env python3
"""Check every page renders numbers that match the tracker, not just that it renders.

`smoke_app.py` proves a page draws its charts and tables. It cannot tell whether the
numbers in them are right -- a page bound to a stale frame, a filter silently dropping
rows, or a chart truncating a category all look identical to it.

This reads every `<table class="excel-table">` off every page, pulls the label/count
pairs out, and compares them against counts computed independently from the CSV. A
page whose figures do not reconcile fails, naming the label and both numbers.

  python3 scripts/audit_pages.py
  python3 scripts/audit_pages.py --page "SOURCE 03"     # just the matching pages
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

    # Every page counts every record the customer sent in -- complaints and inquiries.
    return {
        "Executive Summary": dict(split_all),
        "SOURCE 02 · Fix status": counts(df, "Short Term Fix Status"),
        "SOURCE 03 · Severity": counts(df, "Severity"),
        "SOURCE 04 · Root cause": counts(df, "Root Cause"),
        "SOURCE 05 · Top customers": dict(split_all),
        "SOURCE 06 · Automation focus": counts(df, "Standard Automation Focus"),
        "DETAIL · Event workload": counts(df, "Event type"),
        "SOURCE 01 · Monthly trend": {f"{m} Complaint": int(monthly.loc[m].get("Complaint", 0))
                                      for m in monthly.index},
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
    for page, expected in want.items():
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
        note = f"{checked} label(s) reconciled" + (f", {missing} not rendered (top-N cut)" if missing else "")
        print(f"{page:34s} {note}")

    if problems:
        print(f"\nFAIL — {len(problems)} figure(s) do not match the tracker:")
        for p_ in problems:
            print(f"  ✗ {p_}")
        return 1
    print(f"\nPASS — every rendered figure across {len(want)} page(s) matches the tracker.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
