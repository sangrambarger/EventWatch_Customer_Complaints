#!/usr/bin/env python3
"""Recompute the Dashboard's source tables from the tracker, the way Excel would.

The workbook's Dashboard is entirely formula-driven: every source table under row 46
is a COUNTIF/COUNTIFS over the ComplaintTracker table, plus two dynamic arrays. Excel
recalculates all of it on open (`fullCalcOnLoad`), but the *cached* values -- the ones
stored in the sheet and in each chart's `<numCache>`/`<strCache>` -- are what a reader
sees in anything that does not recalculate: GitHub's xlsx preview, a Google Sheets
import, `openpyxl(data_only=True)`, a Quick Look thumbnail.

Those caches drift every time rows are appended. Rather than hand-patch chart XML and
hope, this module re-derives each cell's value from the CSV by reading the sheet's own
formula and evaluating it. Nothing about the table layout is hardcoded here: add a row
to the Fix Status table and its value comes back from the formula that row carries.

Used by `refresh_caches.py` (writes the values back) and `validate.py` (asserts the
stored caches already match).
"""
from __future__ import annotations

import re
import zipfile
from pathlib import Path

import pandas as pd

TABLE = "ComplaintTracker"
# A cell is either self-closing (<c r="H50" s="1" t="n" />) or has a body. The empty
# self-closing form has to be matched first, or a lazy body match runs past it and
# swallows the next real cell -- which silently loses every label on the sheet.
_CELL = re.compile(r'<c r="([A-Z]+\d+)"[^>]*?(?:/>|>(.*?)</c>)', re.S)


def col_to_num(col: str) -> int:
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


def split_ref(ref: str) -> tuple[str, int]:
    m = re.match(r"([A-Z]+)(\d+)$", ref)
    return m.group(1), int(m.group(2))


def expand_range(rng: str) -> list[str]:
    """'B50:B58' -> ['B50', ..., 'B58'] (single column or single row only)."""
    a, _, b = rng.partition(":")
    if not b:
        return [a]
    ca, ra = split_ref(a)
    cb, rb = split_ref(b)
    if ca == cb:
        return [f"{ca}{r}" for r in range(ra, rb + 1)]
    return [f"{chr(64 + c)}{ra}" for c in range(col_to_num(ca), col_to_num(cb) + 1)]


class Sheet:
    """The Dashboard's cells: literal values and formulas, straight out of the XML."""

    def __init__(self, xml: str):
        self.text: dict[str, str] = {}
        self.formula: dict[str, str] = {}
        self.array_ref: dict[str, str] = {}  # anchor -> the range the array spills over
        for m in _CELL.finditer(xml):
            ref, body = m.group(1), m.group(2) or ""
            f = re.search(r"<f([^>]*)>(.*?)</f>", body, re.S)
            if f:
                self.formula[ref] = _unescape(f.group(2))
                aref = re.search(r'ref="([^"]+)"', f.group(1))
                if 't="array"' in f.group(1) and aref:
                    self.array_ref[ref] = aref.group(1)
            t = re.search(r"<is>.*?<t[^>]*>(.*?)</t>", body, re.S) or re.search(r"<v>(.*?)</v>", body, re.S)
            if t:
                self.text[ref] = _unescape(t.group(1))


def _plain(f: str) -> str:
    """Strip the _xlfn/_xlws/_xlpm prefixes Excel writes for newer functions."""
    return f.replace("_xlfn._xlws.", "").replace("_xlfn.", "").replace("_xlpm.", "")


def _split_top(expr: str, op: str) -> list[str]:
    """Split on `op` only where it sits outside any parentheses or quoted string."""
    parts, depth, quoted, start = [], 0, False, 0
    for i, ch in enumerate(expr):
        if ch == '"':
            quoted = not quoted
        elif quoted:
            continue
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == op and depth == 0:
            parts.append(expr[start:i])
            start = i + 1
    parts.append(expr[start:])
    return parts


def _unescape(s: str) -> str:
    return s.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")


