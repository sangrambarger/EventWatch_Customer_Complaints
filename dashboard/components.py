"""Reusable rendering: cards, tables, charts and the page furniture around them.

Everything here takes a frame or a figure and draws it. Nothing here decides what a
number means -- that is `metrics` -- so a view can be restyled without touching a total.
"""
from __future__ import annotations

import html
import os
import re
import textwrap
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from dashboard.config import DESCRIPTIONS, PAGE_KICKERS
from dashboard.styles import BLUE_RAMP, RED_BLUE, TAGS, esc
from dashboard.taxonomy import plural
from dashboard.metrics import MISS_COLOURS




def page_header(title):
    kicker, accent = PAGE_KICKERS.get(title, ("Dashboard", "#8ab4f8"))
    st.markdown(
        f"<div class='page-hero' style='--accent:{accent}'><div class='page-kicker'><span class='dot'></span>{kicker}</div>"
        f"<h1>{title}</h1><p>{DESCRIPTIONS.get(title,'')}</p></div>",
        unsafe_allow_html=True,
    )


def add_section(title, desc="", accent="#8ab4f8"):
    st.markdown(f"<div class='section-card' style='--accent:{accent}'><h3>{title}</h3><p>{desc}</p></div>", unsafe_allow_html=True)


def kpis(items, columns=None):
    """A row of cards, on one row. `columns` sizes the grid to the count.

    The default five-column grid is right for the KPI strips, which are always five
    cards. Everything else is a variable count, and both auto-fitting and assuming five
    get it wrong: auto-fit wrapped a five-card row to four-plus-one on any window
    narrower than about 1200px, and a fixed five leaves a hole when there are four.
    Passing the count keeps the row a row at any width the dashboard is read at.
    """
    cards = [f"<div class='kpi' style='--accent:{a}'><div class='kpi-label'>{esc(l)}</div><div class='kpi-num'>{esc(v)}</div><div class='kpi-foot'>{esc(f)}</div></div>" for l, v, f, a in items]
    style = f" style='grid-template-columns:repeat({columns},minmax(0,1fr))'" if columns else ""
    st.markdown(f"<div class='kpi-grid'{style}>" + "".join(cards) + "</div>", unsafe_allow_html=True)


