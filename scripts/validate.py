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
import json
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
# One key, or several slash-separated when a single incident spans more than one
# ticket -- the same convention multi-customer rows use for the Customer column.
JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+(?:/[A-Z][A-Z0-9]+-\d+)*$")


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
    # Two shapes, both of which have actually shipped here:
    #   a '?' butted against a letter -- a lost accent or dash inside a word
    #   a '?' standing alone between two words -- a lost arrow, e.g. "Apr 1 ? May 1"
    # A genuine question mark attaches to the word before it, so neither shape is
    # ordinary punctuation. The second was missed for months because the original
    # pattern required a letter immediately beside the '?'.
    patterns = [r"[A-Za-z0-9]\?[ ,\"]|\?[A-Za-z]", r"(?<=\w) \? (?=\w)"]
    seen: set[int] = set()
    for pattern in patterns:
        for m in re.finditer(pattern, text):
            if m.start() in seen:
                continue
            seen.add(m.start())
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
    same_month = len(drops) - len(cross_month)
    if cross_month:
        # A record landing in the wrong month is the append bug, not human entry order,
        # and `sort_tracker.py` fixes it in one command -- so this blocks. Day-level
        # jitter inside a month stays a warning: a record logged a few days late is
        # ordinary, and a validator that cries wolf gets ignored.
        rep.fail("row_order", f"{len(cross_month)} record(s) sit in the wrong month; "
                              f"run `python3 scripts/sort_tracker.py --all`")
        for i, prev, cur in cross_month[:5]:
            rep.fail("row_order", f"  row {i + 2}: {prev} followed by {cur}")
    if same_month:
        rep.warn("row_order", f"{same_month} same-month date regression(s); "
                              f"first at row {drops[0][0] + 2}: {drops[0][1]} followed by {drops[0][2]}")


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


def _norm(v) -> str:
    """One comparable string per cell, so a date read as a Timestamp on one side and a
    string on the other, or 1 vs 1.0, does not read as a difference."""
    if v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip()):
        return ""
    if pd.isna(v):
        return ""
    if isinstance(v, str):
        for fmt in ("%d-%b-%Y", "%b %Y"):
            ts = pd.to_datetime(v.strip(), format=fmt, errors="coerce")
            if pd.notna(ts):
                return ts.strftime("%Y-%m-%d")
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


def check_parity(df: pd.DataFrame, xlsx_path: Path, rep: Report) -> None:
    """The workbook's Data sheet and the CSV should describe the same records."""
    xl = pd.read_excel(xlsx_path, sheet_name="Data")
    if len(xl) != len(df):
        rep.fail("parity", f"workbook Data sheet has {len(xl)} rows, CSV has {len(df)}")
        return
    missing = [c for c in df.columns if c not in xl.columns]
    if missing:
        rep.fail("parity", f"column(s) {missing} are in the CSV but not the workbook Data sheet")
    # Every shared column, not a sample of three: a reordering bug that permuted one
    # file differently from the other would slip past any column that happened to match.
    shared = [c for c in df.columns if c in xl.columns]
    for col in shared:
        # A column the CSV writes as "Jan 2026" is a month, and the workbook holds it as
        # a real date; compare those at month precision so the two spellings agree.
        as_month = df[col].dropna().astype(str).str.strip().replace("", pd.NA).dropna()
        monthly = len(as_month) > 0 and pd.to_datetime(as_month, format="%b %Y", errors="coerce").notna().all()
        norm = (lambda v: _norm(v)[:7]) if monthly else _norm
        a = xl[col].map(norm).reset_index(drop=True)
        b = df[col].map(norm).reset_index(drop=True)
        if a.equals(b):
            continue
        rows = [i for i in range(len(a)) if a[i] != b[i]]
        rep.fail("parity", f"{col!r} differs in {len(rows)} row(s), first at row {rows[0] + 2}: "
                           f"workbook {a[rows[0]]!r} vs CSV {b[rows[0]]!r}")
    rep.note(f"workbook Data sheet and CSV agree on {len(xl)} rows across {len(shared)} shared column(s)")


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


