#!/usr/bin/env python3
"""Rewrite the workbook's cached values so they match the tracker.

Excel recalculates this workbook on open (`fullCalcOnLoad`), so the caches are not
what Excel uses -- but they are what everything else uses: GitHub's xlsx preview, a
Google Sheets or LibreOffice import, `openpyxl(data_only=True)`, a Finder preview.
Left alone they drift from the data every time rows are appended, and they had:
four of six charts and both dynamic-array spills were showing the pre-EAO 80-row
figures against a 93-row tracker.

What gets refreshed, all derived from the CSV via dashboard_calc -- no table layout,
range or label is hardcoded here:
  * every chart series' <numCache>/<strCache>
  * both dynamic-array spill regions on the Dashboard, including the array `ref`
    when the array has grown (Event Type gains a row per new event type)

This patches zip members as text. It never uses openpyxl's load/save, which would
strip xl/metadata.xml and the cm= markers the spills depend on (see CLAUDE.md).

  python3 scripts/refresh_caches.py            # rewrite in place
  python3 scripts/refresh_caches.py --dry-run  # report drift, change nothing
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dashboard_calc import DashboardCalc, Sheet, col_to_num, expand_range, load, split_ref  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO / "customer_tracker.csv"
DEFAULT_XLSX = REPO / "EventWatch_Customer_Complaints_2026.xlsx"
SHEET = "xl/worksheets/sheet2.xml"


def esc(v) -> str:
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def num(v) -> str:
    f = float(v)
    return str(int(f)) if f == int(f) else repr(f)


def cell_pattern(ref: str) -> re.Pattern:
    return re.compile(r'<c r="%s"[^>]*?(?:/>|>.*?</c>)' % ref, re.S)


def style_of(xml: str, ref: str) -> str | None:
    m = cell_pattern(ref).search(xml)
    if not m:
        return None
    s = re.search(r'\ss="(\d+)"', m.group(0))
    return s.group(1) if s else None


def write_cell(xml: str, ref: str, value, style: str | None, keep_formula: bool) -> str:
    """Replace one cell, preserving its array formula and cm= marker when it is an anchor."""
    m = cell_pattern(ref).search(xml)
    if not m:
        raise KeyError(f"{ref} is not present in the sheet; refusing to invent a cell")
    old = m.group(0)
    head = ""
    if keep_formula:
        fm = re.search(r"<f[^>]*>.*?</f>", old, re.S)
        head = fm.group(0) if fm else ""
    cm = ' cm="1"' if 'cm="1"' in old else ""
    sattr = f' s="{style}"' if style else ""
    if isinstance(value, str):
        body = f"{head}<is><t>{esc(value)}</t></is>" if not head else f"{head}<v>{esc(value)}</v>"
        tattr = ' t="str"' if head else ' t="inlineStr"'
    elif value is None or value == "":
        body, tattr = head, ' t="n"'
    else:
        body, tattr = f"{head}<v>{num(value)}</v>", ' t="n"'
    new = f'<c r="{ref}"{sattr}{tattr}{cm}>{body}</c>' if body else f'<c r="{ref}"{sattr}{tattr}{cm} />'
    return xml[: m.start()] + new + xml[m.end():]


def refresh_spills(xml: str, calc: DashboardCalc, report: list[str], dry: bool) -> str:
    """Rewrite each dynamic array's spilled cells, and its ref when the array grew.

    A block can be built from several array formulas side by side -- Top Customers is a
    one-column TAKE() in A64, an ANCHORARRAY count in B64 and a share in C64 -- so each
    anchor is refreshed against its own declared width, and only its row count follows
    the data.
    """
    for anchor, span, grid in calc.array_regions():
        acol, arow = split_ref(anchor)
        old_ref = calc.sheet.array_ref[anchor]
        old_last = split_ref(old_ref.split(":")[-1])[1]
        rows = len(grid)
        new_last = arow + rows - 1
        new_ref = f"{acol}{arow}:{chr(64 + col_to_num(acol) + span - 1)}{new_last}"

        # Styles come from the block as it stands: its header row, its body rows, and --
        # only where the array itself ends in a Total row -- whatever that total row
        # wears today, so the banding follows the array instead of staying behind.
        has_total = str(grid[-1][0]).strip().lower() == "total"

        def sty(row: int, c: int) -> str | None:
            return style_of(xml, f"{chr(64 + col_to_num(acol) + c)}{row}")

        first = [sty(arow, c) for c in range(span)]
        body = [sty(arow + 1, c) for c in range(span)]
        total = [sty(old_last, c) for c in range(span)] if has_total else body
        blank = [sty(old_last + 1, c) for c in range(span)]

        if old_ref != new_ref:
            report.append(f"{anchor}: array ref {old_ref} -> {new_ref} ({rows} rows)")
            if not dry:
                m = cell_pattern(anchor).search(xml)
                xml = xml[: m.start()] + m.group(0).replace(f'ref="{old_ref}"', f'ref="{new_ref}"') + xml[m.end():]

        changed = 0
        for r in range(rows):
            for c in range(span):
                ref = f"{chr(64 + col_to_num(acol) + c)}{arow + r}"
                want = grid[r][c]
                style = first[c] if r == 0 else (total[c] if (has_total and r == rows - 1) else body[c])
                got = Sheet(cell_pattern(ref).search(xml).group(0)).text.get(ref)
                if got != (want if isinstance(want, str) else num(want)):
                    changed += 1
                if not dry:
                    xml = write_cell(xml, ref, want, style, keep_formula=(ref == anchor))
        for r in range(new_last + 1, old_last + 1):  # ground the array used to cover
            for c in range(span):
                ref = f"{chr(64 + col_to_num(acol) + c)}{r}"
                report.append(f"{ref}: to be cleared, outside the new spill")
                if not dry:
                    xml = write_cell(xml, ref, None, blank[c], keep_formula=False)
        if changed:
            report.append(f"{anchor}: {changed} of {rows * span} spilled value(s) out of date")
    return xml


def refresh_chart(xml: str, calc: DashboardCalc, name: str, report: list[str], dry: bool) -> str:
    """Rewrite every series cache in one chart part from the ranges it already binds."""
    out, pos = [], 0
    for m in re.finditer(r"<f>([^<]+)</f>(\s*)<(numCache|strCache)>(.*?)</\3>", xml, re.S):
        rng, gap, kind, inner = m.group(1), m.group(2), m.group(3), m.group(4)
        ref = rng.split("!", 1)[1].replace("$", "")
        values = calc.range_values(ref)
        got = re.findall(r'<pt idx="\d+"[^>]*>\s*<v>(.*?)</v>\s*</pt>', inner, re.S)
        want = [esc(v) if kind == "strCache" else num(v) for v in values]
        if got == want:
            continue
        report.append(f"{name} {rng}: {got} -> {want}")
        if dry:
            continue
        fmt = re.search(r"<formatCode>.*?</formatCode>", inner, re.S)
        pts = "".join(f'<pt idx="{i}"><v>{v}</v></pt>' for i, v in enumerate(want))
        rebuilt = (f"<f>{rng}</f>{gap}<{kind}>{fmt.group(0) if fmt else ''}"
                   f'<ptCount val="{len(want)}" />{pts}</{kind}>')
        out.append(xml[pos:m.start()] + rebuilt)
        pos = m.end()
    out.append(xml[pos:])
    return "".join(out)


def rewrite(csv_path: Path, xlsx_path: Path, dry: bool) -> tuple[list[str], list]:
    """Recompute every cache; return what drifted and the patched zip members.

    With dry=True nothing is modified, so `validate.py` can use this as an assertion
    that the stored caches already agree with the tracker.
    """
    calc = load(csv_path, xlsx_path)
    report: list[str] = []
    with zipfile.ZipFile(xlsx_path) as z:
        blob = {i.filename: z.read(i.filename) for i in z.infolist()}
        infos = list(z.infolist())
    # Note: growing a hand-listed block automatically is NOT done here. The source
    # tables share rows -- row 53 carries April's serial in column A, the Root Cause
    # Total in E, and a Fix Status value in I -- so inserting a row for one block
    # rewrites cells belonging to the others. An attempt at it silently replaced May's
    # month serial with a duplicate of April's. `validate.py`'s enum_coverage reports a
    # new value and the row is added by hand, against a block that does not share rows.
    blob[SHEET] = refresh_spills(blob[SHEET].decode("utf-8"), calc, report, dry).encode("utf-8")
    for n in list(blob):
        if re.match(r"xl/charts/chart\d+\.xml$", n):
            blob[n] = refresh_chart(blob[n].decode("utf-8"), calc, Path(n).name,
                                    report, dry).encode("utf-8")
    return report, [(i, blob[i.filename]) for i in infos]


def audit(csv_path: Path, xlsx_path: Path) -> list[str]:
    """Everything that no longer matches the tracker. Empty means the workbook is current."""
    return rewrite(csv_path, xlsx_path, dry=True)[0]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    report, patched = rewrite(args.csv, args.xlsx, args.dry_run)
    members = patched

    for line in report:
        print(f"  · {line}")
    if not report:
        print("  · every cached value already matches the tracker")
        return 0
    if args.dry_run:
        print(f"\n{len(report)} change(s) needed; nothing written (--dry-run).")
        return 1

    tmp = args.xlsx.with_suffix(".xlsx.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for info, data in patched:
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type, zi.external_attr = info.compress_type, info.external_attr
            zo.writestr(zi, data)
    with zipfile.ZipFile(tmp) as check:
        if check.testzip() or len(check.namelist()) != len(members):
            print("FAIL — rewritten workbook is not intact; leaving the original in place")
            tmp.unlink()
            return 1
    shutil.move(tmp, args.xlsx)
    print(f"\n{len(report)} change(s) written to {args.xlsx.name}. Run scripts/validate.py next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
