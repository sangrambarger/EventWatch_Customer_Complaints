#!/usr/bin/env python3
"""Append one record to the tracker: CSV and workbook Data sheet, in one step.

Appending by hand is the single most error-prone edit in this repo, and it has gone
wrong before. The workbook's column order is not the CSV's -- `Jira Key` is the third
CSV column and column W on the sheet -- so a row written positionally lands one column
off, and only `validate.py`'s full-width parity check catches it. `ComplaintTracker`'s
ref must grow with the row or every Dashboard COUNTIFS silently undercounts. Dates are
serials on the sheet and dd-mmm-yyyy in the CSV. Empty cells still need their style.

This script does all of that from one dict, keyed by CSV column name, and derives the
fields nobody should retype (Month, Reporting Month, Month_Sort, Number of Customers,
Routed To). It refuses to write anything unless every required field is present, so a
half-filled row cannot reach either file.

It deliberately does not refresh caches: run refresh_caches.py then validate.py after,
which is a gate rather than a habit.

Usage:
  python3 scripts/append_row.py --json record.json
  python3 scripts/append_row.py --json record.json --dry-run
  echo '{"Email/JIRA Date": "10-Sep-2026", ...}' | python3 scripts/append_row.py --json -

Required keys: Email/JIRA Date, Customer, Event type, Event/Bulletin Title, Issue Type,
Reason, Root Cause, Severity, Standard Automation Focus, Comments.
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
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO / "customer_tracker.csv"
DEFAULT_XLSX = REPO / "EventWatch_Customer_Complaints_2026.xlsx"
DATA_SHEET = "xl/worksheets/sheet1.xml"

REQUIRED = ["Email/JIRA Date", "Customer", "Event type", "Event/Bulletin Title",
            "Issue Type", "Reason", "Root Cause", "Severity",
            "Standard Automation Focus", "Comments"]

# Excel's 1900 date system, with its phantom 29-Feb-1900: day 1 is 01-Jan-1900 and
# everything from 01-Mar-1900 on is offset by one.
EPOCH = datetime(1899, 12, 30)

# Sheet columns that are not inline strings, and the style each carries. Read off the
# rows already on the sheet rather than invented; a mismatch here shows up as a cell
# in the wrong font, which validate.py's `styling` rule blocks.
NUMERIC = {"Month": 35, "Email/JIRA Date": 37, "Number of Customers": 39,
           "Month_Sort": 39, "Delay (Hours)": 39}
STYLES = {"Reporting Month": 35}
DEFAULT_STYLE = 33


def serial(value: str) -> int:
    """Excel serial for a tracker date.

    Two spellings reach here: `Email/JIRA Date` is dd-mmm-yyyy, while `Month` is
    "Sep 2026" in the CSV and the first of that month as a serial on the sheet.
    """
    for fmt in ("%d-%b-%Y", "%b %Y"):
        try:
            return (datetime.strptime(value, fmt) - EPOCH).days
        except ValueError:
            continue
    raise SystemExit(f"unparseable date {value!r}; expected dd-mmm-yyyy or 'Mon YYYY'")


def derive(record: dict) -> dict:
    """Fill the columns that follow from the ones a human actually types."""
    record = {k: ("" if v is None else v) for k, v in record.items()}
    date = datetime.strptime(str(record["Email/JIRA Date"]).strip(), "%d-%b-%Y")
    record["Email/JIRA Date"] = date.strftime("%d-%b-%Y")
    record.setdefault("Month", "")
    record["Month"] = record["Month"] or date.strftime("%b %Y")
    record["Reporting Month"] = record.get("Reporting Month") or date.strftime("%b %Y")
    record["Month_Sort"] = record.get("Month_Sort") or date.month
    if not str(record.get("Number of Customers", "")).strip():
        record["Number of Customers"] = len(
            [p for p in str(record["Customer"]).split("/") if p.strip()])
    if not str(record.get("Routed To", "")).strip():
        # Derived default; a human override is expected and nothing recomputes it.
        record["Routed To"] = ("Product & Platform" if record.get("Root Cause") == "Product"
                               else "EventWatch Ops - Nitin Rindhe")
    return record


def csv_line(record: dict, columns: list[str]) -> str:
    buf = io.StringIO()
    # QUOTE_MINIMAL with \r\n suppressed matches how every existing line is written,
    # so the diff shows one added line and nothing else.
    writer = csv.writer(buf, lineterminator="")
    writer.writerow([str(record.get(c, "")) for c in columns])
    return buf.getvalue()


def sheet_row(record: dict, header: dict[str, str], row_no: int) -> str:
    cells = []
    for column, letter in header.items():
        value = str(record.get(column, "")).strip()
        ref = f"{letter}{row_no}"
        if column in NUMERIC:
            style = NUMERIC[column]
            if not value:
                cells.append(f'<c r="{ref}" s="{style}" t="n" />')
            elif column in ("Month", "Email/JIRA Date"):
                cells.append(f'<c r="{ref}" s="{style}" t="n"><v>{serial(value)}</v></c>')
            else:
                cells.append(f'<c r="{ref}" s="{style}" t="n"><v>{value}</v></c>')
            continue
        style = STYLES.get(column, DEFAULT_STYLE)
        if not value:
            cells.append(f'<c r="{ref}" s="{style}" t="n" />')
        else:
            cells.append(f'<c r="{ref}" s="{style}" t="inlineStr"><is><t>{escape(value)}</t></is></c>')
    return f'<row r="{row_no}">' + "".join(cells) + "</row>"


def append(record: dict, csv_path: Path, xlsx_path: Path, dry_run: bool = False) -> str:
    text = csv_path.read_text(encoding="utf-8")
    columns = next(csv.reader([text.split("\n", 1)[0]]))
    missing = [c for c in REQUIRED if not str(record.get(c, "")).strip()]
    if missing:
        raise SystemExit(f"refusing to append: missing required field(s) {missing}")
    unknown = [k for k in record if k not in columns]
    if unknown:
        raise SystemExit(f"refusing to append: {unknown} are not tracker columns")

    record = derive(record)

    sheet = zipfile.ZipFile(xlsx_path).read(DATA_SHEET).decode("utf-8")
    # The sheet's own header row decides column order -- never the CSV's, and never a
    # hardcoded list. This is the mistake that put a Jira Key in the wrong column.
    header: dict[str, str] = {}
    for m in re.finditer(r'<c r="([A-Z]+)1"[^>]*>(?:<is>)?<t>(.*?)</t>', sheet):
        header[m.group(2).strip()] = m.group(1)
    absent = [c for c in columns if c not in header]
    if absent:
        raise SystemExit(f"Data sheet has no column for {absent}")

    last = max(int(n) for n in re.findall(r'<row r="(\d+)"', sheet))
    new_row = last + 1
    sheet = sheet.replace("</sheetData>", sheet_row(record, header, new_row) + "</sheetData>", 1)
    dim = re.search(r'<dimension ref="(A1:[A-Z]+)(\d+)" />', sheet)
    if dim:
        sheet = sheet.replace(dim.group(0), f'<dimension ref="{dim.group(1)}{new_row}" />', 1)

    table = zipfile.ZipFile(xlsx_path).read("xl/tables/table1.xml").decode("utf-8")
    ref = re.search(r'(<table[^>]*\sref="A1:[A-Z]+)(\d+)(")', table)
    if not ref or int(ref.group(2)) != last:
        raise SystemExit("ComplaintTracker ref does not end at the sheet's last row; "
                         "run validate.py and fix that before appending")
    table = table[:ref.start()] + f"{ref.group(1)}{new_row}{ref.group(3)}" + table[ref.end():]

    line = csv_line(record, columns)
    summary = (f"row {new_row}: {record['Email/JIRA Date']} | {record['Customer']} | "
               f"{record.get('Jira Key') or 'no key'} | {record['Event/Bulletin Title'][:60]}")
    if dry_run:
        return f"would append {summary}\n  csv: {line[:160]}"

    csv_path.write_text(text.rstrip("\n") + "\n" + line + "\n", encoding="utf-8")
    src = zipfile.ZipFile(xlsx_path)
    tmp = xlsx_path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == DATA_SHEET:
                data = sheet.encode("utf-8")
            elif item.filename == "xl/tables/table1.xml":
                data = table.encode("utf-8")
            out.writestr(item, data)
    src.close()
    shutil.move(tmp, xlsx_path)
    return (f"appended {summary}\n"
            f"  next: python3 scripts/refresh_caches.py && python3 scripts/validate.py")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", required=True, help="path to a JSON object, or - for stdin")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.json == "-" else Path(args.json).read_text(encoding="utf-8")
    payload = json.loads(raw)
    records = payload if isinstance(payload, list) else [payload]
    for record in records:
        print(append(record, args.csv, args.xlsx, args.dry_run))
    return 0


if __name__ == "__main__":
    sys.exit(main())
