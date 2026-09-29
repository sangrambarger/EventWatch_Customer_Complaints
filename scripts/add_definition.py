#!/usr/bin/env python3
"""Add a term to the workbook's Definitions sheet, so a new taxonomy value is legal.

`validate.py`'s `enum_definitions` refuses a value in use that the Definitions sheet
does not document, which is the rule that caught six event types, four reason labels and
the `Pending` fix status all circulating undefined. So introducing a new `Event type`,
`Reason`, `Sub-type` or similar is two edits, not one: the value on the record, and its
row here. This does the second, which was the fiddly one -- a row appended to sheet3,
`DefinitionsTable`'s `ref` extended, and the sheet `dimension` extended, all three or the
workbook opens with the table short and the new row outside it.

Rows append at the bottom, out of section order, which is how rows 138 onward already sit
and is why nothing above them shifts. The style ids are read off the sheet's own last row
rather than hardcoded, so a row added here cannot be the one in the wrong font that
`validate.py`'s `styling` rule blocks.

Run `scripts/export_definitions.py` afterwards to regenerate `definitions.json`, then
`validate.py`, which fails if the committed JSON has drifted from the sheet.

Usage:
  python3 scripts/add_definition.py --json term.json
  python3 scripts/add_definition.py --json term.json --dry-run

Each entry is {"section", "term", "definition", "allowed", "source"}; `allowed` and
`source` may be omitted for an operational term that documents no column.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

REPO = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = REPO / "EventWatch_Customer_Complaints_2026.xlsx"
SHEET = "xl/worksheets/sheet3.xml"
TABLE = "xl/tables/table2.xml"
COLUMNS = ("section", "term", "definition", "allowed", "source")


def styles_of(row_xml: str) -> dict[str, str]:
    """The style id each column carries on the sheet's own last row."""
    found = {}
    for m in re.finditer(r'<c r="([A-E])\d+"\s+s="(\d+)"', row_xml):
        found[m.group(1)] = m.group(2)
    return found


def add(entries: list[dict], xlsx_path: Path, dry_run: bool) -> list[str]:
    src = zipfile.ZipFile(xlsx_path)
    sheet = src.read(SHEET).decode("utf-8")
    table = src.read(TABLE).decode("utf-8")

    rows = [(int(m.group(1)), m.group(0)) for m in re.finditer(r'<row r="(\d+)".*?</row>', sheet, re.S)]
    last_no, last_xml = rows[-1]
    styles = styles_of(last_xml)
    if set(styles) != set("ABCDE"):
        raise SystemExit(f"could not read a style for every column off row {last_no}")

    # Terms already on the sheet, so a second row for one cannot be added silently.
    known = {m.group(1).strip() for m in re.finditer(r'<c r="B\d+"[^>]*><is><t>(.*?)</t>', sheet)}

    report, additions = [], []
    for entry in entries:
        unknown = [k for k in entry if k not in COLUMNS]
        if unknown:
            raise SystemExit(f"{unknown} are not definition fields; expected {list(COLUMNS)}")
        for required in ("section", "term", "definition"):
            if not str(entry.get(required, "")).strip():
                raise SystemExit(f"refusing to add: {required!r} is empty")
        term = entry["term"].strip()
        if term in known:
            raise SystemExit(f"{term!r} already has a row on the Definitions sheet")
        known.add(term)
        additions.append(entry)
        report.append(f"{entry['section']} / {term}"
                      + (f"  [{entry.get('source')}]" if entry.get("source") else ""))

    if not additions:
        return ["nothing to add"]

    built = []
    for offset, entry in enumerate(additions, start=1):
        number = last_no + offset
        cells = []
        for letter, field in zip("ABCDE", COLUMNS):
            value = str(entry.get(field, "")).strip()
            ref = f"{letter}{number}"
            if not value:
                cells.append(f'<c r="{ref}" s="{styles[letter]}" t="n" />')
            else:
                cells.append(f'<c r="{ref}" s="{styles[letter]}" t="inlineStr">'
                             f"<is><t>{escape(value)}</t></is></c>")
        built.append(f'<row r="{number}" ht="30.75" customHeight="1">' + "".join(cells) + "</row>")
    new_last = last_no + len(additions)

    sheet = sheet.replace("</sheetData>", "".join(built) + "</sheetData>", 1)
    dim = re.search(r'<dimension ref="(A1:[A-Z]+)(\d+)"\s*/>', sheet)
    if not dim:
        raise SystemExit("Definitions sheet has no dimension to extend")
    sheet = sheet.replace(dim.group(0), f'<dimension ref="{dim.group(1)}{new_last}" />', 1)

    ref = re.search(r'(<table[^>]*\sref="A3:[A-Z]+)(\d+)(")', table)
    if not ref or int(ref.group(2)) != last_no:
        raise SystemExit(f"DefinitionsTable ends at row {ref.group(2) if ref else '?'} but the sheet "
                         f"ends at {last_no}; run validate.py and fix that first")
    table = table[:ref.start()] + f"{ref.group(1)}{new_last}{ref.group(3)}" + table[ref.end():]

    report.append(f"DefinitionsTable and sheet dimension extended to row {new_last}")
    if dry_run:
        src.close()
        return ["(dry run, nothing written)"] + report

    tmp = xlsx_path.with_suffix(".xlsx.tmp")
    members = [(info, src.read(info.filename)) for info in src.infolist()]
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for info, data in members:
            if info.filename == SHEET:
                data = sheet.encode("utf-8")
            elif info.filename == TABLE:
                data = table.encode("utf-8")
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type, zi.external_attr = info.compress_type, info.external_attr
            out.writestr(zi, data)
    with zipfile.ZipFile(tmp) as check:
        if check.testzip() or len(check.namelist()) != len(members):
            tmp.unlink()
            raise SystemExit("rewritten workbook is not intact; original left in place")
    src.close()
    shutil.move(tmp, xlsx_path)
    report.append("next: python3 scripts/export_definitions.py && python3 scripts/validate.py")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", required=True, help="path to a JSON list of terms, or - for stdin")
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.json == "-" else Path(args.json).read_text(encoding="utf-8")
    payload = json.loads(raw)
    for line in add(payload if isinstance(payload, list) else [payload], args.xlsx, args.dry_run):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