def excel_bar_table(df, label_col, value_col="Records", extras=None, label_head=None,
                    value_head="Total emails", height=None, total_row=True, variant=None,
                    totals=None, wrap=(), raw=(), classes=None, caption=None):
    """A ranked table whose last-but-one column is a bar drawn inside the cell.

    `extras` are the columns carried between the label and the bar; the default picks
    up the complaint/inquiry split wherever a table has it. `height` caps the table and
    scrolls it in place -- which is how a full list of every account stays on an
    executive page without either truncating it or costing thirty rows of scroll. It is
    a scroll box rather than a collapsed expander on purpose: a collapsed expander is
    laid out at zero height, so `innerText` reads empty and `audit_pages.py` stops
    reconciling every row it hides.

    `wrap` names the columns that hold a sentence rather than a value. Without it the
    `wide` variant sets `white-space:nowrap` on every cell, so a column of explanations
    pushed the table sideways off the panel and the reader scrolled horizontally to
    read a sentence -- the single worst thing on this page. A wrapped column is
    left-aligned and bounded, and the rest of the table keeps its one-line rows.

    `raw` names the columns whose value is already HTML and must not be escaped -- the
    owner pills, and nothing else. Everything a customer or an analyst typed goes
    through `esc()`; only strings this module builds itself may skip it.
    """
    if df.empty or label_col not in df.columns or value_col not in df.columns:
        st.info("No data available for this view."); return
    max_v = max(float(df[value_col].max()), 1)
    extra = [c for c in (extras if extras is not None
                         else ("Complaints", "Inquiries", "Misses", "Reported timely"))
             if c in df.columns]
    wrap = tuple(wrap); raw = tuple(raw); classes = classes or {}
    klass_of = {}
    for c in extra:
        names = (["wrap"] if c in wrap else []) + ([classes[c]] if c in classes else [])
        klass_of[c] = f" class='{' '.join(names)}'" if names else ""
    rows = []
    for _, r in df.iterrows():
        width = float(r[value_col]) / max_v * 100
        cells = "".join(f"<td{klass_of[c]}>{r[c] if c in raw else esc(r[c])}</td>" for c in extra)
        rows.append(f"<tr><td>{esc(r[label_col])}</td>{cells}"
                    f"<td class='bar-cell'><div class='bar-box' style='--w:{width:.1f}%'><span>{esc(r[value_col])}</span></div></td>"
                    f"<td>{esc(r.get('% of Total',''))}</td></tr>")
    if total_row and len(df):
        # Summed here rather than by a generic helper, because the share column is a
        # formatted string: "29.5%" cannot be added up after the fact, and the total of
        # a column of shares is 100% of whatever base the table was built from, not the
        # sum of the strings in it.
        #
        # `totals` overrides a column's sum with the true figure, for the one table whose
        # rows deliberately double-count: an email naming two accounts appears on both
        # their rows, so the columns add to more than the tracker holds. Adding the
        # column up there would print a total that contradicts every other number on the
        # page, which is exactly what a total row exists to prevent.
        def foot(col):
            if totals and col in totals:
                return int(totals[col])
            if pd.api.types.is_numeric_dtype(df[col]):
                return int(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
            return None
        sums = "".join(f"<td{klass_of[c]}>{esc(v)}</td>" if (v := foot(c)) is not None
                       else f"<td{klass_of[c]}></td>" for c in extra)
        grand = foot(value_col)
        rows.append(f"<tr class='total'><td>Total</td>{sums}<td>{esc(grand)}</td>"
                    f"<td>{'100%' if '% of Total' in df.columns else ''}</td></tr>")
    heads = "".join(f"<th{klass_of[c]}>{esc(c)}</th>" for c in extra)
    box = f" style='max-height:{int(height)}px;overflow-y:auto'" if height else ""
    if height and total_row:
        variant = f"{variant} stickytotal" if variant else "stickytotal"
    klass = "excel-table" + (f" {variant}" if variant else "")
    st.markdown(f"<div class='table-wrap'{box}><table class='{klass}'><thead><tr>"
                f"<th>{esc(label_head or label_col)}</th>" + heads +
                f"<th>{esc(value_head)}</th><th>% of Total</th></tr></thead><tbody>" + "".join(rows) +
                "</tbody></table></div>", unsafe_allow_html=True)
    if caption:
        st.caption(caption)


def cell(v):
    """One display string per value.

    A date column read from the CSV arrives as a Timestamp, and str() on that prints
    "2026-01-09 00:00:00" -- a midnight time on every row of the tracker that means
    nothing and crowds the column. Whole floats lose their trailing ".0" for the same
    reason, and a missing value renders as empty rather than "nan".
    """
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    # pd.NaT satisfies isinstance(v, datetime) as well as the Timestamp check above,
    # and strftime raises on it -- so both date branches have to guard, not just one.
    # Nothing rendered a date column containing blanks until Resolution Date arrived,
    # which is why this only surfaced now.
    if isinstance(v, (pd.Timestamp, datetime)):
        return "" if pd.isna(v) else v.strftime("%d-%b-%Y")
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    text = str(v)
    return "" if text in {"nan", "NaT", "None"} else text


def styled_table(df, max_rows=None, height=None, variant=None, wrap=(), styles=None,
                 total_row=False):
    """Render any dataframe as a clean bordered table matching the Excel dashboard's table style.

    `variant="wide"` is for a grid with more columns than fit the panel -- the tracker's
    eighteen. The default table is `width:100%`, which squeezes those columns until every
    multi-word cell wraps and the rows come out two and three lines tall; the wide variant
    sizes to its content and scrolls sideways instead, so each row is one line.
    `variant="record"` is the one-record card: two columns, left-aligned and wrapping,
    because centring a paragraph of Comments across half the page is unreadable.
    `variant="wide grid"` adds the Complaint Tracker's restyle on top of `wide`: hairline
    row separators instead of a full box grid, top-aligned cells and a sticky first column.
    `wrap` names the columns that may wrap inside a bounded width rather than being held
    to one line, so a long value is shown whole instead of cut. `styles` gives a column one
    more cell class -- `num` for tabular figures so dates line up down the column, `key` for
    the monospace Jira key.
    """
    if df is None or df.empty:
        st.info("No data available for this view."); return
    show = df.head(max_rows) if max_rows else df
    styles = styles or {}
    klasses = []
    for c in show.columns:
        names = (["wrap"] if c in wrap else []) + ([styles[c]] if c in styles else [])
        klasses.append(f" class='{' '.join(names)}'" if names else "")
    head = "".join(f"<th{k}>{esc(c)}</th>" for c, k in zip(show.columns, klasses))
    # A wrapped cell's text goes inside a div, because `max-height` on a `td` is advisory
    # -- the cell still grows to its content. The div is what the grid variant caps.
    wrapped = [c in wrap for c in show.columns]
    last = len(show) - 1
    mark = " class='total'"
    body = "".join(
        "<tr" + (mark if total_row and i == last else "") + ">" + "".join(
            f"<td{k}><div class='cell'>{esc(cell(v))}</div></td>" if w else f"<td{k}>{esc(cell(v))}</td>"
            for v, k, w in zip(row, klasses, wrapped)) + "</tr>"
        for i, row in enumerate(show.itertuples(index=False))
    )
    wrap_style = f" style='max-height:{height}px;overflow-y:auto'" if height else ""
    klass = f"excel-table {variant}" if variant else "excel-table"
    st.markdown(f"<div class='table-wrap'{wrap_style}><table class='{klass}'><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>", unsafe_allow_html=True)
    if max_rows and len(df) > max_rows:
        st.caption(f"Showing {max_rows} of {len(df)} rows — use the download button below for the full set.")


def chart(df, label_col, value_col="Records", title="", x_title="Records"):
    if df.empty or label_col not in df.columns or value_col not in df.columns:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}, {value_col}."); return None
    # When the table carries the complaint/inquiry split, stack it so the bar shows what
    # the total is made of rather than hiding it behind one number.
    parts = [c for c in ("Complaints", "Inquiries") if c in df.columns]
    keep = [label_col, value_col] + parts
    data = df[keep].dropna(subset=[label_col, value_col]).head(20).copy()
    if data.empty: st.info("No chartable records available for this view."); return None
    data[label_col] = data[label_col].astype(str)
    if parts:
        fig = px.bar(data, x=parts, y=label_col, orientation="h", text_auto=True, title=title,
                     color_discrete_map={"Complaints": "#8ab4f8", "Inquiries": "#f6c177"})
        fig.update_layout(barmode="stack", legend_title_text="",
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0))
    else:
        fig = px.bar(data, x=value_col, y=label_col, orientation="h", text=value_col, title=title, color_discrete_sequence=["#8ab4f8"])
    fig.update_yaxes(categoryorder="total ascending", tickfont=dict(size=13, color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title=x_title)
    fig.update_traces(opacity=.92, cliponaxis=False, marker_line_width=0)
    if not parts: fig.update_traces(textposition="outside")
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26", font=dict(color="#f3f4f6", size=13), margin=dict(l=20, r=60, t=64 if parts else 44, b=28), height=max(360, min(760, len(data) * 38 + 150)), showlegend=bool(parts))
    st.plotly_chart(fig, width="stretch")
    return fig


def donut(t, label_col="Category", value_col="Records", colours=None, centre="", title="",
          meanings=None):
    """Parts of one whole, labelled on the slice.

    A pie is usually the wrong answer, but this is the one shape it is right for: four
    mutually exclusive buckets that sum to a stated total, where the question is "which
    one is the biggest share of the misses". Labels sit outside the ring with the count
    and the share on them, so the ring is the shape and the text is the number.
    """
    if t is None or t.empty or value_col not in t.columns:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}.")
        return None
    total = int(t[value_col].sum())
    # Each slice explains itself on hover, wrapped before it reaches plotly -- plotly's
    # hover label neither wraps nor is clipped to the panel, so an unwrapped sentence
    # runs off both edges of a half-width column and loses its own ends.
    note = [("<br>".join(textwrap.wrap((meanings or {}).get(str(label), ""), 44)))
            for label in t[label_col]]
    fig = go.Figure(go.Pie(
        labels=list(t[label_col]), values=list(t[value_col]), hole=0.58, sort=False,
        direction="clockwise", marker=dict(colors=colours or MISS_COLOURS,
                                           line=dict(color="#1b1f26", width=2)),
        # One decimal on the share, like the table under it. Plotly's default gives two
        # significant figures, so a 3-miss slice printed 3.85% beside a table saying 3.8%.
        texttemplate="%{label}<br><b>%{percent:.1%}</b> · %{value}", textposition="outside",
        textfont=dict(size=13, color="#f3f4f6"), customdata=note,
        hovertemplate="<b>%{label}</b> — %{value} of " + str(total) +
                      ", %{percent:.1%}<br>%{customdata}<extra></extra>"))
    fig.update_layout(
        template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
        font=dict(color="#f3f4f6", size=13), showlegend=False, title=title,
        hoverlabel=dict(bgcolor="#11151b", align="left",
                        font=dict(color="#f3f4f6", size=12)),
        margin=dict(l=90, r=90, t=70 if title else 40, b=40), height=440,
        annotations=[dict(text=f"<b style='font-size:30px'>{total}</b><br>{centre}",
                          x=0.5, y=0.5, showarrow=False,
                          font=dict(size=13, color="#b6beca"))])
    st.plotly_chart(fig, width="stretch")
    return fig