class DashboardCalc:
    """Evaluate Dashboard cells against the tracker.

    Supports exactly the formula vocabulary this workbook uses. Anything else raises,
    so a new formula shape fails loudly instead of being silently skipped.
    """

    def __init__(self, df: pd.DataFrame, sheet: Sheet):
        self.df = df.fillna("")
        self.sheet = sheet
        self._cache: dict[str, object] = {}
        self._arrays_cache: dict[str, list[list]] = {}

    # -- table column access ------------------------------------------------
    def column(self, name: str) -> pd.Series:
        if name not in self.df.columns:
            raise KeyError(f"{TABLE}[{name}] is not a tracker column")
        return self.df[name].astype(str).str.strip()

    def countifs(self, pairs: list[tuple[str, object]]) -> int:
        mask = pd.Series(True, index=self.df.index)
        for col, crit in pairs:
            mask &= self.column(col) == str(crit).strip()
        return int(mask.sum())

    # -- cell evaluation ----------------------------------------------------
    def value(self, ref: str):
        if ref in self._cache:
            return self._cache[ref]
        self._cache[ref] = out = self._evaluate(ref)
        return out

    def _evaluate(self, ref: str):
        # A cell inside a dynamic array's spill is answered by the array, whether it is
        # the anchor (which carries the formula), a spilled cell (which carries nothing)
        # or a neighbouring column driven by ANCHORARRAY.
        spilled = self._spill_value(ref)
        if spilled is not None:
            return spilled
        f = self.sheet.formula.get(ref)
        if f is None:
            return self.sheet.text.get(ref, "")
        return self._eval_formula(f, ref)

    def _eval_formula(self, f: str, ref: str):
        f = _plain(f)
        _, row = split_ref(ref)

        m = re.fullmatch(r"SUM\(([A-Z]+\d+:[A-Z]+\d+)\)", f)
        if m:
            return sum(float(self.value(c) or 0) for c in expand_range(m.group(1)))

        # COUNTIF(Issue Type,"Complaint") - SUM(B64:B73): the "everything else" bucket
        m = re.fullmatch(r'COUNTIFS?\((.+?)\)\s*-\s*SUM\(([A-Z]+\d+:[A-Z]+\d+)\)', f)
        if m:
            total = self.countifs(self._parse_args(m.group(1), row))
            return total - sum(float(self.value(c) or 0) for c in expand_range(m.group(2)))

        m = re.fullmatch(r"COUNTIFS?\((.+)\)", f)
        if m:
            return self.countifs(self._parse_args(m.group(1), row))

        # A ratio cell: "B74/COUNTIF(...)" -- split on the top-level operator only.
        parts = _split_top(f, "/")
        if len(parts) == 2:
            a, b = (self._operand(p, ref) for p in parts)
            return a / b if b else 0

        raise ValueError(f"{ref}: unsupported formula {f!r}")

    def _operand(self, expr: str, ref: str) -> float:
        expr = expr.strip()
        if re.fullmatch(r"\$?[A-Z]+\$?\d+", expr):
            return float(self.value(expr.replace("$", "")) or 0)
        return float(self._eval_formula(expr, ref) or 0)

    def _parse_args(self, args: str, row: int) -> list[tuple[str, object]]:
        """'ComplaintTracker[Issue Type],"Complaint",ComplaintTracker[Month_Sort],ROW()-49'"""
        parts = re.findall(r'{}\[([^\]]+)\],\s*(".*?"|[^,]+)'.format(TABLE), args)
        out: list[tuple[str, object]] = []
        for col, crit in parts:
            crit = crit.strip()
            if crit.startswith('"'):
                out.append((col, crit.strip('"')))
            elif crit.startswith("ROW()"):
                out.append((col, eval(crit.replace("ROW()", str(row)))))  # noqa: S307 - digits only
            elif crit.startswith("ANCHORARRAY"):
                raise ValueError("spill criteria are handled by top_customers()")
            elif re.fullmatch(r"\$?[A-Z]+\$?\d+", crit):
                out.append((col, self.value(crit.replace("$", ""))))
            else:
                raise ValueError(f"unsupported COUNTIFS criterion {crit!r}")
        if not out:
            raise ValueError(f"no {TABLE}[...] criteria found in {args!r}")
        return out

    # -- the two dynamic arrays --------------------------------------------
    def top_customers(self) -> list[list]:
        """UNIQUE + FILTER + SORTBY(count desc, name asc) + TAKE 10, as two columns."""
        complaints = self.df[self.column("Issue Type") == "Complaint"]
        counts = complaints["Customer"].astype(str).str.strip().value_counts()
        # How many customers the sheet asks for: the trailing count of TAKE(..., n).
        # Greedy on purpose -- a lazy match lands on the ",1)" inside SORTBY's arguments.
        take = 10
        for f in self.sheet.formula.values():
            m = re.search(r"TAKE\(.*,\s*(\d+)\)", _plain(f))
            if m and "SORTBY" in f:
                take = int(m.group(1))
                break
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:take]
        return [[name] for name, _ in ranked]

    def event_types(self) -> list[list]:
        """SORT(UNIQUE(...)) with complaint/inquiry/total columns and a Total row."""
        types = sorted({t for t in self.column("Event type") if t})
        issue = self.column("Issue Type")
        rows = []
        for t in types:
            hit = self.column("Event type") == t
            c = int((hit & (issue == "Complaint")).sum())
            q = int((hit & (issue == "Inquiry")).sum())
            rows.append([t, c, q, c + q])
        rows.append(["Total", sum(r[1] for r in rows), sum(r[2] for r in rows), sum(r[3] for r in rows)])
        return rows

    def _array_vector(self, anchor: str) -> list[list]:
        """The rows one array formula produces, as lists matching that anchor's width.

        Three shapes appear in this workbook and all three are resolved from the
        formula itself, so a block can be moved or a column added without edits here:
        the two LET(...) source arrays, an elementwise COUNTIFS over another array's
        spill, and an elementwise division of one.
        """
        if anchor in self._arrays_cache:
            return self._arrays_cache[anchor]
        f = _plain(self.sheet.formula[anchor])

        if f.startswith("LET("):
            out = self.top_customers() if "SORTBY" in f else self.event_types()
        elif (m := re.fullmatch(r"COUNTIFS?\((.+)\)", f)) and "ANCHORARRAY" in f:
            src = re.search(r"ANCHORARRAY\(([A-Z]+\d+)\)", f).group(1)
            args = m.group(1)
            out = [[self.countifs(self._parse_args(
                args.replace(f"ANCHORARRAY({src})", '"%s"' % row[0]), 0))]
                for row in self._array_vector(src)]
        elif m := re.fullmatch(r"ANCHORARRAY\(([A-Z]+\d+)\)\s*/\s*(.+)", f):
            denom = self._eval_formula(m.group(2), anchor)
            out = [[row[0] / denom if denom else 0] for row in self._array_vector(m.group(1))]
        else:
            raise ValueError(f"{anchor}: unsupported array formula {f!r}")

        self._arrays_cache[anchor] = out
        return out

    def array_regions(self) -> list[tuple[str, int, list[list]]]:
        """(anchor, column span, rows) for every dynamic array declared on the sheet."""
        out = []
        for anchor, ref in self.sheet.array_ref.items():
            left, right = (ref.split(":") + [ref])[:2]
            span = col_to_num(split_ref(right)[0]) - col_to_num(split_ref(left)[0]) + 1
            out.append((anchor, span, self._array_vector(anchor)))
        return out

    def _spill_value(self, ref: str):
        """Values inside a dynamic array come from the array, not a per-cell formula."""
        col, row = split_ref(ref)
        for anchor, span, grid in self.array_regions():
            acol, arow = split_ref(anchor)
            dr, dc = row - arow, col_to_num(col) - col_to_num(acol)
            if 0 <= dr < len(grid) and 0 <= dc < span and dc < len(grid[dr]):
                return grid[dr][dc]
        return None

    def range_values(self, rng: str) -> list:
        return [self.value(c) for c in expand_range(rng)]


def load(csv_path: Path, xlsx_path: Path, sheet_member: str = "xl/worksheets/sheet2.xml") -> DashboardCalc:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    with zipfile.ZipFile(xlsx_path) as z:
        sheet = Sheet(z.read(sheet_member).decode("utf-8"))
    return DashboardCalc(df, sheet)


def chart_series(xml: str) -> list[tuple[str, str, str]]:
    """[(range, cache_kind, whole cache block)] for every <f> in a chart part."""
    out = []
    for m in re.finditer(r"<f>([^<]+)</f>\s*<(numCache|strCache)>(.*?)</\2>", xml, re.S):
        out.append((m.group(1), m.group(2), m.group(0)))
    return out


def cached_points(block: str) -> list[str]:
    return re.findall(r"<pt idx=\"\d+\"[^>]*>\s*<v>(.*?)</v>\s*</pt>", block, re.S)