def check_caches(csv_path: Path, xlsx_path: Path, rep: Report) -> None:
    """Every cached value in the workbook must already agree with the tracker.

    Excel recalculates on open, so these caches are not what Excel reads -- they are
    what everything that does not recalculate reads: GitHub's xlsx preview, a Google
    Sheets import, openpyxl(data_only=True), a file-manager preview. They drift on
    every append and had: four of six charts and all three Top Customers array columns
    were still showing 80-row figures against a 93-row tracker.

    `refresh_caches.py` recomputes them from the CSV; this asserts that has been run.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from refresh_caches import audit

    drift = audit(csv_path, xlsx_path)
    if drift:
        rep.fail("caches", f"{len(drift)} cached value(s) no longer match the tracker; "
                           f"run `python3 scripts/refresh_caches.py`")
        for line in drift[:6]:
            rep.fail("caches", f"  {line}")
    else:
        rep.note("chart and dynamic-array caches all match the tracker")


def check_spill_space(csv_path: Path, xlsx_path: Path, rep: Report) -> None:
    """A dynamic array that outgrows its declared ref needs empty cells to grow into.

    Excel resizes a spill on recalculation, but only when nothing is in the way -- a
    blocked spill shows #SPILL! instead of data. The Event Type table gains a row every
    time a new event type appears in the tracker, so the room below it must stay clear.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dashboard_calc import Sheet, col_to_num, load, split_ref

    calc = load(csv_path, xlsx_path)
    with zipfile.ZipFile(xlsx_path) as z:
        sheet = Sheet(z.read("xl/worksheets/sheet2.xml").decode("utf-8"))

    for anchor, span, grid in calc.array_regions():
        acol, arow = split_ref(anchor)
        declared_last = split_ref(sheet.array_ref[anchor].split(":")[-1])[1]
        needed_last = arow + len(grid) - 1
        if needed_last <= declared_last:
            continue
        blockers = [
            f"{chr(64 + col_to_num(acol) + c)}{r}"
            for r in range(declared_last + 1, needed_last + 1) for c in range(span)
            if sheet.text.get(f"{chr(64 + col_to_num(acol) + c)}{r}")
        ]
        if blockers:
            rep.fail("spill_space", f"the {anchor} array needs {len(grid)} rows but "
                                    f"{blockers[:4]} are in the way; Excel will show #SPILL!")
        else:
            rep.note(f"the {anchor} array must grow to row {needed_last}; that space is clear")