def heatmap(grid, title=""):
    """A grid of magnitudes wants a heatmap, not sixteen coloured bars.

    Sixteen sub-types is far past the point where categorical colour stays readable, and
    a single sequential hue also shows the *sparsity* -- People and Product barely
    overlap -- which a ranked bar chart cannot say at all.
    """
    if grid is None or grid.empty:
        st.info("Chart cannot be rendered because required fields are missing: Sub-type, Root Cause.")
        return None
    fig = px.imshow(grid.values, x=list(grid.columns), y=list(grid.index),
                    color_continuous_scale=BLUE_RAMP, aspect="auto", text_auto=True, title=title)
    fig.update_traces(xgap=2, ygap=2,  # the 2px surface gap between fills
                      hovertemplate="%{y} · %{x}<br>%{z} record(s)<extra></extra>")
    fig.update_xaxes(side="top", tickfont=dict(size=13, color="#f3f4f6"), title="")
    fig.update_yaxes(tickfont=dict(size=12, color="#f3f4f6"), title="")
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=13), coloraxis_showscale=False,
                      margin=dict(l=20, r=30, t=70, b=30),
                      height=max(380, len(grid.index) * 32 + 150))
    st.plotly_chart(fig, width="stretch")
    return fig


def proportion_bar(frame, label_col, part_col, whole_col, part_name, rest_name, title=""):
    """A ratio per row, drawn to a common 100% width.

    These are ratios, not categories: a two-slice pie is the classic wrong answer and a
    grouped bar makes the reader divide. Rows share a baseline, so a glance ranks them.
    """
    if frame is None or frame.empty:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}.")
        return None
    data = frame.copy()
    data["_part"] = data[part_col] / data[whole_col] * 100
    data["_rest"] = 100 - data["_part"]
    part_hue, rest_hue = RED_BLUE
    fig = go.Figure()
    fig.add_trace(go.Bar(y=data[label_col], x=data["_part"], orientation="h", name=part_name,
                         marker=dict(color=part_hue, line=dict(width=2, color="#1b1f26")),
                         text=[f"{v:.0f}%" for v in data["_part"]], textposition="inside",
                         insidetextanchor="middle", textfont=dict(color="#1b1f26", size=12),
                         customdata=data[[part_col, whole_col]].values,
                         hovertemplate="%{y}<br>%{customdata[0]} of %{customdata[1]}<extra></extra>"))
    fig.add_trace(go.Bar(y=data[label_col], x=data["_rest"], orientation="h", name=rest_name,
                         marker=dict(color=rest_hue, line=dict(width=2, color="#1b1f26")),
                         hoverinfo="skip"))
    fig.update_xaxes(ticksuffix="%", range=[0, 100], tickfont=dict(size=12, color="#f3f4f6"),
                     gridcolor="#303846", title="")
    fig.update_yaxes(tickfont=dict(size=13, color="#f3f4f6"), title="")
    fig.update_layout(barmode="stack", template="plotly_dark", plot_bgcolor="#1b1f26",
                      paper_bgcolor="#1b1f26", font=dict(color="#f3f4f6", size=13), title=title,
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0), legend_title_text="",
                      margin=dict(l=20, r=40, t=70, b=30),
                      height=max(320, len(data) * 40 + 150))
    st.plotly_chart(fig, width="stretch")
    return fig


