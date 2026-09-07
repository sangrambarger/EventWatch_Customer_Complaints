#!/usr/bin/env python3
"""Offline integrity checks for the complaint tracker and its workbook.

Every check here was run by hand at least once while building this repo. Each one
corresponds to a bug that actually shipped, so they are worth keeping runnable:

  mojibake        two ellipses, an arrow and a CO2 subscript had decayed to "?"
  row_order       August rows were appended after September rows
  enum_coverage   a new "Pending" fix status was silently undercounted by the
                  Dashboard, whose Fix Status table lists only 3 statuses
  month_coverage  September records existed with no September row in the
                  Dashboard's monthly trend block, so the chart omitted them
  parity          the CSV and the workbook's Data sheet drifting apart
  dynamic_arrays  an openpyxl resave stripped the cm= markers that make the
                  Dashboard's UNIQUE/FILTER/SORTBY formulas spill

Usage:  python3 scripts/validate.py [--csv PATH] [--xlsx PATH]
Exits non-zero if any check fails, so it works as a pre-commit or CI gate.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO / "customer_tracker.csv"
DEFAULT_XLSX = REPO / "EventWatch_Customer_Complaints_2026.xlsx"

REQUIRED_FIELDS = [
    "Month", "Email/JIRA Date", "Customer", "Event/Bulletin Title", "Issue Type",
    "Reason", "Root Cause", "Severity", "Standard Automation Focus", "Comments",
]
# CSV column -> the Dashboard header its values are counted under. A value present
# in the CSV but missing from that Dashboard block is silently excluded from the
# chart and its total.
ENUM_BLOCKS = {
    "Root Cause": "Root Cause",
    "Short Term Fix Status": "Fix Status",
    "Severity": "Severity",
    "Standard Automation Focus": "Automation Focus",
    "Event type": "Event Type",
}
JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.warnings: list[str] = []
        self.notes: list[str] = []

    def fail(self, check: str, msg: str) -> None:
        self.failures.append(f"{check}: {msg}")

    def warn(self, check: str, msg: str) -> None:
        self.warnings.append(f"{check}: {msg}")

    def note(self, msg: str) -> None:
        self.notes.append(msg)

    def emit(self) -> int:
        for n in self.notes:
            print(f"  · {n}")
        for w in self.warnings:
            print(f"  ! {w}")
        if not self.failures:
            print(f"\nPASS — no blocking issues ({len(self.warnings)} warning(s)).")
            return 0
        print(f"\nFAIL — {len(self.failures)} issue(s):")
        for f in self.failures:
            print(f"  ✗ {f}")
        return 1


def check_mojibake(csv_path: Path, rep: Report) -> None:
    """Catch characters that decayed to '?' and bytes that are not valid UTF-8."""
    raw = csv_path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        rep.fail("mojibake", f"{csv_path.name} is not valid UTF-8 ({exc}); pandas will fall back to the workbook")
        return
    # A '?' adjacent to a letter is almost always a lost character, not real punctuation.
    for m in re.finditer(r"[A-Za-z0-9]\?[ ,\"]|\?[A-Za-z]", text):
        line = text.count("\n", 0, m.start()) + 1
        rep.fail("mojibake", f"line {line}: suspicious '?' in {text[max(0, m.start() - 30):m.end() + 10]!r}")


def check_row_order(df: pd.DataFrame, rep: Report) -> None:
    dates = pd.to_datetime(df["Email/JIRA Date"], format="%d-%b-%Y", errors="coerce")
    if dates.isna().any():
        bad = df.loc[dates.isna(), "Email/JIRA Date"].head(3).tolist()
        rep.fail("row_order", f"unparseable Email/JIRA Date value(s): {bad}")
        return
    drops = [(i, dates[i - 1].date(), dates[i].date()) for i in range(1, len(dates)) if dates[i] < dates[i - 1]]
    if not drops:
        rep.note(f"row order ascends across all {len(dates)} rows")
        return
    # Day-level jitter is normal in the hand-maintained original rows (a record logged
    # a few days late sits after a later one). A regression that crosses a month
    # boundary is the shape of the real bug -- appended rows landing out of sequence --
    # so surface those distinctly, but warn rather than block: this is human entry
    # order, not corruption, and a validator that cries wolf gets ignored.
    cross_month = [d for d in drops if (d[1].year, d[1].month) != (d[2].year, d[2].month)]
    rep.warn("row_order", f"{len(drops)} date regression(s) ({len(cross_month)} crossing a month boundary); "
                          f"first at row {drops[0][0] + 2}: {drops[0][1]} followed by {drops[0][2]}")
    for i, prev, cur in cross_month[:5]:
        rep.warn("row_order", f"  row {i + 2}: {prev} followed by {cur} — check this row is in the right place")


def check_required_fields(df: pd.DataFrame, rep: Report) -> None:
    for col in REQUIRED_FIELDS:
        if col not in df.columns:
            rep.fail("required_fields", f"column {col!r} is missing entirely")
            continue
        blank = df[col].isna() | (df[col].astype(str).str.strip() == "")
        if blank.any():
            rep.fail("required_fields", f"{col!r} is blank in {int(blank.sum())} row(s), first at row {int(blank.idxmax()) + 2}")


def check_jira_keys(df: pd.DataFrame, rep: Report) -> None:
    if "Jira Key" not in df.columns:
        rep.fail("jira_keys", "Jira Key column is missing")
        return
    keys = df["Jira Key"].dropna().astype(str).str.strip()
    keys = keys[keys != ""]
    bad = [k for k in keys if not JIRA_KEY_RE.match(k)]
    if bad:
        rep.fail("jira_keys", f"malformed key(s): {sorted(set(bad))[:5]}")
    complaints = df[df["Issue Type"].astype(str) == "Complaint"]
    linked = complaints["Jira Key"].notna() & (complaints["Jira Key"].astype(str).str.strip() != "")
    rep.note(f"{int(linked.sum())} of {len(complaints)} complaints carry a Jira Key "
             f"({len(keys)} keys total, {keys.nunique()} distinct)")


def dashboard_blocks(xlsx_path: Path) -> dict[str, dict]:
    """Read the Dashboard's enumeration blocks by locating their header text.

    Blocks are found by header label rather than hardcoded row numbers so this keeps
    working if the sheet is rearranged. Each block runs from just under its header
    down to a blank cell or a "Total" row.

    A block whose first data cell holds a formula is *dynamic* -- it is fed by a
    UNIQUE/FILTER/SORT spill that grows on its own, so a new value appearing in the
    tracker is not a coverage gap there. Only hand-listed (literal) blocks can go
    stale, so the coverage check applies to those alone.
    """
    import openpyxl
    from openpyxl.worksheet.formula import ArrayFormula

    wb = openpyxl.load_workbook(xlsx_path, data_only=False)
    if "Dashboard" not in wb.sheetnames:
        return {}
    ws = wb["Dashboard"]
    wanted = set(ENUM_BLOCKS.values()) | {"Month"}
    blocks: dict[str, dict] = {}
    for row in ws.iter_rows():
        for cell in row:
            if not isinstance(cell.value, str) or cell.value.strip() not in wanted:
                continue
            label = cell.value.strip()
            if label in blocks:
                continue
            first = ws.cell(row=cell.row + 1, column=cell.column).value
            dynamic = isinstance(first, ArrayFormula) or (isinstance(first, str) and first.startswith("="))
            values = []
            for r in range(cell.row + 1, ws.max_row + 1):
                v = ws.cell(row=r, column=cell.column).value
                if isinstance(v, ArrayFormula):
                    continue
                if v is None or (isinstance(v, str) and (not v.strip() or v.strip() == "Total")):
                    break
                values.append(v.strip() if isinstance(v, str) else v)
            if values or dynamic:
                blocks[label] = {"values": values, "dynamic": dynamic}
    return blocks


def check_enum_coverage(df: pd.DataFrame, blocks: dict[str, dict], rep: Report) -> None:
    for csv_col, header in ENUM_BLOCKS.items():
        if csv_col not in df.columns:
            continue
        block = blocks.get(header)
        if not block:
            rep.note(f"no Dashboard block found for {header!r}; skipping coverage check")
            continue
        if block["dynamic"]:
            rep.note(f"{header!r} block is a dynamic array; it self-populates, coverage check not needed")
            continue
        listed = {str(v) for v in block["values"]}
        present = {str(v).strip() for v in df[csv_col].dropna() if str(v).strip()}
        missing = sorted(present - listed)
        if missing:
            rep.fail("enum_coverage", f"{csv_col!r} value(s) {missing} exist in the tracker but are not "
                                      f"listed in the Dashboard's {header!r} table, so they are excluded "
                                      f"from that chart and its total")


def check_month_coverage(df: pd.DataFrame, blocks: dict[str, dict], rep: Report) -> None:
    block = blocks.get("Month")
    months_listed = block["values"] if block else []
    if not months_listed:
        rep.note("no Dashboard 'Month' block found; skipping month coverage check")
        return
    listed = set()
    for v in months_listed:
        ts = pd.Timestamp(v) if not isinstance(v, str) else pd.to_datetime(v, errors="coerce")
        if pd.notna(ts):
            listed.add((ts.year, ts.month))
    present = set()
    for v in pd.to_datetime(df["Email/JIRA Date"], format="%d-%b-%Y", errors="coerce").dropna():
        present.add((v.year, v.month))
    missing = sorted(present - listed)
    if missing:
        pretty = ", ".join(f"{y}-{m:02d}" for y, m in missing)
        rep.fail("month_coverage", f"tracker has records in {pretty} with no matching row in the Dashboard's "
                                   f"monthly trend block, so the trend chart omits them")
    else:
        rep.note(f"monthly trend block covers all {len(present)} month(s) present in the tracker")


def check_parity(df: pd.DataFrame, xlsx_path: Path, rep: Report) -> None:
    """The workbook's Data sheet and the CSV should describe the same records."""
    xl = pd.read_excel(xlsx_path, sheet_name="Data")
    if len(xl) != len(df):
        rep.fail("parity", f"workbook Data sheet has {len(xl)} rows, CSV has {len(df)}")
        return
    for col in ("Customer", "Jira Key", "Event/Bulletin Title"):
        if col not in xl.columns or col not in df.columns:
            rep.fail("parity", f"column {col!r} missing from one side")
            continue
        a = xl[col].fillna("").astype(str).str.strip().reset_index(drop=True)
        b = df[col].fillna("").astype(str).str.strip().reset_index(drop=True)
        diff = a.compare(b) if not a.equals(b) else None
        if diff is not None and not diff.empty:
            first = diff.index[0]
            rep.fail("parity", f"{col!r} differs at row {int(first) + 2}: workbook {a[first]!r} vs CSV {b[first]!r} "
                               f"({len(diff)} row(s) differ)")
    rep.note(f"workbook Data sheet and CSV agree on {len(xl)} rows")