def check_styling(xlsx_path: Path, rep: Report) -> None:
    """Every record on the Data sheet must be formatted like every other record.

    Rows appended without matching the sheet render in a different font, which reads
    as a rendering fault rather than as new data -- and it is invisible until someone
    opens the workbook, which is exactly the kind of thing that goes unnoticed for
    months. It went unnoticed here: 13 rows sat in Calibri against the sheet's Aptos,
    and the Jira Key column was appended with no style at all.

    A cell carrying a fill is a deliberate human highlight and is exempt.
    `sort_tracker.py --all` normalises whatever this finds.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sort_tracker import data_cell_styles

    cells, fonts, fills = data_cell_styles(xlsx_path)
    if not cells:
        rep.fail("styling", "no data rows found on the Data sheet")
        return
    tally: dict[str, int] = {}
    for _, _, style in cells:
        f = fonts.get(style, "0") if style else "0"
        tally[f] = tally.get(f, 0) + 1
    main_font = max(tally, key=tally.get)

    odd = [(r, c) for r, c, style in cells
           if fills.get(style, "0") == "0" and (fonts.get(style, "0") if style else "0") != main_font]
    if odd:
        rows = sorted({r for r, _ in odd})
        rep.fail("styling", f"{len(odd)} cell(s) across {len(rows)} row(s) are not in the sheet's font "
                            f"(rows {rows[0]}-{rows[-1]}, e.g. {odd[0][1]}{odd[0][0]}); "
                            f"run `python3 scripts/sort_tracker.py --all`")
    else:
        rep.note(f"all {len(cells)} Data cells share one font, "
                 f"{sum(1 for _, _, s in cells if fills.get(s, '0') != '0')} highlighted cell(s) aside")


def check_table_ref(df: pd.DataFrame, xlsx_path: Path, rep: Report) -> None:
    """The ComplaintTracker table must span exactly the rows and columns that exist.

    Every Dashboard number is a COUNTIFS over this table. A ref left short after an
    append silently undercounts every chart, with nothing on the sheet to show for it
    -- no error, no gap, just quietly wrong totals. Nothing else here would catch that.
    """
    with zipfile.ZipFile(xlsx_path) as z:
        parts = [n for n in z.namelist() if re.match(r"xl/tables/table\d+\.xml$", n)]
        tables = {n: z.read(n).decode("utf-8") for n in parts}
    for name, xml in tables.items():
        if 'displayName="ComplaintTracker"' not in xml:
            continue
        ref = re.search(r'<table[^>]*\sref="([^"]+)"', xml).group(1)
        cols = len(re.findall(r"<tableColumn ", xml))
        top, bottom = (int(re.sub(r"\D", "", part)) for part in ref.split(":"))
        last_col = re.sub(r"\d", "", ref.split(":")[1])
        want_bottom = top + len(df)  # header row plus one row per record
        if bottom != want_bottom:
            rep.fail("table_ref", f"ComplaintTracker covers {ref} ({bottom - top} record row(s)) but the CSV "
                                  f"has {len(df)}; every Dashboard COUNTIFS is reading the wrong range")
        elif cols != len(df.columns):
            rep.fail("table_ref", f"ComplaintTracker declares {cols} column(s) to the CSV's {len(df.columns)}")
        else:
            rep.note(f"ComplaintTracker spans {ref}: {len(df)} records x {cols} columns, matching the CSV")
        return
    rep.fail("table_ref", "no ComplaintTracker table found; the Dashboard's COUNTIFS formulas cannot resolve")


def check_duplicates(df: pd.DataFrame, rep: Report) -> None:
    """The same complaint must not be logged twice.

    Nothing stops it: rows arrive from Jira and from email, and the same miss reaches
    the tracker down both paths. A duplicate inflates every count on the Dashboard, and
    unlike a wrong value it looks entirely plausible on the row itself.

    Two customers hitting the same event on the same day is a real pattern here, so the
    customer is part of the key -- a slash row (`Ford/GM`) is one record by convention.
    """
    keys = ["Email/JIRA Date", "Customer", "Event/Bulletin Title"]
    if any(k not in df.columns for k in keys):
        rep.fail("duplicates", f"cannot check for duplicates: {[k for k in keys if k not in df.columns]} missing")
        return
    norm = df[keys].apply(lambda c: c.fillna("").astype(str).str.strip().str.casefold())
    dupes = norm[norm.duplicated(keep=False)]
    if not dupes.empty:
        for _, rows in dupes.groupby(list(dupes.columns)):
            lines = [int(i) + 2 for i in rows.index]
            rep.fail("duplicates", f"rows {lines} are the same record: "
                                   f"{df.loc[rows.index[0], 'Customer']} / "
                                   f"{str(df.loc[rows.index[0], 'Event/Bulletin Title'])[:60]!r}")
        return
    rep.note(f"no two rows share a date, customer and title across {len(df)} records")


def definitions_entries(xlsx_path: Path) -> list[dict] | None:
    """Read the Definitions sheet into one dict per row: section, term, source column.

    Both definitions rules read the same sheet, and the sheet identifies itself by its
    "Source column" header rather than by name or position -- the same way the rest of
    this file refuses to hardcode layout. Returns None when no such sheet exists.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from dashboard_calc import Sheet

    with zipfile.ZipFile(xlsx_path) as z:
        names = {n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)}
        sheets = {n: Sheet(z.read(n).decode("utf-8")) for n in sorted(names)}
    sheet = next((sh for sh in sheets.values()
                  if any(v.strip() == "Source column" for v in sh.text.values())), None)
    if sheet is None:
        return None
    header = next(k for k, v in sheet.text.items() if v.strip() == "Source column")
    source_col = re.sub(r"\d", "", header)
    header_row = int(re.sub(r"\D", "", header))
    # The section, term and source-column headers sit on that same row; find each by
    # its own label so a reordered sheet still reads correctly.
    labels = {v.strip(): re.sub(r"\d", "", k) for k, v in sheet.text.items()
              if int(re.sub(r"\D", "", k)) == header_row}
    section_col = labels.get("Section")
    term_col = labels.get("Term / Field")
    definition_col = labels.get("Definition")
    allowed_col = labels.get("Allowed values / interpretation")

    rows: dict[int, dict[str, str]] = {}
    for ref, value in sheet.text.items():
        r = int(re.sub(r"\D", "", ref))
        if r > header_row:
            rows.setdefault(r, {})[re.sub(r"\d", "", ref)] = value.strip()
    return [{"row": r,
             "section": cells.get(section_col, ""),
             "term": cells.get(term_col, ""),
             "definition": cells.get(definition_col, ""),
             "allowed": cells.get(allowed_col, ""),
             "source": cells.get(source_col, "")}
            for r, cells in sorted(rows.items())]


