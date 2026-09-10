#!/usr/bin/env python3
"""Prove each of validate.py's rules actually fires, by breaking the data on purpose.

A validator nobody has seen fail is a validator nobody should trust. Two of the checks
here were silently no-ops when first written, and one -- the mojibake pattern -- passed
clean for months over four corrupted cells it was meant to catch, because its regex
needed a letter beside the '?' and the real corruption had spaces on both sides.

Each case copies the CSV and workbook to a scratch directory, introduces one specific
fault, runs validate.py against the pair, and asserts that the expected rule blocks.
A case that passes clean is a rule that is not doing its job.

  python3 scripts/selftest.py          # all cases
  python3 scripts/selftest.py styling  # just the ones whose name matches
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CSV = REPO / "customer_tracker.csv"
XLSX = REPO / "EventWatch_Customer_Complaints_2026.xlsx"
DATA_SHEET = "xl/worksheets/sheet1.xml"
DASH_SHEET = "xl/worksheets/sheet2.xml"


def patch_zip(path: Path, member: str, fn) -> None:
    """Rewrite one member of the workbook in place, leaving every other byte alone."""
    with zipfile.ZipFile(path) as z:
        items = [(i, z.read(i.filename)) for i in z.infolist()]
    tmp = path.with_suffix(".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for info, data in items:
            if info.filename == member:
                data = fn(data.decode("utf-8")).encode("utf-8")
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type, zi.external_attr = info.compress_type, info.external_attr
            zo.writestr(zi, data)
    shutil.move(tmp, path)


def csv_lines(csv: Path) -> list[str]:
    return csv.read_text(encoding="utf-8").split("\n")


def write_lines(csv: Path, lines: list[str]) -> None:
    csv.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------- the faults

def break_mojibake_adjacent(csv: Path, xlsx: Path) -> None:
    csv.write_text(csv.read_text(encoding="utf-8").replace("Fürth", "F?rth"), encoding="utf-8")


def break_mojibake_lone(csv: Path, xlsx: Path) -> None:
    """The shape that shipped: an arrow lost between two words, spaces either side."""
    csv.write_text(csv.read_text(encoding="utf-8").replace(" → ", " ? ", 1), encoding="utf-8")


def break_row_order(csv: Path, xlsx: Path) -> None:
    """Move a record across a month boundary, the way a mis-ordered append does."""
    lines = csv_lines(csv)
    lines.insert(2, lines.pop(60))
    write_lines(csv, lines)


def break_required_fields(csv: Path, xlsx: Path) -> None:
    lines = csv_lines(csv)
    parts = lines[5].split(",")
    parts[4] = ""  # Customer
    lines[5] = ",".join(parts)
    write_lines(csv, lines)


def break_jira_keys(csv: Path, xlsx: Path) -> None:
    csv.write_text(csv.read_text(encoding="utf-8").replace("EAO-11", "EAO_11", 1), encoding="utf-8")


def break_enum_coverage(csv: Path, xlsx: Path) -> None:
    """A fix status the Dashboard's fixed table does not list drops out of its total."""
    csv.write_text(csv.read_text(encoding="utf-8").replace(",Fixed,", ",Escalated,", 1), encoding="utf-8")


def break_month_coverage(csv: Path, xlsx: Path) -> None:
    """A month past the end of the trend block. It runs Jan-Dec 2026 now, so the fault
    has to reach into the next year to be a fault at all."""
    text = csv.read_text(encoding="utf-8").replace("Sep 2026,03-Sep-2026", "Jan 2027,03-Jan-2027", 1)
    csv.write_text(text, encoding="utf-8")


def break_parity(csv: Path, xlsx: Path) -> None:
    """Diverge one CSV cell from the workbook without touching anything else."""
    patch_zip(xlsx, DATA_SHEET, lambda x: x.replace("<t>Caterpillar</t>", "<t>Caterpillar Inc</t>", 1))


def break_dynamic_arrays(csv: Path, xlsx: Path) -> None:
    patch_zip(xlsx, DASH_SHEET, lambda x: x.replace(' cm="1"', "", 1))