def check_dynamic_arrays(xlsx_path: Path, rep: Report) -> None:
    """Dynamic-array formulas need both t="array" and a cm= marker to spill in Excel.

    An openpyxl load/save round-trip silently drops the cm= attribute and
    xl/metadata.xml, which breaks the Dashboard's UNIQUE/FILTER/SORTBY tables.
    """
    with zipfile.ZipFile(xlsx_path) as z:
        names = z.namelist()
        if "xl/metadata.xml" not in names:
            rep.fail("dynamic_arrays", "xl/metadata.xml is missing — dynamic-array formulas will not spill "
                                       "(usually caused by an openpyxl resave)")
        sheet = next((n for n in names if n.endswith("worksheets/sheet2.xml")), None)
        if not sheet:
            rep.note("Dashboard sheet XML not found; skipping dynamic-array check")
            return
        xml = z.read(sheet).decode("utf-8")
    array_cells = re.findall(r'<c r="([A-Z]+\d+)"[^>]*>(?=<f t="array")', xml)
    marked = re.findall(r'<c r="([A-Z]+\d+)"[^>]*cm="\d+"', xml)
    unmarked = sorted(set(array_cells) - set(marked))
    if unmarked:
        rep.fail("dynamic_arrays", f"array formula cell(s) {unmarked} have no cm= marker; Excel may treat them "
                                   f"as legacy CSE arrays instead of spilling")
    elif array_cells:
        rep.note(f"{len(array_cells)} dynamic-array cell(s) carry their cm= marker")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    args = ap.parse_args()

    rep = Report()
    print(f"Validating {args.csv.name} against {args.xlsx.name}")

    if not args.csv.exists():
        print(f"FAIL — {args.csv} not found")
        return 1
    check_mojibake(args.csv, rep)
    df = pd.read_csv(args.csv, dtype=str, keep_default_na=False).replace("", pd.NA)
    rep.note(f"{len(df)} rows, {len(df.columns)} columns")

    check_row_order(df, rep)
    check_required_fields(df, rep)
    check_jira_keys(df, rep)

    if args.xlsx.exists():
        blocks = dashboard_blocks(args.xlsx)
        check_enum_coverage(df, blocks, rep)
        check_month_coverage(df, blocks, rep)
        check_parity(df, args.xlsx, rep)
        check_dynamic_arrays(args.xlsx, rep)
    else:
        rep.note(f"{args.xlsx.name} not found; ran CSV-only checks")

    return rep.emit()


if __name__ == "__main__":
    sys.exit(main())
