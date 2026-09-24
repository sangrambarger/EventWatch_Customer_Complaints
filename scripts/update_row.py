#!/usr/bin/env python3
"""Change fields on records already in the tracker: CSV and Data sheet together.

`append_row.py` is the only supported way to add a record; this is its counterpart for
the edit that always follows. A row is staged from an open Jira ticket before anyone
knows why the event was missed, and the answer lands days later in a comment: the cause
turns out to be a keyword gap rather than a source gap, an RCA goes out, the ticket
resolves. Those are four fields on a row that already exists in two files.

Editing by hand has the same failure modes as appending by hand. The workbook's column
order is not the CSV's, so a positional write lands in the wrong column; a date is
dd-mmm-yyyy in the CSV and a serial on the sheet; an emptied cell still needs its style
or `validate.py`'s `styling` rule fires. And the two files drift silently -- `parity`
is the only thing that notices, which means noticing after the fact.

Guards, because a wrong edit here is worse than no edit:

  * a `match` that selects no row, or more than one, refuses rather than guessing;
  * every CSV line is re-serialised and compared to itself first, so a file whose
    quoting this script would not reproduce byte-for-byte is refused untouched;
  * the sheet row is located by position and then *verified* against the CSV row's own
    key columns before anything is written;
  * a column that is not a tracker column refuses, and a value equal to what is already
    there is reported as a no-op rather than written.

It deliberately does not refresh caches: run refresh_caches.py then validate.py after.

Usage:
  python3 scripts/update_row.py --json changes.json
  python3 scripts/update_row.py --json changes.json --dry-run
  echo '[{"match": {"Jira Key": "EAO-41"}, "set": {"Sub-type": "Keyword Update"}}]' \
      | python3 scripts/update_row.py --json -

Each change is {"match": {column: exact value, ...}, "set": {column: new value, ...}}.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO / "customer_tracker.csv"
DEFAULT_XLSX = REPO / "EventWatch_Customer_Complaints_2026.xlsx"
DATA_SHEET = "xl/worksheets/sheet1.xml"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from append_row import (  # noqa: E402  - shares one definition of the sheet's shape
    DATE_COLUMNS, DEFAULT_STYLE, NUMERIC, STYLES, serial,
)

# Columns checked against the sheet before writing, so a row that has drifted out of
# alignment with the CSV is caught here rather than by `parity` two commands later.
VERIFY = ["Jira Key", "Customer", "Event/Bulletin Title"]


def csv_line(values: list[str]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="")
    writer.writerow(values)
    return buf.getvalue()


def read_csv(csv_path: Path) -> tuple[list[str], list[str], list[list[str]], str]:
    """Return (columns, raw data lines, parsed rows, trailing newline).

    Refuses a file this script could not rewrite byte-for-byte. Re-serialising one
    edited line is only safe while every untouched line round-trips exactly; if the
    file were ever written with different quoting, the diff would show lines nobody
    changed and the real edit would be lost in it.
    """
    text = csv_path.read_text(encoding="utf-8")
    lines = text.split("\n")
    tail = "\n" if lines and lines[-1] == "" else ""
    if tail:
        lines = lines[:-1]
    columns = next(csv.reader([lines[0]]))
    rows = []
    for number, line in enumerate(lines[1:], start=2):
        values = next(csv.reader([line]))
        if csv_line(values) != line:
            raise SystemExit(f"refusing to edit: CSV line {number} would not round-trip "
                             f"unchanged; this script would rewrite lines nobody edited")
        if len(values) != len(columns):
            raise SystemExit(f"refusing to edit: CSV line {number} has {len(values)} "
                             f"field(s), header has {len(columns)}")
        rows.append(values)
    return columns, lines, rows, tail


def find(rows: list[list[str]], columns: list[str], match: dict) -> int:
    unknown = [c for c in match if c not in columns]
    if unknown:
        raise SystemExit(f"refusing to edit: {unknown} are not tracker columns")
    hits = [i for i, values in enumerate(rows)
            if all(values[columns.index(c)].strip() == str(v).strip()
                   for c, v in match.items())]
    if not hits:
        raise SystemExit(f"no record matches {match}")
    if len(hits) > 1:
        raise SystemExit(f"{len(hits)} records match {match} (CSV rows "
                         f"{[i + 2 for i in hits]}); narrow the match")
    return hits[0]


def sheet_header(sheet: str) -> dict[str, str]:
    header: dict[str, str] = {}
    for m in re.finditer(r'<c r="([A-Z]+)1"[^>]*>(?:<is>)?<t>(.*?)</t>', sheet):
        header[m.group(2).strip()] = m.group(1)
    return header


def cell_xml(ref: str, column: str, value: str, style: str) -> str:
    value = value.strip()
    if column in NUMERIC:
        if not value:
            return f'<c r="{ref}" s="{style}" t="n" />'
        number = serial(value) if column in DATE_COLUMNS else value
        return f'<c r="{ref}" s="{style}" t="n"><v>{number}</v></c>'
    if not value:
        return f'<c r="{ref}" s="{style}" t="n" />'
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'


def cell_text(row_xml: str, letter: str, row_no: int) -> str:
    """The visible text of one cell, for the pre-write verification."""
    m = re.search(rf'<c r="{letter}{row_no}"[^>]*?(?:/>|>(.*?)</c>)', row_xml, re.S)
    if not m or not m.group(1):
        return ""
    t = re.search(r"<t[^>]*>(.*?)</t>", m.group(1), re.S)
    if t:
        return re.sub(r"&amp;", "&", re.sub(r"&lt;|&gt;|&quot;", "", t.group(1))).strip()
    v = re.search(r"<v>(.*?)</v>", m.group(1), re.S)
    return v.group(1).strip() if v else ""


def replace_cell(sheet: str, row_no: int, letter: str, column: str, value: str) -> str:
    """Swap one cell, keeping whatever style it already carries."""
    pattern = rf'<c r="{letter}{row_no}"(?:\s[^>]*?)?(?:/>|>.*?</c>)'
    m = re.search(pattern, sheet, re.S)
    if not m:
        raise SystemExit(f"Data sheet has no cell {letter}{row_no}")
    style = re.search(r'\ss="(\d+)"', m.group(0))
    keep = style.group(1) if style else str(
        NUMERIC.get(column, STYLES.get(column, DEFAULT_STYLE)))
    return sheet[:m.start()] + cell_xml(f"{letter}{row_no}", column, value, keep) + sheet[m.end():]


def apply(changes: list[dict], csv_path: Path, xlsx_path: Path, dry_run: bool) -> list[str]:
    columns, lines, rows, tail = read_csv(csv_path)
    sheet = zipfile.ZipFile(xlsx_path).read(DATA_SHEET).decode("utf-8")
    header = sheet_header(sheet)
    absent = [c for c in columns if c not in header]
    if absent:
        raise SystemExit(f"Data sheet has no column for {absent}")

    report = []
    for change in changes:
        match, updates = change.get("match"), change.get("set")
        if not match or not updates:
            raise SystemExit("each change needs both 'match' and 'set'")
        unknown = [c for c in updates if c not in columns]
        if unknown:
            raise SystemExit(f"refusing to edit: {unknown} are not tracker columns")

        index = find(rows, columns, match)
        row_no = index + 2  # CSV data line 1 is sheet row 2; parity keeps them aligned
        row_xml = re.search(rf'<row r="{row_no}"[^>]*>.*?</row>', sheet, re.S)
        if not row_xml:
            raise SystemExit(f"Data sheet has no row {row_no}")
        for column in VERIFY:
            want = rows[index][columns.index(column)].strip()
            got = cell_text(row_xml.group(0), header[column], row_no)
            if want != got:
                raise SystemExit(
                    f"row {row_no} is not the CSV's row {row_no}: {column} reads "
                    f"{got!r} on the sheet and {want!r} in the CSV. Run validate.py")

        touched = []
        for column, value in updates.items():
            value = "" if value is None else str(value)
            if rows[index][columns.index(column)] == value:
                report.append(f"row {row_no}: {column} already {value!r}, left alone")
                continue
            was = rows[index][columns.index(column)]
            rows[index][columns.index(column)] = value
            sheet = replace_cell(sheet, row_no, header[column], column, value)
            touched.append(column)
            report.append(f"row {row_no}: {column}: {was[:40]!r} -> {value[:40]!r}")
        if touched:
            lines[index + 1] = csv_line(rows[index])
            key = rows[index][columns.index("Jira Key")] or "no key"
            report.append(f"row {row_no} ({key}): {len(touched)} field(s) updated")

    if dry_run:
        return ["(dry run, nothing written)"] + report

    csv_path.write_text("\n".join(lines) + tail, encoding="utf-8")
    src = zipfile.ZipFile(xlsx_path)
    tmp = xlsx_path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = sheet.encode("utf-8") if item.filename == DATA_SHEET else src.read(item.filename)
            out.writestr(item, data)
    src.close()
    shutil.move(tmp, xlsx_path)
    report.append("next: python3 scripts/refresh_caches.py && python3 scripts/validate.py")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", required=True, help="path to a JSON list of changes, or - for stdin")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.json == "-" else Path(args.json).read_text(encoding="utf-8")
    payload = json.loads(raw)
    changes = payload if isinstance(payload, list) else [payload]
    for line in apply(changes, args.csv, args.xlsx, args.dry_run):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