def break_caches(csv: Path, xlsx: Path) -> None:
    def bend(x):
        rng = re.search(r"<f>Dashboard!\$B\$\d+:\$B\$\d+</f>", x).group(0)
        # The range element stays inside the capture group. Left outside it, the
        # substitution drops the whole <f> ref and the chart loses the series --
        # which is not the fault this case is meant to introduce.
        return re.sub("(" + re.escape(rng) + r'<numCache>.*?<pt idx="0"><v>)\d+',
                      r"\g<1>99", x, count=1, flags=re.S)
    patch_zip(xlsx, "xl/charts/chart1.xml", bend)


def break_spill_space(csv: Path, xlsx: Path) -> None:
    """Shrink the Event Type array's ref and park a value in the row it must grow into.

    The ref is read out of the file rather than written in: hardcoding it here means the
    fault silently stops being a fault the next time the array grows, and the case then
    passes for the wrong reason.
    """
    def bend(x):
        # Find the widest array ref on the sheet rather than naming its anchor: the
        # anchor moved from I64 to I67 when the monthly block was extended, and a
        # pinned one stops being a fault instead of failing.
        best = max(re.finditer(r'<f t="array" ref="([A-Z]+)(\d+):([A-Z]+)(\d+)"', x),
                   key=lambda m: int(m.group(4)) - int(m.group(2)))
        col, first, last = best.group(1), int(best.group(2)), int(best.group(4))
        short = last - 7
        x = x.replace(best.group(0), f'<f t="array" ref="{col}{first}:{best.group(3)}{short}"', 1)
        return re.sub(r'<c r="%s%d"[^>]*?(?:/>|>.*?</c>)' % (col, short + 1),
                      f'<c r="{col}{short + 1}" t="inlineStr"><is><t>in the way</t></is></c>',
                      x, count=1, flags=re.S)
    patch_zip(xlsx, DASH_SHEET, bend)


def break_table_ref(csv: Path, xlsx: Path) -> None:
    """A table ref left short after an append: every Dashboard COUNTIFS undercounts.

    Derived from the current ref for the same reason as above -- this case was a silent
    no-op for one commit because it was pinned to A1:W94 after the table reached W95.
    """
    def bend(x):
        m = re.search(r'ref="(A1:[A-Z]+)(\d+)"', x)
        return x.replace(m.group(0), f'ref="{m.group(1)}{int(m.group(2)) - 4}"', 1)
    patch_zip(xlsx, "xl/tables/table1.xml", bend)


def break_styling(csv: Path, xlsx: Path) -> None:
    """Rows appended in the wrong font, the defect that went unnoticed for two runs."""
    def bend(x):
        m = re.search(r'<row r="50".*?</row>', x, re.S)
        return x[: m.start()] + re.sub(r'\ss="\d+"', ' s="118"', m.group(0)) + x[m.end():]
    patch_zip(xlsx, DATA_SHEET, bend)


def break_duplicates(csv: Path, xlsx: Path) -> None:
    """Log the same complaint twice, the way a Jira path and an email path both would."""
    lines = csv_lines(csv)
    lines.insert(40, lines[40])
    write_lines(csv, lines)


def break_definitions(csv: Path, xlsx: Path) -> None:
    """A tracker column with no row in the workbook's data dictionary."""
    patch_zip(xlsx, "xl/worksheets/sheet3.xml",
              lambda x: x.replace("<t>Jira Key</t>", "<t>Ticket Ref</t>"))


def break_definitions_table_ref(csv: Path, xlsx: Path) -> None:
    """DefinitionsTable left short after an append, hiding the new rows from the table."""
    patch_zip(xlsx, "xl/tables/table2.xml",
              lambda x: re.sub(r'(<table[^>]*\sref="A3:E)(\d+)(")',
                               lambda m: f"{m.group(1)}{int(m.group(2)) - 4}{m.group(3)}", x, count=1))


