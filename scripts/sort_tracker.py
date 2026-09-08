#!/usr/bin/env python3
"""Put tracker records back in date order, in the CSV and the workbook together.

Rows get appended in the order tickets are triaged, not the order they happened, so
the tracker drifts out of chronological order -- `validate.py`'s `row_order` warning
is what notices. This sorts a chosen set of records by their Email/JIRA Date and
writes both files, keeping the two in the lockstep the rest of the tooling assumes.

Records are sorted *among the positions they already occupy*, so selecting a subset
never disturbs anything outside it: pick Jul and Aug and the January rows do not move,
even if the two months are interleaved with each other.

The sort is stable, so same-day records keep their existing relative order -- which is
the only ordering information there is once the date ties.

  python3 scripts/sort_tracker.py Jul Aug   # sort July and August records
  python3 scripts/sort_tracker.py --all     # sort the whole tracker
  python3 scripts/sort_tracker.py --all --dry-run

Two things it deliberately preserves, because they carry human intent:
  * a row's highlight fill and any per-cell formatting travel with the record
  * the CSV is rewritten line-by-line, not re-serialised, so quoting is untouched and
    the diff shows only the rows that actually moved

It does normalise one thing: rows appended with a different font than the rest of the
sheet are restyled to match. Left alone, sorting scatters them through the table and
turns a tidy block of odd-looking rows at the bottom into odd-looking rows throughout.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEFAULT_CSV = REPO / "customer_tracker.csv"
DEFAULT_XLSX = REPO / "EventWatch_Customer_Complaints_2026.xlsx"
DATA_SHEET = "xl/worksheets/sheet1.xml"
EXCEL_EPOCH = date(1899, 12, 30)
DATE_COL = "Email/JIRA Date"
MONTH_COL = "Month"


def parse_date(text: str) -> date:
    return date(*map(int, __import__("datetime").datetime.strptime(text.strip(), "%d-%b-%Y").timetuple()[:3]))


# ---------------------------------------------------------------- CSV

def read_csv_lines(path: Path) -> tuple[str, list[str], list[str]]:
    """Header line, data lines, and the fields of the header -- text kept verbatim."""
    text = path.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.split(newline)
    trailing = lines.pop() if lines and lines[-1] == "" else None
    if trailing is None:
        raise ValueError(f"{path} does not end with a newline; refusing to guess")
    return newline, lines[0].split(","), lines[1:]


def field(line: str, index: int) -> str:
    """One field out of a CSV line, honouring quotes. Only used for Month and Date."""
    out, cur, quoted, n = [], [], False, 0
    for ch in line:
        if ch == '"':
            quoted = not quoted
        elif ch == "," and not quoted:
            out.append("".join(cur))
            cur = []
            n += 1
            if n > index:
                break
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out[index]


# ---------------------------------------------------------------- workbook

CELL = re.compile(r'<c r="([A-Z]+)(\d+)"((?:[^>](?!<c ))*?)(?:/>|>(.*?)</c>)', re.S)
ROW = re.compile(r'<row r="(\d+)"([^>]*)>(.*?)</row>', re.S)


def style_fonts(xlsx: zipfile.ZipFile) -> tuple[dict[str, str], dict[str, str]]:
    """style id -> fontId, and style id -> fillId, read out of cellXfs."""
    styles = xlsx.read("xl/styles.xml").decode("utf-8")
    xfs = re.search(r"<cellXfs[^>]*>(.*?)</cellXfs>", styles, re.S).group(1)
    fonts, fills = {}, {}
    for i, xf in enumerate(re.findall(r"<xf\b.*?(?:/>|</xf>)", xfs, re.S)):
        fonts[str(i)] = (re.search(r'fontId="(\d+)"', xf) or re.match("", "")).group(1) if 'fontId="' in xf else "0"
        fills[str(i)] = re.search(r'fillId="(\d+)"', xf).group(1) if 'fillId="' in xf else "0"
    return fonts, fills


def split_rows(xml: str) -> tuple[str, list[tuple[int, str, str]], str]:
    """Everything before the first <row>, the rows themselves, and everything after."""
    rows = [(int(m.group(1)), m.group(2), m.group(3)) for m in ROW.finditer(xml)]
    first, last = next(ROW.finditer(xml)), None
    for last in ROW.finditer(xml):
        pass
    return xml[: first.start()], rows, xml[last.end():]


def renumber(body: str, new_row: int) -> str:
    return CELL.sub(lambda m: m.group(0).replace(f'r="{m.group(1)}{m.group(2)}"',
                                                 f'r="{m.group(1)}{new_row}"', 1), body)


def restyle(body: str, canon: dict[str, str], fallback: str, fonts, fills, main_font: str) -> tuple[str, int]:
    """Bring off-font and unstyled cells onto the column's canonical style.

    A cell carrying a fill is a deliberate human highlight and is never touched.
    """
    changed = 0

    def one(m):
        nonlocal changed
        col, text = m.group(1), m.group(0)
        s = re.search(r'\ss="(\d+)"', m.group(3))
        current = s.group(1) if s else None
        if current and fills.get(current, "0") != "0":
            return text
        if current and fonts.get(current, "0") == main_font:
            return text
        want = canon.get(col, fallback)
        if want == current:
            return text
        changed += 1
        return (re.sub(r'\ss="\d+"', f' s="{want}"', text, count=1) if current
                else text.replace(f'r="{col}{m.group(2)}"', f'r="{col}{m.group(2)}" s="{want}"', 1))

    return CELL.sub(one, body), changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("months", nargs="*", help='month tokens to sort, e.g. Jul Aug (matched against the Month column)')
    ap.add_argument("--all", action="store_true", help="sort every record")
    ap.add_argument("--csv", type=Path, default=DEFAULT_CSV)
    ap.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.months and not args.all:
        ap.error("name at least one month, or pass --all")

    newline, header, lines = read_csv_lines(args.csv)
    month_i, date_i = header.index(MONTH_COL), header.index(DATE_COL)
    dates = [parse_date(field(ln, date_i)) for ln in lines]
    months = [field(ln, month_i).strip() for ln in lines]

    selected = [i for i in range(len(lines))
                if args.all or any(m.lower() in months[i].lower() for m in args.months)]
    if not selected:
        print(f"No records match {args.months}; nothing to do.")
        return 0
    order = sorted(selected, key=lambda i: dates[i])  # stable: ties keep their order
    moved = sum(1 for a, b in zip(selected, order) if a != b)

    print(f"{len(selected)} record(s) selected ({min(dates[i] for i in selected)} to "
          f"{max(dates[i] for i in selected)}); {moved} change position")
    for slot, src in zip(selected, order):
        if slot != src:
            print(f"  · row {slot + 2} <- row {src + 2}  {dates[src]}  {field(lines[src], month_i)}")
    # --- CSV: move whole lines, so quoting and spacing survive untouched.
    # The workbook pass runs even when nothing moves: it also normalises styling, and
    # that work is worth doing on its own.
    if moved and not args.dry_run:
        new_lines = list(lines)
        for slot, src in zip(selected, order):
            new_lines[slot] = lines[src]
        args.csv.write_text(newline.join([",".join(header)] + new_lines) + newline, encoding="utf-8")

    # --- workbook Data sheet: move whole rows, so highlights travel with the record
    with zipfile.ZipFile(args.xlsx) as z:
        members = [(i, z.read(i.filename)) for i in z.infolist()]
        fonts, fills = style_fonts(z)
    xml = next(d for i, d in members if i.filename == DATA_SHEET).decode("utf-8")
    head, rows, tail = split_rows(xml)
    by_r = {r: (attrs, body) for r, attrs, body in rows}  # every row, header included

    data_rows = [r for r in by_r if r >= 2]
    if len(data_rows) != len(lines):
        print(f"FAIL — the Data sheet has {len(data_rows)} record rows but the CSV has {len(lines)}")
        return 1

    # Which font do the records mostly use? Cells that disagree, or that carry no style
    # at all, were appended without matching the sheet; sorting would scatter them
    # through the table, so they are brought into line here -- cell by cell, so a
    # highlighted cell in an otherwise ordinary row keeps its highlight.
    tally: dict[str, int] = {}
    for r in data_rows:
        for m in CELL.finditer(by_r[r][1]):
            s = re.search(r'\ss="(\d+)"', m.group(3))
            f = fonts.get(s.group(1), "0") if s else "0"
            tally[f] = tally.get(f, 0) + 1
    main_font = max(tally, key=tally.get)

    canon: dict[str, str] = {}
    for r in sorted(data_rows):
        for m in CELL.finditer(by_r[r][1]):
            s = re.search(r'\ss="(\d+)"', m.group(3))
            if s and fonts.get(s.group(1)) == main_font and fills.get(s.group(1)) == "0":
                canon.setdefault(m.group(1), s.group(1))
    if not canon:
        print("FAIL — no reference styling found on the Data sheet")
        return 1
    # A column nobody has styled yet (Jira Key was appended bare) takes the style the
    # other text columns use rather than staying in the default font.
    fallback = max(set(canon.values()), key=list(canon.values()).count)

    touched, cells = [], 0
    for r in data_rows:
        body, n = restyle(by_r[r][1], canon, fallback, fonts, fills, main_font)
        if n:
            by_r[r] = (by_r[r][0], body)
            touched.append(r)
            cells += n
    if touched:
        print(f"\nrestyled {cells} cell(s) across {len(touched)} row(s) that did not match the "
              f"sheet's font (rows {touched[0]}-{touched[-1]})")

    if args.dry_run:
        print("\nNothing written (--dry-run).")
        return 1 if (moved or touched) else 0
    if not moved and not touched:
        return 0

    # Every row is rebuilt from by_r, not from the original list: restyling applies to
    # the whole sheet, and taking unselected rows from the original would throw it away.
    first_data = min(data_rows)
    source_for = {first_data + slot: first_data + src for slot, src in zip(selected, order)}
    rebuilt = []
    for r, _, _ in rows:
        attrs, body = by_r[source_for.get(r, r)]
        rebuilt.append(f'<row r="{r}"{attrs}>{renumber(body, r)}</row>')
    xml = head + "".join(rebuilt) + tail

    tmp = args.xlsx.with_suffix(".xlsx.tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zo:
        for info, data in members:
            if info.filename == DATA_SHEET:
                data = xml.encode("utf-8")
            zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
            zi.compress_type, zi.external_attr = info.compress_type, info.external_attr
            zo.writestr(zi, data)
    with zipfile.ZipFile(tmp) as check:
        if check.testzip() or len(check.namelist()) != len(members):
            tmp.unlink()
            print("FAIL — rewritten workbook is not intact; original left in place")
            return 1
    shutil.move(tmp, args.xlsx)
    print(f"\nWrote {args.csv.name} and {args.xlsx.name}. Run scripts/validate.py next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