def check_definitions(df: pd.DataFrame, xlsx_path: Path, rep: Report) -> None:
    """Every tracker column needs a row in the workbook's own data dictionary.

    The Definitions sheet is what a reader consults to understand a column, and it
    silently goes stale the moment a column is added -- `Jira Key` sat undocumented
    from the day it was introduced. The Definitions page in the app renders this sheet,
    so the gap is user-facing, not just internal.
    """
    entries = definitions_entries(xlsx_path)
    if entries is None:
        rep.fail("definitions", "no Definitions sheet found (no 'Source column' header)")
        return
    sourced = {e["source"] for e in entries}

    undocumented = [c for c in df.columns if c not in sourced]
    if undocumented:
        rep.fail("definitions", f"tracker column(s) {undocumented} have no row in the Definitions sheet")
    unknown = sorted(v for v in sourced if v and v != "Various" and v not in df.columns)
    if unknown:
        rep.fail("definitions", f"Definitions cite source column(s) {unknown} that the tracker does not have")
    # The Definitions sheet carries its own ListObject. A ref left short after an
    # append hides the new rows from the table -- and from anything reading the table
    # rather than the cells -- exactly as a short ComplaintTracker ref does.
    with zipfile.ZipFile(xlsx_path) as z:
        parts = [n for n in z.namelist() if re.match(r"xl/tables/table\d+\.xml$", n)]
        tables = [z.read(n).decode("utf-8") for n in parts]
    definitions_table = next((t for t in tables if 'displayName="DefinitionsTable"' in t), None)
    last_row = max(e["row"] for e in entries)
    short = False
    if definitions_table is None:
        rep.fail("definitions", "no DefinitionsTable found on the Definitions sheet")
        short = True
    else:
        ref = re.search(r'<table[^>]*\sref="([^"]+)"', definitions_table).group(1)
        bottom = int(re.sub(r"\D", "", ref.split(":")[1]))
        if bottom != last_row:
            rep.fail("definitions", f"DefinitionsTable covers {ref} but the sheet is populated "
                                    f"through row {last_row}; rows appended past the ref are "
                                    f"outside the table")
            short = True

    if not undocumented and not unknown and not short:
        rep.note(f"Definitions sheet documents all {len(df.columns)} tracker columns "
                 f"in {last_row - 3} rows, all inside DefinitionsTable")


def check_enum_definitions(df: pd.DataFrame, xlsx_path: Path, rep: Report) -> None:
    """Every value in an enumerated tracker column needs its own Definitions row.

    `definitions` watches the sheet's *columns*; nothing watched its *values*. The
    Definitions sheet is the only place a reader can look up what "Source Coverage"
    or "Clarification Provided" means, and it is the taxonomy an analyst picks from
    when logging a new row. A value used in the tracker but absent from the sheet is
    a term in circulation that nobody defined -- which is how the tracker grew six
    undocumented event types, four undocumented reason labels and a `Pending` fix
    status while every other check stayed green.

    Only value taxonomies are checked. Rows whose section is a field definition or a
    general operational term describe a column or a piece of vocabulary, not a value.
    Boolean flags are listed as "Yes -- Missed_Flag" so the sheet can define both
    senses of a shared word; that suffix is stripped before matching.
    """
    entries = definitions_entries(xlsx_path)
    if entries is None:
        rep.fail("enum_definitions", "no Definitions sheet found (no 'Source column' header)")
        return

    documented: dict[str, set[str]] = {}
    for e in entries:
        source = e["source"]
        if not source or source == "Various":
            continue
        if e["section"] in ("Field definition", "Operational term"):
            continue
        term = re.sub(r"\s+[\u2014-]\s+" + re.escape(source) + r"$", "", e["term"]).strip()
        documented.setdefault(source, set()).add(term)

    if not documented:
        rep.fail("enum_definitions", "the Definitions sheet lists no value taxonomies at all")
        return

    gaps = []
    checked = 0
    for source in sorted(documented):
        if source not in df.columns:
            continue  # check_definitions already reports a source column the tracker lacks
        checked += 1
        used = {str(v).strip() for v in df[source].dropna() if str(v).strip()}
        missing = sorted(used - documented[source])
        if missing:
            gaps.append((source, missing))
    for source, missing in gaps:
        rep.fail("enum_definitions",
                 f"{source!r} value(s) {missing} are used in the tracker but have no row in the "
                 f"Definitions sheet; a reader cannot look them up and an analyst cannot pick them")
    if not gaps:
        total = sum(len(v) for k, v in documented.items() if k in df.columns)
        rep.note(f"Definitions sheet defines every value in {checked} enumerated column(s) "
                 f"({total} terms)")


