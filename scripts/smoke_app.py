#!/usr/bin/env python3
"""Load every dashboard page and report exceptions or empty renders. No screenshots.

`validate.py` checks the data and the workbook; nothing checked the app itself. A
silently broken chart shipped here once -- `chart()` was called with its title in
the `value_col` position, so most bar charts rendered "Chart cannot be rendered
because required fields are missing" instead of failing loudly. That was only
caught by looking at a screenshot. This script catches that class of bug by reading
the DOM instead, which costs a fraction of the tokens an image does.

Starts Streamlit against the local CSV, clicks each page, and asserts:
  - no Streamlit exception container is present
  - no in-app error text ("cannot be rendered", "required fields are missing", ...)
  - each page renders the number of charts/tables it should

Usage:
  python3 scripts/smoke_app.py            # starts and stops Streamlit itself
  python3 scripts/smoke_app.py --port 8502
Requires playwright with chromium available (PLAYWRIGHT_BROWSERS_PATH honoured).
Exits non-zero if any page has a problem.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHROMIUM = "/opt/pw-browsers/chromium"

# page -> (minimum charts, minimum tables). A page that should draw a chart but
# renders zero is the exact symptom of the bug this script exists to catch.
EXPECTED: dict[str, tuple[int, int]] = {
    "Executive Summary": (6, 6),
    "Open items": (0, 4),
    "SOURCE 01 · Monthly trend": (2, 2),
    "SOURCE 02 · Fix status": (1, 1),
    "SOURCE 03 · Severity": (1, 1),
    "SOURCE 04 · Root cause": (1, 4),
    "SOURCE 05 · Top customers": (1, 5),
    "SOURCE 06 · Automation focus": (1, 1),
    "DETAIL · Event workload": (1, 1),
    "Repeat patterns": (1, 1),
    "Automation urgency": (1, 1),
    "Dynamic Source Discovery": (3, 7),
    "Definitions": (0, 12),
    "Complaint Tracker": (0, 1),
}

ERROR_TEXT = [
    "Traceback", "StreamlitAPIException", "KeyError", "ValueError", "AttributeError",
    "cannot be rendered", "required fields are missing",
    "could not be loaded",
]


def wait_for_server(url: str, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8599)
    ap.add_argument("--keep-running", action="store_true", help="leave Streamlit up after the run")
    args = ap.parse_args()
    url = f"http://localhost:{args.port}"

    # No secrets are written: the app resolves the tracker sitting next to app.py on
    # its own, which is the same zero-config path a Streamlit Cloud deploy takes. If
    # that discovery regresses, this smoke test fails, which is the point.
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app.py",
         "--server.headless", "true", "--server.port", str(args.port)],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    try:
        if not wait_for_server(url):
            print(f"FAIL — Streamlit did not come up on {url}")
            return 1
        return run_checks(url)
    finally:
        if not args.keep_running:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


def run_checks(url: str) -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("FAIL — playwright is not installed (pip install playwright)")
        return 1

    problems: list[str] = []
    with sync_playwright() as p:
        launch = {"executable_path": CHROMIUM} if os.path.exists(CHROMIUM) else {}
        browser = p.chromium.launch(**launch)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        page.goto(url, wait_until="networkidle", timeout=45000)
        page.wait_for_timeout(2500)

        for name, (min_charts, min_tables) in EXPECTED.items():
            try:
                page.get_by_text(name, exact=True).first.click()
            except Exception as exc:
                problems.append(f"{name}: nav item not found ({type(exc).__name__})")
                continue
            page.wait_for_timeout(1800)

            exceptions = page.locator('[data-testid="stException"]').count()
            body = page.inner_text("body")
            hits = sorted({t for t in ERROR_TEXT if t in body})
            charts = page.locator(".js-plotly-plot").count()
            tables = page.locator("table.excel-table").count()

            issues = []
            if exceptions:
                issues.append(f"{exceptions} exception container(s)")
            if hits:
                issues.append(f"error text {hits}")
            if charts < min_charts:
                issues.append(f"{charts} chart(s), expected >= {min_charts}")
            if tables < min_tables:
                issues.append(f"{tables} table(s), expected >= {min_tables}")

            status = "ok" if not issues else "; ".join(issues)
            print(f"{name:34s} charts={charts:2d} tables={tables:2d}  {status}")
            if issues:
                problems.append(f"{name}: {status}")

        browser.close()

    if problems:
        print(f"\nFAIL — {len(problems)} page(s) with problems:")
        for p_ in problems:
            print(f"  ✗ {p_}")
        return 1
    print(f"\nPASS — {len(EXPECTED)} pages rendered with no exceptions or empty charts.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