def downloads(df, name, fig=None):
    # The plotly toolbar hint used to print beside every download row, including the many
    # that sit under a table with no chart anywhere near them.
    c1, c2 = st.columns([1, 1]) if fig is not None else (st.container(), None)
    # The Owner column carries pill markup for the screen. A CSV full of "<span class=..."
    # is not a download anybody can open in Excel, so the tags come off on the way out
    # and the cell reads "Product 12 People 3".
    export = df.copy()
    for col in export.columns:
        if export[col].dtype == object:
            export[col] = export[col].map(
                lambda v: TAGS.sub(" ", v).strip() if isinstance(v, str) and "<" in v else v)
    c1.download_button("Download table CSV", export.to_csv(index=False).encode(), f"{name}.csv", "text/csv", key=f"csv_{name}")
    if fig is not None:
        c2.download_button("Download chart HTML", fig.to_html().encode(), f"{name}_chart.html", "text/html", key=f"chart_{name}")


def add_rule():
    """A full-width hairline between sections.

    The heading card alone was not enough separation: on a page this long the eye lost
    which chart a table belonged to, and two adjacent sections read as one.
    """
    st.markdown("<div class='section-rule'></div>", unsafe_allow_html=True)


def driver_bar(frame, colour, title="", slots=None, xmax=None):
    """A compact bar of one root cause's drivers, all in that root's colour.

    One hue per chart on purpose: the root cause is already named on the card above, so
    colouring the drivers against each other would say a difference that is not there.
    The plain-English meaning rides on the hover so the bar stays a bar.
    """
    if frame is None or frame.empty:
        st.caption("No confirmed miss for this root cause in the current filter.")
        return None
    data = frame.copy()
    # Plotly's hover label does not wrap and is not clipped to the panel, so a long
    # meaning ran off both edges of a third-width column and lost its own ends. Wrapping
    # it here is the only thing that keeps the tooltip inside the card.
    data["_hover"] = data["What it means"].map(
        lambda t: "<br>".join(textwrap.wrap(str(t), 44)) or "")
    data["_count"] = data["Misses"].map(lambda n: plural(int(n), "confirmed miss", "confirmed misses"))
    fig = px.bar(data, x="Misses", y="Driver", orientation="h", text="Misses",
                 title=title, color_discrete_sequence=[colour],
                 custom_data=["_hover", "% of Total", "_count"],
                 category_orders={"Driver": list(data["Driver"])})
    fig.update_traces(opacity=.93, marker_line_width=0, cliponaxis=False,
                      textposition="outside", textfont=dict(size=12, color="#f3f4f6"),
                      hovertemplate="<b>%{y}</b> — %{customdata[2]}, %{customdata[1]}"
                                    "<br>%{customdata[0]}<extra></extra>")
    fig.update_yaxes(tickfont=dict(size=12.5, color="#f3f4f6"), gridcolor="#303846", title="",
                     automargin=True, ticklabelposition="outside")
    # One x scale across all three panels. Each chart used to autoscale, so Process's
    # 2-miss bar drew almost as long as Product's 24 -- three panels side by side are
    # read as a comparison whether or not they are labelled one, and bar length is the
    # thing a reader takes from a bar chart before the number beside it. The axis stays
    # hidden; the count still rides on the end of every bar.
    fig.update_xaxes(visible=False, range=[0, (xmax or float(data["Misses"].max())) * 1.16])
    # `slots` pads the axis to the longest of the three lists rather than stretching this
    # one's bars to fill the panel: three charts of equal height whose bars are three
    # different thicknesses compare their own shapes, not their numbers. The padding is
    # empty space below the last bar, which reads as "this root cause has fewer kinds".
    rows = max(slots or len(data), len(data))
    # px numbers the categories from the bottom, so the padded slots have to be added
    # below the shortest list rather than above it -- otherwise a root cause with two
    # drivers draws them at the foot of an empty panel.
    fig.update_yaxes(range=[len(data) - rows - 0.5, len(data) - 0.5])
    # hovermode "y" so the tooltip fires anywhere along the row, not only on the bar:
    # a one-miss bar is fourteen pixels wide, and the rows a reader most wants explained
    # -- Other, Needs Review -- are exactly the short ones.
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=12), showlegend=False, hovermode="y",
                      hoverlabel=dict(bgcolor="#11151b", bordercolor=colour, align="left",
                                      font=dict(color="#f3f4f6", size=12)),
                      margin=dict(l=0, r=40, t=8, b=6),
                      height=max(160, rows * 38 + 36))
    st.plotly_chart(fig, width="stretch")
    return fig


