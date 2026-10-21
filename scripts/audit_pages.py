#!/usr/bin/env python3
"""Check every page renders numbers that match the tracker, not just that it renders.

`smoke_app.py` proves a page draws its charts and tables. It cannot tell whether the
numbers in them are right -- a page bound to a stale frame, a filter silently dropping
rows, or a chart truncating a category all look identical to it.

This reads every `<table class="excel-table">` off every page, pulls the label/count
pairs out, and compares them against counts computed independently from the CSV. A
page whose figures do not reconcile fails, naming the label and both numbers.

  python3 scripts/audit_pages.py
  python3 scripts/audit_pages.py --page "Analysis"   # just the matching pages
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
    from dashboard.taxonomy import REASON_CATEGORIES
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
    from dashboard.taxonomy import PLAIN_SUBTYPE, failure_label
    missed = df[df["Missed_Flag"].astype(str).str.strip() == "Yes"]
    sub = missed["Sub-type"].astype(str).str.strip()
    root = missed["Root Cause"].astype(str).str.strip()
    # `Analyst Review Miss` joins the three the analyst/model rules already name: it is
    # the V1 taxonomy's word for the same failure, so leaving it out here would have the
    # audit recompute a bucket the app no longer draws that way and call the app wrong.
    surfaced = ["Review", "Model Classification Defect", "Analyst Review Miss"]
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
    #
    # Keyed on (owner, sub-type), not the sub-type alone: `Mapping` means a different
    # failure under each owner and carries a different label, so an owner-blind lookup
    # here would file a People/Mapping miss under the Product wording and disagree with
    # the app. No missed record carries that pair today, which is exactly why it would
    # have gone unnoticed until one did.
    for (owner, value), n in rest.groupby(
            [rest["Root Cause"].astype(str).str.strip(),
             rest["Sub-type"].astype(str).str.strip()]).size().items():
        label = failure_label(owner, value)
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
    from dashboard.taxonomy import DRIVERS, NEEDS_REVIEW
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
        # Analysis is the merge of what were Root cause and Top customer complaints, so
        # it is checked against BOTH sets: the root-cause and driver counts from the
        # first half, the per-account counts from the second. Both halves run the
        # Executive Summary's own renderers, so if the two tabs ever drift one of them
        # fails here rather than both agreeing with themselves.
        #
        # Root Cause values and account names cannot collide, so the merge is safe --
        # check that again if either vocabulary ever grows a shared word.
        "Analysis": {**counts(df, "Root Cause"), **dict(drivers), **split_all},
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

    It is registered for BOTH pages that render it. Analysis calls the Executive
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
    return {"Executive Summary": exec_page, "Analysis": dict(exec_page)}


def total_row_problems(page: str, tables, df: pd.DataFrame, reconciled) -> list[str]:
    """Every rendered Total row, checked against the column above it or against the CSV.

    A total that silently disagrees with its own column is arithmetic nobody sees; a
    total that disagrees with the tracker is worse, because the reader trusts the foot
    over the rows. Both have shipped here. Columns whose foot is a formatted string
    (a share, a blank) carry no plain integer and are skipped.

    The reconciled figures apply to the ONE table that double-counts, not to the page.
    They were applied page-wide, and the first run after Top customer complaints gained
    per-account tables failed with "Total row shows 44 for EMAILS, the tracker says 115"
    -- 44 is Ford's own total and perfectly correct. A table is the double-counting one
    only if it carries a miss-bucket column, which is the signature of Customers
    impacted and of nothing else.
    """
    buckets = {k.upper() for k in miss_buckets(df)}
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
            fixed = reconciled.get(page, {}).get(column) if buckets & set(head) else None
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


def card_detail_problems(df: pd.DataFrame) -> tuple[list[str], int]:
    """Every card popup's own arithmetic, checked without opening a browser.

    The panels are only in the DOM once a reader clicks, so the scrape above never
    sees them -- which would leave eight panels of figures outside the one gate that
    exists to say whether a number is right. Their payloads are plain data, so the
    check is a pure call: the stat cards a panel prints must match the equation it
    prints underneath, and that equation must be true.

    This is the whole reason a popup carries a visible `N + M = T` line. A panel whose
    parts do not add up to its own headline is the fault a reader spots first and
    trusts least, and it has shipped on this dashboard before -- the Customers impacted
    foot once read 120 against a tracker of 115.

    Only the blocks marked `partition` are compared against the equation. A block that
    is context rather than a split -- the account panel's second row, which carries that
    account's share of the capture gap and two other accounts entirely -- would
    otherwise be matched against an owner split and call a correct panel wrong.
    """
    sys.path.insert(0, str(REPO))
    from dashboard.metrics import card_details
    problems, checked = [], 0
    for card in card_details(df):
        if not card.get("proof"):
            continue
        equation = card["proof"]
        left, _, right = equation.partition("=")
        try:
            parts = [int(p.strip()) for p in left.split("+")]
            whole = int(right.strip())
        except ValueError:
            problems.append(f"popup {card['key']!r}: cannot read its own equation {equation!r}")
            continue
        checked += 1
        if sum(parts) != whole:
            problems.append(f"popup {card['key']!r}: {equation} does not add up")
        if card.get("foot_left") != equation:
            problems.append(f"popup {card['key']!r}: prints {card.get('foot_left')!r} under an "
                            f"equation of {equation!r}")
        shown = [int(s["value"]) for b in card.get("blocks", []) if b.get("partition")
                 for s in b["items"] if str(s["value"]).isdigit()]
        if sorted(shown, reverse=True) != sorted(parts, reverse=True):
            problems.append(f"popup {card['key']!r}: stat cards {sorted(shown, reverse=True)} do not "
                            f"match the equation {sorted(parts, reverse=True)}")
    return problems, checked


def month_panel_problems(df: pd.DataFrame) -> tuple[list[str], int]:
    """Every month dialog's own arithmetic, checked without opening a browser.

    A month panel is only in the DOM once a reader clicks a bar, so the scrape above
    never sees it -- the same hole `card_detail_problems()` was written to close for the
    eight card popups. The panel reuses `render_root_tier()` rather than carrying a
    payload, which is what stops it drifting from the Root cause page but also means
    there is nothing for the scrape to read. So the check recomputes the panel's two
    levels from the CSV instead:

        that month's owner cards sum to that month's confirmed misses
        each owner's driver bars sum to that owner's card

    A month whose cards did not add up to its own headline is exactly the fault the
    `42 + 9 + 35 = 86` row made visible on the cards, one level down.
    """
    sys.path.insert(0, str(REPO))
    from dashboard.metrics import monthly_breakdown, root_drivers, root_summary
    # The scrape reads the CSV raw, where `Month Label` does not exist -- the app derives
    # it in `data.py` from the first of Reporting Month / Month / Email/JIRA Date that is
    # present. Mirrored here in the same order, because a check that silently found no
    # months would pass on every tracker.
    df = df.copy()
    if "Month Label" not in df.columns:
        source = next((c for c in ("Reporting Month", "Month", "Email/JIRA Date")
                       if c in df.columns), None)
        if not source:
            return [], 0
        # `Reporting Month` already holds "Oct 2026"; naming the format keeps pandas
        # from falling back to dateutil row by row and warning about it in a gate's output.
        parsed = pd.to_datetime(df[source], format="%b %Y", errors="coerce")
        if parsed.isna().all():
            parsed = pd.to_datetime(df[source], errors="coerce", dayfirst=True)
        df["Month Label"] = parsed.dt.strftime("%b %Y")
    frame = monthly_breakdown(df)
    if frame.empty:
        return ["month panels: no month could be derived from the tracker"], 0
    problems, checked = [], 0
    for _, row in frame.iterrows():
        month = str(row["Month"])
        part = df[df["Month Label"].astype(str) == month]
        roots = root_summary(part)
        owners = {str(r[0]): int(r[1]) for r in roots}
        expect = {"Product": int(row["Product"]), "People": int(row["Analyst"]),
                  "Process": int(row["Process"])}
        checked += 1
        if sum(owners.values()) != int(row["Misses"]):
            problems.append(f"month panel {month!r}: owner cards sum to {sum(owners.values())}, "
                            f"the month holds {int(row['Misses'])} misses")
        for owner, want in expect.items():
            got = owners.get(owner, 0)
            if got != want:
                problems.append(f"month panel {month!r}: {owner} card shows {got}, "
                                f"the table says {want}")
        for owner, n in owners.items():
            bars = root_drivers(part, owner, top=99)
            total = int(bars["Misses"].sum()) if not bars.empty else 0
            if total != n:
                problems.append(f"month panel {month!r}: {owner} driver bars sum to {total} "
                                f"against a card of {n}")
    return problems, checked


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

    card_problems, cards_checked = card_detail_problems(df)
    problems += card_problems
    print(f"{'Executive Summary popups':34s} {cards_checked} card popup(s) add up")

    month_problems, months_checked = month_panel_problems(df)
    problems += month_problems
    print(f"{'Month dialogs':34s} {months_checked} month panel(s) add up")

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