def check_definitions_export(csv_path: Path, xlsx_path: Path, rep: Report) -> None:
    """definitions.json must still match the sheet it was generated from.

    The app's Definitions page reads that file rather than the workbook, so the CSV-only
    deploy path still has a glossary. That is only safe while the file cannot silently
    rot -- which is exactly what the hardcoded dict it replaced did, drifting until it
    had no Event type section at all and defined a term the tracker never had.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from export_definitions import DEFAULT_JSON, build, render

    if not DEFAULT_JSON.exists():
        rep.fail("definitions_export", f"{DEFAULT_JSON.name} is missing; the app's Definitions "
                                       f"page will render empty. Run scripts/export_definitions.py")
        return
    want = render(build(csv_path, xlsx_path))
    if DEFAULT_JSON.read_text(encoding="utf-8") != want:
        rep.fail("definitions_export", f"{DEFAULT_JSON.name} no longer matches the Definitions "
                                       f"sheet; run `python3 scripts/export_definitions.py`")
        return
    payload = json.loads(want)
    rep.note(f"{DEFAULT_JSON.name} matches the sheet: {payload['terms']} terms in "
             f"{len(payload['groups'])} groups, {payload['pruned']} pruned as unused")


def check_formula_columns(df: pd.DataFrame, xlsx_path: Path, rep: Report) -> None:
    """Every ComplaintTracker[...] reference, on any sheet, must name a real column.

    The Management Readout is twelve formulas over this table and holds no cached
    values at all, so a renamed or dropped column turns the whole sheet into #REF!
    the next time someone opens it, with nothing here to warn them first. The same
    reference style drives the Dashboard, so this covers both in one pass.
    """
    with zipfile.ZipFile(xlsx_path) as z:
        parts = sorted(n for n in z.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        blobs = {n: z.read(n).decode("utf-8") for n in parts}
    referenced: dict[str, set[str]] = {}
    for name, xml in blobs.items():
        for m in re.finditer(r"ComplaintTracker\[([^\]#]+)\]", xml):
            referenced.setdefault(m.group(1), set()).add(Path(name).stem)
    unknown = {c: sorted(v) for c, v in referenced.items() if c not in df.columns}
    if unknown:
        for col, where in unknown.items():
            rep.fail("formula_columns", f"formulas on {where} reference ComplaintTracker[{col}], "
                                        f"which is not a tracker column; those cells resolve to #REF!")
        return
    rep.note(f"{len(referenced)} distinct table column(s) referenced by formulas all exist")


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
    check_duplicates(df, rep)

    if args.xlsx.exists():
        blocks = dashboard_blocks(args.xlsx)
        check_enum_coverage(df, blocks, rep)
        check_month_coverage(df, blocks, rep)
        check_parity(df, args.xlsx, rep)
        check_dynamic_arrays(args.xlsx, rep)
        check_spill_space(args.csv, args.xlsx, rep)
        check_caches(args.csv, args.xlsx, rep)
        check_table_ref(df, args.xlsx, rep)
        check_styling(args.xlsx, rep)
        check_definitions(df, args.xlsx, rep)
        check_enum_definitions(df, args.xlsx, rep)
        check_definitions_export(args.csv, args.xlsx, rep)
        check_formula_columns(df, args.xlsx, rep)
    else:
        rep.note(f"{args.xlsx.name} not found; ran CSV-only checks")

    return rep.emit()


if __name__ == "__main__":
    sys.exit(main())