def stacked_bar(frame, label_col, parts, colours, title="", x_title="Records", rows=8):
    """A ranked horizontal bar broken into named parts.

    `chart()` stacks the complaint/inquiry split and nothing else; this takes any set of
    part columns, which is what lets one account's bar say *why* it was missed rather
    than only how often.
    """
    parts = [c for c in parts if c in frame.columns]
    if frame.empty or label_col not in frame.columns or not parts:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}.")
        return None
    data = frame.head(rows).copy()
    data[label_col] = data[label_col].astype(str)
    fig = px.bar(data, x=parts, y=label_col, orientation="h", title=title,
                 color_discrete_map=colours)
    # Eleven series wrap the legend onto three rows. Above the plot those rows land on
    # the title; below the axis they have the whole bottom margin to themselves.
    rows_of_legend = max(1, (len(parts) + 3) // 4)
    fig.update_layout(barmode="stack", legend_title_text="",
                      legend=dict(orientation="h", yanchor="top", y=-0.13, x=0))
    fig.update_yaxes(categoryorder="total ascending", tickfont=dict(size=13, color="#f3f4f6"),
                     gridcolor="#303846", title="")
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title=x_title)
    fig.update_traces(opacity=.92, cliponaxis=False, marker_line_width=0,
                      hovertemplate="%{y}<br>%{fullData.name}: %{x}<extra></extra>")
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=13),
                      margin=dict(l=20, r=40, t=56, b=46 + 26 * rows_of_legend),
                      height=max(360, min(780, len(data) * 40 + 190 + 26 * rows_of_legend)))
    st.plotly_chart(fig, width="stretch")
    return fig