def break_definitions_export(csv: Path, xlsx: Path) -> None:
    """A Definitions sheet edit that never made it into the committed definitions.json.

    The app renders that file, not the sheet, so a sheet edit nobody exported is a
    glossary that reads correctly in Excel and wrongly in the dashboard -- the drift
    the hardcoded dict used to have, now catchable.
    """
    patch_zip(xlsx, "xl/worksheets/sheet3.xml",
              lambda x: x.replace("Root Cause Analysis;", "Root Cause Assessment;"))


def break_enum_definitions(csv: Path, xlsx: Path) -> None:
    """A value in use across the tracker whose Definitions row was renamed away.

    'High' is a Severity used by dozens of records; rename the taxonomy row and the
    value is in circulation with nothing defining it -- the exact shape of the six
    undocumented event types this rule was written for.
    """
    patch_zip(xlsx, "xl/worksheets/sheet3.xml",
              lambda x: x.replace("<t>High</t>", "<t>Critical</t>"))


def break_formula_columns(csv: Path, xlsx: Path) -> None:
    """A column renamed out from under the Management Readout's formulas."""
    patch_zip(xlsx, "xl/worksheets/sheet4.xml",
              lambda x: x.replace("ComplaintTracker[Severity]", "ComplaintTracker[Impact]"))


CASES: list[tuple[str, str, object]] = [
    ("mojibake_adjacent", "mojibake", break_mojibake_adjacent),
    ("mojibake_lone_arrow", "mojibake", break_mojibake_lone),
    ("row_order", "row_order", break_row_order),
    ("required_fields", "required_fields", break_required_fields),
    ("jira_keys", "jira_keys", break_jira_keys),
    ("enum_coverage", "enum_coverage", break_enum_coverage),
    ("month_coverage", "month_coverage", break_month_coverage),
    ("parity", "parity", break_parity),
    ("dynamic_arrays", "dynamic_arrays", break_dynamic_arrays),
    ("caches", "caches", break_caches),
    ("spill_space", "spill_space", break_spill_space),
    ("table_ref", "table_ref", break_table_ref),
    ("styling", "styling", break_styling),
    ("duplicates", "duplicates", break_duplicates),
    ("definitions_column", "definitions", break_definitions),
    ("definitions_table_ref", "definitions", break_definitions_table_ref),
    ("enum_definitions", "enum_definitions", break_enum_definitions),
    ("definitions_export", "definitions_export", break_definitions_export),
    ("formula_columns", "formula_columns", break_formula_columns),
]


def run_validate(csv: Path, xlsx: Path) -> tuple[int, str]:
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "validate.py"),
                           "--csv", str(csv), "--xlsx", str(xlsx)],
                          capture_output=True, text=True)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("filter", nargs="?", help="only run cases whose name contains this")
    args = ap.parse_args()

    code, out = run_validate(CSV, XLSX)
    if code != 0:
        print("FAIL — the real data does not pass validate.py, so nothing below means anything:")
        print(out)
        return 1
    print("baseline: the real data passes validate.py\n")

    cases = [c for c in CASES if not args.filter or args.filter in c[0]]
    failures = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, rule, fault in cases:
            csv, xlsx = Path(tmp) / "t.csv", Path(tmp) / "t.xlsx"
            shutil.copy(CSV, csv)
            shutil.copy(XLSX, xlsx)
            fault(csv, xlsx)
            code, out = run_validate(csv, xlsx)
            caught = code != 0 and f"✗ {rule}:" in out
            print(f"{name:22s} -> {'caught by ' + rule if caught else 'NOT CAUGHT'}")
            if not caught:
                failures.append((name, rule, out))

    if failures:
        print(f"\nFAIL — {len(failures)} rule(s) did not fire on a fault they exist to catch:")
        for name, rule, out in failures:
            print(f"\n  ✗ {name} (expected {rule}):")
            print("    " + "\n    ".join(out.strip().splitlines()[-6:]))
        return 1
    print(f"\nPASS — all {len(cases)} rule(s) blocked the fault they exist to catch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
