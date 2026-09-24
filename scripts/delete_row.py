#!/usr/bin/env python3
"""Remove records from the tracker: CSV and workbook Data sheet, in one step.

The third of the trio with `append_row.py` and `update_row.py`, and the one that was
missing when it was first needed. A row logged in good faith turns out not to be a
record at all -- a customer's follow-up question on a query already in the tracker is
part of that query, not a second incident -- and taking it back out by hand is worse
than putting it in. Deleting from the Data sheet means renumbering every `<row r>` and
every `<c r>` below the gap, shrinking the sheet `dimension` and shrinking
`ComplaintTracker`'s ref, which is the same ref that silently undercounts every
Dashboard COUNTIFS when it disagrees with the data.

Guards match `update_row.py`: a `match` that selects anything but exactly one row
refuses, every CSV line is re-serialised and compared to itself before anything is
written, and each sheet row is verified against its CSV row's key columns first. All
deletions are resolved against the original row numbers before any of them is applied,
so deleting two rows at once cannot have the first shift the second out from under it.

It deliberately does not refresh caches: run refresh_caches.py then validate.py after.

Usage:
  python3 scripts/delete_row.py --json removals.json
  python3 scripts/delete_row.py --json removals.json --dry-run

`removals.json` is a list of {"match": {column: exact value, ...}}, optionally with
"why" for the printed report.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO / "customer_tracker.csv"
DEFAULT_XLSX = REPO / "EventWatch_Customer_Complaints_2026.xlsx"
DATA_SHEET = "xl/worksheets/sheet1.xml"
TABLE = "xl/tables/table1.xml"

sys.path.insert(0, str(Path(__file__).resolve().parent))
from update_row import (  # noqa: E402  - one definition of the guards and the sheet's shape
    VERIFY, cell_text, find, read_csv, sheet_header,
)
from sort_tracker import ROW, renumber, split_rows  # noqa: E402


def apply(removals: list[dict], csv_path: Path, xlsx_path: Path, dry_run: bool) -> list[str]:
    columns, lines, rows, tail = read_csv(csv_path)
    src = zipfile.ZipFile(xlsx_path)
    sheet = src.read(DATA_SHEET).decode("utf-8")
    table = src.read(TABLE).decode("utf-8")
    header = sheet_header(sheet)
    absent = [c for c in columns if c not in header]
    if absent:
        raise SystemExit(f"Data sheet has no column for {absent}")

    head, sheet_rows, sheet_tail = split_rows(sheet)
    by_r = {r: (attrs, body) for r, attrs, body in sheet_rows}
    last = max(by_r)

    report, doomed = [], []
    for removal in removals:
        match = removal.get("match")
        if not match:
            raise SystemExit("each removal needs a 'match'")
        index = find(rows, columns, match)
        row_no = index + 2  # CSV data line 1 is sheet row 2; parity keeps them aligned
        if row_no in doomed:
            raise SystemExit(f"row {row_no} named twice")
        if row_no not in by_r:
            raise SystemExit(f"Data sheet has no row {row_no}")
        attrs, body = by_r[row_no]
        for column in VERIFY:
            want = rows[index][columns.index(column)].strip()
            got = cell_text(f'<row r="{row_no}"{attrs}>{body}</row>', header[column], row_no)
            if want != got:
                raise SystemExit(
                    f"row {row_no} is not the CSV's row {row_no}: {column} reads {got!r} "
                    f"on the sheet and {want!r} in the CSV. Run validate.py")
        doomed.append(row_no)
        key = rows[index][columns.index("Jira Key")] or "no key"
        title = rows[index][columns.index("Event/Bulletin Title")]
        why = f" ({removal['why']})" if removal.get("why") else ""
        report.append(f"row {row_no} ({key}): {title[:64]}{why}")

    if not doomed:
        return ["nothing matched; nothing to do"]

    # Resolve every target against the ORIGINAL numbering first, then rebuild once.
    keep = [(r, by_r[r]) for r, _, _ in sheet_rows if r not in doomed]
    rebuilt = []
    for new_r, (_, (attrs, body)) in enumerate(keep, start=min(by_r)):
        rebuilt.append(f'<row r="{new_r}"{attrs}>{renumber(body, new_r)}</row>')
    sheet = head + "".join(rebuilt) + sheet_tail
    new_last = last - len(doomed)

    import re
    dim = re.search(r'<dimension ref="(A1:[A-Z]+)(\d+)"\s*/>', sheet)
    if dim:
        sheet = sheet.replace(dim.group(0), f'<dimension ref="{dim.group(1)}{new_last}" />', 1)
    ref = re.search(r'(<table[^>]*\sref="A1:[A-Z]+)(\d+)(")', table)
    if not ref or int(ref.group(2)) != last:
        raise SystemExit("ComplaintTracker ref does not end at the sheet's last row; "
                         "run validate.py and fix that before deleting")
    table = table[:ref.start()] + f"{ref.group(1)}{new_last}{ref.group(3)}" + table[ref.end():]

    report.append(f"{len(doomed)} record(s) removed; sheet now ends at row {new_last}")
    if dry_run:
        src.close()
        return ["(dry run, nothing written)"] + report

    for row_no in sorted(doomed, reverse=True):
        del lines[row_no - 1]
    csv_path.write_text("\n".join(lines) + tail, encoding="utf-8")

    tmp = xlsx_path.with_suffix(".xlsx.tmp")
    members = [(info, src.read(info.filename)) for info in src.infolist()]
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as out:
        for info, data in members:
            if info.filename == DATA_SHEET:
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
    report.append("next: python3 scripts/refresh_caches.py && python3 scripts/validate.py")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", required=True, help="path to a JSON list of removals, or - for stdin")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    raw = sys.stdin.read() if args.json == "-" else Path(args.json).read_text(encoding="utf-8")
    payload = json.loads(raw)
    for line in apply(payload if isinstance(payload, list) else [payload],
                      args.csv, args.xlsx, args.dry_run):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