def trend_chart(rate, band, title=""):
    """One bar per month, coloured by which window it belongs to.

    This was a line with two flat shelves drawn over it and a signed delta printed on the
    plot, and it was not readable: a reader had to be told what the shelves meant before
    the chart said anything. Bars need no explaining -- each month is its own bar with its
    own percentage printed on it, and the two windows being compared are told apart by
    colour, with the comparison itself stated in words above the chart rather than drawn
    into it. Months outside both windows stay grey so they cannot be mistaken for part of
    the comparison.
    """
    if rate.empty or "Missed %" not in rate.columns:
        st.info("Chart cannot be rendered because required fields are missing: Month, Missed %.")
        return None
    months = list(rate["Month"])
    older = set(band["older"]["months"]) if band else set()
    recent = set(band["recent"]["months"]) if band else set()
    colour = ["#8ab4f8" if m in recent else "#b6beca" if m in older else "#3a414d" for m in months]
    legend = ("Blue: the last three months.  Grey: the three before.  Dark: outside the comparison."
              if band else "")
    fig = go.Figure(go.Bar(
        x=months, y=list(rate["Missed %"]), marker=dict(color=colour, line=dict(width=0)),
        text=[f"{v:.0f}%" for v in rate["Missed %"]], textposition="outside",
        textfont=dict(size=13, color="#f3f4f6"),
        customdata=rate[["Missed", "Records"]].values,
        hovertemplate="%{x}<br>%{y:.0f}% — %{customdata[0]} of %{customdata[1]} emails<extra></extra>"))
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_yaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title="",
                     ticksuffix="%", range=[0, 105])
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=13), title=title, showlegend=False,
                      margin=dict(l=20, r=30, t=56 if title else 20, b=28), height=400)
    st.plotly_chart(fig, width="stretch")
    if legend:
        st.caption(legend)
    return fig


def ranked_bar(frame, label_col, value_col, colours=None, title="", x_title="Records",
               height_per=38):
    """One bar per category, longest first, each in its own colour.

    A donut stops working past about six slices, and there are eleven kinds of miss once
    the residue bucket is gone. A ranked bar takes as many categories as the taxonomy
    has, keeps every name readable on the axis, and still shows the share -- which is
    what the ring was for.
    """
    if frame is None or frame.empty or label_col not in frame.columns:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}.")
        return None
    data = frame.copy()
    data[label_col] = data[label_col].astype(str)
    fig = px.bar(data, x=value_col, y=label_col, orientation="h", title=title,
                 text=value_col, color=label_col,
                 color_discrete_map=colours or {},
                 category_orders={label_col: list(data[label_col])})
    fig.update_yaxes(tickfont=dict(size=13, color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title=x_title)
    fig.update_traces(opacity=.92, cliponaxis=False, marker_line_width=0,
                      textposition="outside", textfont=dict(size=13, color="#f3f4f6"),
                      hovertemplate="%{y}<br>%{x}<extra></extra>")
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=13), showlegend=False,
                      margin=dict(l=20, r=70, t=56 if title else 20, b=34),
                      height=max(320, len(data) * height_per + 130))
    st.plotly_chart(fig, width="stretch")
    return fig


def grouped_bar(frame, label_col, series, colours, title="", x_title="Customer emails"):
    """Two bars per row, so "how many, and how many of those went wrong" is one picture.

    The sunburst that stood here was two rings of unequal wedges, and past the biggest
    four every label was too small to print. This says the same thing in a form a reader
    does not have to be taught: every sub-type on the axis, nothing folded away.
    """
    series = [c for c in series if c in frame.columns]
    if frame is None or frame.empty or not series:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}.")
        return None
    data = frame.copy()
    data[label_col] = data[label_col].astype(str)
    fig = px.bar(data, x=series, y=label_col, orientation="h", barmode="group", title=title,
                 text_auto=True, color_discrete_map=colours,
                 category_orders={label_col: list(data[label_col])})
    fig.update_yaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title=x_title)
    fig.update_traces(opacity=.92, cliponaxis=False, marker_line_width=0,
                      textfont=dict(size=11), textposition="outside",
                      hovertemplate="%{y}<br>%{fullData.name}: %{x}<extra></extra>")
    fig.update_layout(template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
                      font=dict(color="#f3f4f6", size=13), legend_title_text="",
                      legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
                      margin=dict(l=20, r=70, t=86, b=34),
                      height=max(420, len(data) * 46 + 180))
    st.plotly_chart(fig, width="stretch")
    return fig

