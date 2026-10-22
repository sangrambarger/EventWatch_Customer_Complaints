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
from dashboard.styles import BLUE_RAMP, CAT_SLATE, RED_BLUE, ROOT_COLOURS, TAGS, UNKNOWN_OWNER, esc
from dashboard.taxonomy import plural




def page_header(title):
    kicker, accent = PAGE_KICKERS.get(title, ("Dashboard", "#8ab4f8"))
    st.markdown(
        f"<div class='page-hero' style='--accent:{accent}'><div class='page-kicker'><span class='dot'></span>{kicker}</div>"
        f"<h1>{title}</h1><p>{DESCRIPTIONS.get(title,'')}</p></div>",
        unsafe_allow_html=True,
    )


def add_section(title, desc="", accent="#8ab4f8"):
    # An empty `desc` used to render an empty `<p>`, which the card's flex gap then
    # spaces as though it held a sentence. A heading with no description is a heading.
    body = f"<p>{desc}</p>" if desc else ""
    st.markdown(f"<div class='section-card' style='--accent:{accent}'><h3>{title}</h3>{body}</div>", unsafe_allow_html=True)


def kpis(items, columns=None):
    """A row of cards, on one row. `columns` sizes the grid to the count.

    The default five-column grid is right for the KPI strips, which are always five
    cards. Everything else is a variable count, and both auto-fitting and assuming five
    get it wrong: auto-fit wrapped a five-card row to four-plus-one on any window
    narrower than about 1200px, and a fixed five leaves a hole when there are four.
    Passing the count keeps the row a row at any width the dashboard is read at.
    """
    cards = [kpi_card(l, v, f, a) for l, v, f, a in items]
    style = f" style='grid-template-columns:repeat({columns},minmax(0,1fr))'" if columns else ""
    st.markdown("<div class='kpi-grid'" + style + ">" + "".join(cards) + "</div>", unsafe_allow_html=True)


def kpi_card(label, value, foot, accent):
    """One card's markup. The single source for it, so the plain grid above and the
    clickable row below cannot drift into two slightly different cards."""
    return (f"<div class='kpi' style='--accent:{accent}'><div class='kpi-label'>{esc(label)}</div>"
            f"<div class='kpi-num'>{esc(value)}</div><div class='kpi-foot'>{esc(foot)}</div></div>")


def clickable_kpis(items, keys, row, available=()):
    """A row of cards where the WHOLE CARD is the click target, not a button beside it.

    Returns the key of the card clicked this run, or None.

    Streamlit cannot attach a callback to arbitrary HTML, so the first cut put a small
    button under each card. The owner's answer was that the card itself should open its
    own breakdown, which leaves two ways to do it and only one that is safe.

    A plain `<a href="?card=...">` would make the card clickable with no widget at all,
    and it is the wrong answer here: a real anchor navigates the page, Streamlit hands
    back a fresh session, and every sidebar filter resets. The filters are the one thing
    on this dashboard that has already cost a round of "I had to constantly refresh the
    tab", so a popup that silently clears them is a worse bug than the one it fixes.

    So: a real `st.button` per card, laid over the card and made invisible. The click
    stays inside the session, the filter state is untouched, and the button keeps its
    label in the accessibility tree -- the text is hidden with `color:transparent` and a
    zero font size rather than by removing it, so a screen reader still announces which
    card it is opening. Each card sits in its own `st.container(key=...)`, which is what
    the stylesheet positions the overlay against.

    A card with no payload (the filter left it nothing to break down) renders as a plain
    card with no overlay, rather than a click that opens an empty panel.
    """
    clicked = None
    with st.container(key=f"kpi-row-{row}"):
        for column, (item, key) in zip(st.columns(len(items)), zip(items, keys)):
            label, value, foot, accent = item
            with column:
                if key not in available:
                    st.markdown(kpi_card(label, value, foot, accent), unsafe_allow_html=True)
                    continue
                with st.container(key=f"kpi-hit-{key}"):
                    st.markdown(kpi_card(label, value, foot, accent), unsafe_allow_html=True)
                    if st.button(f"Break down {label}", key=f"kpi-open-{key}", width="stretch"):
                        clicked = key
    return clicked


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



def detail_panel(card):
    """Draw one card popup from the payload `metrics.card_details()` built.

    One anatomy on all eight, because eight panels that each invent their own shape are
    eight things a reader has to learn: the chain that says where the figure sits in the
    funnel, the question, the figure with its base, one short sentence, a rule, the stat
    cards, a rule, and one footer line carrying the arithmetic and the single caveat.

    The number leads on every card and its label sits under it. The panels this replaced
    put each figure at the right edge of a line of prose, which is the arrangement where
    the words are read and the number is not.

    Drawing only. Every number arrives formatted; nothing here adds, divides or rounds.
    """
    chain = " <span class='pop-sep'>&rsaquo;</span> ".join(
        f"<span class='{'pop-here' if here else ''}'>{esc(str(t))}</span>" for t, here in card.get("chain", []))
    out = [f"<div class='pop'><div class='pop-chain'>{chain}</div>",
           f"<div class='pop-q'>{esc(card['question'])}</div>",
           f"<div class='pop-hero'><div class='pop-num'>{esc(card['hero'])}</div>"
           f"<div class='pop-base'>{card.get('base', '')}</div></div>"]
    if card.get("lead"):
        out.append(f"<div class='pop-lead' style='--accent:{card['accent']}'>{card['lead']}</div>")
    out.append("<div class='pop-rule'></div>")

    # The shape bar. Widths come from the counts the cards print, so the bar and the
    # cards cannot disagree; a 2px gap in the surface colour separates the segments
    # rather than a border, which would add ink that is not data.
    stack = [(n, c) for n, c in card.get("stack", []) if n]
    if stack:
        out.append("<div class='pop-stack'>"
                   + "".join(f"<span style='flex:{n};background:{c}'></span>" for n, c in stack)
                   + "</div>")
    if card.get("legend"):
        out.append("<div class='pop-keys'>"
                   + "".join(f"<span class='pop-key'><i style='background:{c}'></i>{esc(t)}</span>"
                             for t, c in card["legend"]) + "</div>")

    for i, block in enumerate(card.get("blocks", [])):
        if not block["items"]:
            continue
        if i:
            out.append("<div class='pop-rule'></div>")
        cells = "".join(
            f"<div class='pop-stat' style='--c:{s['colour']}'>"
            f"<div class='pop-sv'>{esc(s['value'])}</div>"
            f"<div class='pop-sl'>{s['label']}</div>"
            + (f"<div class='pop-sn'>{s['note']}</div>" if s.get("note") else "")
            + "</div>" for s in block["items"])
        out.append(f"<div class='pop-stats' style='--cols:{block['cols']}'>{cells}</div>")

    # The monthly bars, on the one panel about movement. Each carries its own base,
    # because a rate quoted bare invites a reader to lean on a month that will move.
    if card.get("bars"):
        out.append("<div class='pop-rule'></div><div class='pop-bars'>")
        for b in card["bars"]:
            out.append(f"<div class='pop-bar'><span class='pop-bname'>{esc(b['name'])}</span>"
                       f"<span class='pop-track'><span class='pop-fill' "
                       f"style='width:{max(float(b['width']), 2):.1f}%;background:{b['colour']}'></span></span>"
                       f"<b class='pop-bval'>{esc(str(b['value']))}</b>"
                       f"<span class='pop-bnote'>{esc(str(b['note']))}</span></div>")
        out.append("</div>")

    out.append(f"<div class='pop-foot'><span class='pop-eq'>{esc(card.get('foot_left', ''))}</span>"
               f"<span>{esc(card.get('foot_right', ''))}</span></div></div>")
    st.markdown("".join(out), unsafe_allow_html=True)


# Bottom to top, the order a reader works down the funnel: the two miss owners first,
# then the stage nobody owns, then the emails that were never a failure. Colour carries
# the one thing it carries everywhere on this dashboard -- who investigates it --
# straight from `ROOT_COLOURS`, so a Product miss is the same blue here as on the cards.
#
# `--red` against `--amber` is the weak colourblind pair at dE 13.9 and they would sit
# adjacent in this stack the day the first Process miss lands. Every segment prints its
# own count and the table beneath carries all of them, which is the secondary encoding
# that makes the pair legal -- but it is a real constraint, not a non-issue.
MONTH_PARTS = (
    ("Product", ROOT_COLOURS["Product"], "Product & Platform investigate it"),
    ("Analyst", ROOT_COLOURS["People"], "EventWatch Ops investigate it"),
    ("Process", ROOT_COLOURS["Process"], "A workflow or control failure"),
    ("Wrong", CAT_SLATE, "Reported in time, and something about it was wrong"),
    ("Inquiries", "#80cbc4", "A question, not a complaint"),
)
MONTH_NAMES = {"Wrong": "Reported, but wrong", "Product": "Product miss", "Analyst": "Analyst miss",
               "Process": "Process miss", "Inquiries": "Inquiry"}


def monthly_stack(frame, key=None):
    """One bar per month, split by where that month's emails ended up.

    The grouped complaint-against-inquiry pair this replaced was volume only: it said
    how many arrived and nothing about how many we got wrong, which is the whole of what
    the block was asked for. Five segments in one bar carry the same total and the
    failure split with it.

    Returns `(figure, clicked month or None)`. With a `key` the bars are a click target
    and the chart reports which month the reader opened; without one it is a plain chart,
    which is what the download helper and any future caller that owns no dialog want.

    **The miss rate rides above each bar**, so the chart answers "is it getting worse"
    without the reader going to the table. A month under `THIN_MONTH` emails prints its
    rate muted: Jan is 3 of 4, where one record moves the figure 25 points, and a rate
    that thin sitting in the same white as a 19-email month invites a comparison that
    is not there.
    """
    if frame is None or frame.empty:
        st.info("Chart cannot be rendered because required fields are missing: Month.")
        return None, None
    months = list(frame["Month"])
    top = max([int(v) for v in frame["Emails"]] or [1])
    # A segment under about a sixteenth of the tallest bar is too short to hold its own
    # label: plotly clips the digit vertically rather than dropping it, and a clipped
    # "1" reads as a stray mark on the bar. `uniformtext` does not catch it, because the
    # text fits horizontally. The count is still on the hover and in the table.
    floor = max(top * 0.06, 2)
    fig = go.Figure()
    # `part`, not `key`. This loop variable was named `key` and shadowed the parameter
    # of the same name on the line above: after it ran, `key` was always "Inquiries" --
    # the last entry in MONTH_PARTS -- whatever the caller passed. Two things broke
    # silently. The `if not key` guard below could never fire, so the plain
    # non-clickable chart was unreachable code and every caller got a click handler;
    # and the chart's widget key was the literal string "Inquiries" rather than the
    # caller's, so the one piece of session state this function documents as belonging
    # to exactly one page was filed under a name no page chose. Only one page draws the
    # chart today, which is why neither had a visible symptom yet.
    for part, colour, meaning in MONTH_PARTS:
        values = [int(v) for v in frame[part]]
        if not any(values):
            continue
        fig.add_bar(
            x=months, y=values, name=MONTH_NAMES.get(part, part),
            marker=dict(color=colour, line=dict(width=0)),
            text=[str(v) if v >= floor else "" for v in values], textposition="inside",
            insidetextanchor="middle", textfont=dict(size=12, color="#1b1f26"),
            # `hovermode="x unified"` already prints the month as the box's header, so a
            # row that repeats it reads "May 2026 · 9 product miss" under a heading that
            # says May 2026.
            hovertemplate="%{y} " + esc(MONTH_NAMES.get(part, part).lower())
                          + f" — {esc(meaning)}<extra></extra>")
    for _, r in frame.iterrows():
        fig.add_annotation(
            x=r["Month"], y=int(r["Emails"]) + top * 0.04, showarrow=False,
            text=f"{float(r['Miss %']):.0f}%",
            font=dict(size=12, color="#808894" if bool(r["Thin"]) else "#f3f4f6"))
    fig.update_layout(
        barmode="stack", template="plotly_dark", plot_bgcolor="#1b1f26",
        paper_bgcolor="#1b1f26", font=dict(color="#f3f4f6", size=13),
        margin=dict(l=20, r=30, t=46, b=28), height=440, legend_title_text="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, traceorder="normal"),
        uniformtext=dict(minsize=10, mode="hide"), hovermode="x unified")
    fig.update_xaxes(categoryorder="array", categoryarray=months,
                     tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_yaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846",
                     title="Customer emails", range=[0, top * 1.16])
    if not key:
        st.plotly_chart(fig, width="stretch")
        return fig, None
    # The affordance lives inside the plot, because there is nowhere else to put it: a
    # plotly bar takes no CSS hover rule the way `clickable_kpis()`'s cards do, and a
    # line of prose under the chart is the commentary the owner removed.
    fig.add_annotation(xref="paper", yref="paper", x=1, y=1.14, showarrow=False,
                       xanchor="right", text="Click a month for its breakdown \u2192",
                       font=dict(size=11, color="#808894"))
    # Plotly's modebar floats over the top-right of the graph on hover, which is exactly
    # where the hint sits. Docked vertically it runs down the right edge instead and the
    # two stop overlapping -- cheaper than hiding the modebar, which would take the
    # download and zoom buttons with it.
    fig.update_layout(modebar=dict(orientation="v"))
    # Selected and unselected both at full opacity. Streamlit's selection styling dims
    # every bar the reader did not click, so the chart sat washed out behind the dialog
    # and stayed that way after it closed -- which reads as broken, not as a selection.
    fig.update_traces(selected=dict(marker=dict(opacity=1)),
                      unselected=dict(marker=dict(opacity=1)))
    event = st.plotly_chart(fig, width="stretch", key=key, on_select="rerun",
                            selection_mode="points")
    points = (event or {}).get("selection", {}).get("points", []) if event else []
    return fig, (str(points[0]["x"]) if points else None)


def _rgba(colour, alpha):
    r, g, b = (int(colour[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r},{g},{b},{alpha})"


def nested_donut(ring):
    """One ring of the inbox nest: the parent split on the inside, its parts outside.

    **This replaces a Sankey, which replaced three stacked bars called a funnel.** The
    thing all three were trying to draw is the same: the eight cards are three wholes
    nested inside each other, and a reader should not have to add 42 and 9 and 35 to
    check they make 86. The bars left the join implicit. The Sankey drew the join
    honestly and the owner's verdict, twice, was that it was not worth looking at.

    Two nested rings draw the join by containment instead: the outer band sits bodily
    inside the inner slice it belongs to, so 86 and 17 are visibly the two parts of the
    103 beneath them. `inbox_rings()` is what guarantees the arithmetic; this only draws
    it, and the equation is printed under the pair so the guarantee is checkable rather
    than claimed.

    **Plotly merges slices that share a label inside one trace**, which silently added
    two slices into one the first time this was built. The inner and outer rings are
    separate traces, and no two slices within either carry the same label.
    """
    if not ring or not sum(v for _, v, _ in ring["outer"]):
        st.info("Chart cannot be rendered because required fields are missing: Issue Type.")
        return None
    base = max(sum(v for _, v, _ in ring["outer"]), 1)
    fig = go.Figure()
    # The OUTER ring is drawn first so the inner one lands on top of it; plotly draws
    # traces in order and the inner ring's slice borders should sit above the outer.
    fig.add_trace(go.Pie(
        labels=[label for label, _, _ in ring["outer"]],
        values=[value for _, value, _ in ring["outer"]],
        marker=dict(colors=[colour for *_, colour in ring["outer"]],
                    line=dict(color="#1b1f26", width=2)),
        # A thin outer band -- it is the ring that carries the meaning, and a fat one
        # would swallow the parent it is supposed to sit outside of.
        hole=0.78, sort=False, direction="clockwise", rotation=0,
        text=[f"{label}<br>{value} · {value / base * 100:.0f}%"
              for label, value, _ in ring["outer"]],
        textinfo="text", textposition="outside",
        textfont=dict(size=12, color="#f3f4f6"),
        hovertemplate="<b>%{label}</b><br>%{value} of " + str(base) + "<extra></extra>",
        showlegend=False, domain=dict(x=[0, 1], y=[0, 1])))
    fig.add_trace(go.Pie(
        labels=[label for label, _, _ in ring["inner"]],
        values=[value for _, value, _ in ring["inner"]],
        marker=dict(colors=[colour for *_, colour in ring["inner"]],
                    line=dict(color="#1b1f26", width=2)),
        # A fat inner ring with a small hole: the first cut left 0.42 and the two
        # labels collided with the centre total, which is the one figure on the chart
        # that must be legible from across a room.
        hole=0.30, sort=False, direction="clockwise", rotation=0,
        # Wrapped at ten characters rather than rotated. Tangential text fits and is
        # read at an angle, which is a cost paid on the one ring a VP reads first; a
        # short label broken over two lines fits horizontally in the band's own
        # thickness and is read straight.
        text=[f"{'<br>'.join(textwrap.wrap(label, 10))}<br><b>{value}</b>"
              for label, value, _ in ring["inner"]],
        textinfo="text", textposition="inside", insidetextorientation="horizontal",
        # Per fill rather than per chart: the inner slices are deep and the outer ones
        # are not, and a label colour chosen once for the figure strands one of them.
        textfont=dict(size=12, color="#f3f4f6"),
        hovertemplate="<b>%{label}</b><br>%{value}<extra></extra>",
        showlegend=False, domain=dict(x=[0.17, 0.83], y=[0.17, 0.83])))
    total, unit = ring["centre"]
    # The unit rides in the title, not under the number. Two lines of centre text in a
    # hole this size pushed the inner ring's own labels out onto the slice borders.
    fig.add_annotation(text=f"<b>{total}</b>", x=0.5, y=0.5, showarrow=False,
                       font=dict(size=24, color="#f3f4f6"))
    fig.update_layout(
        template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
        font=dict(color="#f3f4f6", size=12), height=400,
        # Room on all four sides for the outer ring's labels, which sit outside the arc.
        margin=dict(l=96, r=96, t=58, b=58),
        # **`mode="hide"`, not plotly's default shrink.** Left to itself plotly scales a
        # label down until it fits its slice, which on the 35-slice produced 6px text --
        # present, unreadable, and worse than absent because it looks like a rendering
        # fault. A label that will not fit is dropped and its hover still carries it.
        uniformtext=dict(minsize=10, mode="hide"),
        title=dict(text=f"{ring['title']} · {total} {unit}", x=0.5, xanchor="center",
                   font=dict(size=14, color="#b6beca")))
    st.plotly_chart(fig, width="stretch")
    return fig


def _pill_title(cust, owner, label, note, notes):
    """The text of one pill's native tooltip, newline-escaped for a title attribute.

    A `title` attribute is plain text, so the structure has to come from line breaks
    (`&#10;`) rather than markup, and every value goes through `esc()` because a
    customer name or an event title is text a human typed. The failure line is dropped
    when the group carries no meaning -- the bug group prints the defects themselves
    rather than a category -- so the tooltip never opens with a dangling dash.
    """
    head = [f"{esc(cust)} &#183; {esc(owner)} fixes it"]
    if note:
        head.append(f"{esc(label)} &#8212; {esc(note)}")
    else:
        head.append(esc(label))
    blocks = []
    for stamp, title, what in notes:
        block = [esc(stamp)]
        if title:
            block.append(esc(title))
        if what:
            block.append(esc(what))
        blocks.append("&#10;".join(block))
    return "&#10;".join(head) + "&#10;&#10;" + "&#10;&#10;".join(blocks)


def fault_pills(groups, colours):
    """One tapered pill per complaint, grouped by what went wrong.

    **Seventeen records is not a bar chart.** A bar of 3 against a bar of 1 exaggerates
    a difference of two emails, and nine bars of which five are a single record is a
    table drawn as shapes -- both were built and both were rejected on sight. A pill
    per record cannot lie about length: you count them. It also carries the customer
    name for free, which is what turns the block from a count into a finding -- Eaton
    on four of the nine failures is visible here and in no aggregate.

    **The hover names the complaint, not the row it is already sitting in.** The first
    cut printed the failure, the owner and the customer -- the failure is the label at
    the head of the row and the customer is written on the pill, so two of its three
    lines told a reader what they were already looking at. It now opens with the
    account and who fixes it, then the failure and its meaning, then one block per
    complaint folded into that pill: the date the customer wrote in, the ticket to
    open, the event, and what the record says went wrong. Every line is a column, so
    none of it can go stale.

    `metrics.bulletin_errors()` draws one pill per ACCOUNT, so a slashed row such as
    `Eaton/Ford` contributes two, and folds a repeated (account, owner) into one chip
    with a count. The number on the right of each row is the record count throughout.
    """
    if not groups:
        st.info("No complaint in this view was reported and then found wrong.")
        return
    rows = []
    for label, note, pills, n in groups:
        chips = "".join(
            f"<span class='fault-pill' style='--c:{colour}' "
            f"title='{_pill_title(cust, owner, label, note, notes)}'>"
            f"{esc(cust)}{f'<b>&times;{k}</b>' if k > 1 else ''}</span>"
            for cust, owner, colour, k, notes in pills)
        rows.append(f"<div class='fault-row'>"
                    f"<div class='fault-name' title='{esc(note)}'>{esc(label)}</div>"
                    f"<div class='fault-pills'>{chips}</div>"
                    f"<div class='fault-count'>{n}</div></div>")
    key = "".join(f"<div class='fault-key'><span class='fault-swatch' style='--c:{c}'></span>"
                  f"{esc(name)}</div>" for name, c in colours)
    st.markdown("".join(rows) + f"<div class='fault-legend'>{key}</div>", unsafe_allow_html=True)


def trend_line(trend, title=""):
    """The miss rate month by month, inside its own control limits.

    **The first time-series chart on this dashboard.** Everything else is a ranked or
    stacked bar, and the question this answers -- is it getting better -- was a
    percentage printed on top of a bar for a reader to compare ten of in their head.

    The shaded band is +/- 3 sigma around the pooled rate, scaled by each month's own
    email count, so a 4-email month gets a wide band and a 19-email one a narrow band.
    A point inside its band is normal variation, drawn plain. Only a point outside is
    drawn as a signal, because a chart that reacts every month is reporting noise.
    """
    months = trend.get("months")
    if months is None or months.empty:
        st.info("Chart cannot be rendered because required fields are missing: Month.")
        return None
    x = list(months["Month"])
    fig = go.Figure()
    # The band first, so the line and its points sit on top of it.
    fig.add_scatter(x=x, y=list(months["Upper"]), mode="lines", line=dict(width=0),
                    hoverinfo="skip", showlegend=False)
    # **A very light wash, with the lower edge drawn as a real line.** At 0.16 the band
    # filled the plot: 3 sigma on 4-19 emails a month pins the UPPER limit at 100% in
    # nine months of ten, so the fill ran from the lower limit to the ceiling and read
    # as a rendering fault rather than a band -- the thin months drew as solid dark
    # columns. The statistics are unchanged and the width is real; only its visual
    # weight came down, and the one edge that can actually be crossed is now the one you
    # can see.
    fig.add_scatter(x=x, y=list(months["Lower"]), mode="lines",
                    line=dict(color=CAT_SLATE, width=1.5, dash="dash"),
                    fill="tonexty", fillcolor=_rgba(CAT_SLATE, 0.07),
                    name="Usual swing", hoverinfo="skip")
    fig.add_scatter(x=x, y=[trend["centre"]] * len(x), mode="lines",
                    line=dict(color=CAT_SLATE, width=1, dash="dot"),
                    name=f"Year average {trend['centre']:.0f}%", hoverinfo="skip")
    fig.add_scatter(
        x=x, y=list(months["Rate"]), mode="lines+markers+text",
        line=dict(color=BLUE_RAMP[4], width=2.5),
        marker=dict(size=[13 if o else 8 for o in months["Outside"]],
                    color=[ROOT_COLOURS["People"] if o else BLUE_RAMP[4]
                           for o in months["Outside"]],
                    line=dict(color="#1b1f26", width=2)),
        text=[f"{r:.0f}%" for r in months["Rate"]], textposition="top center",
        textfont=dict(size=11, color="#b6beca"),
        customdata=[[int(m), int(e)] for m, e in zip(months["Misses"], months["Emails"])],
        name="Miss rate each month",
        hovertemplate="%{y:.0f}% — %{customdata[0]} of %{customdata[1]} emails<extra></extra>")
    fig.update_layout(
        template="plotly_dark", plot_bgcolor="#1b1f26", paper_bgcolor="#1b1f26",
        font=dict(color="#f3f4f6", size=13), height=380, title=title,
        margin=dict(l=20, r=30, t=52, b=28), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, traceorder="normal"))
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_yaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846",
                     title="Miss rate", ticksuffix="%", range=[0, 112])
    st.plotly_chart(fig, width="stretch")
    return fig


def _on_fill(colour):
    """`--panel` or `--ink` for a label sitting ON a fill, whichever has the contrast.

    The house rule is that an in-bar label wears `--panel` -- white on `--red` is 2.2:1
    where dark is 6.9:1. That is right for every light fill and exactly wrong for a dark
    one, and these charts carry both. Deciding per fill rather than per chart means a
    palette edit cannot silently strand a label on a fill it no longer suits.
    """
    try:
        r, g, b = (int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
    except (ValueError, IndexError):
        return "#1b1f26"
    chan = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in (r, g, b)]
    lum = 0.2126 * chan[0] + 0.7152 * chan[1] + 0.0722 * chan[2]
    return "#f3f4f6" if (lum + 0.05) / 0.062 < 0.945 / (lum + 0.05) else "#1b1f26"


def flow_bar(frame, label_col, title="", x_title="Customer emails"):
    """A horizontal bar split the way the month chart splits a month.

    Same five segments, same colours, same order, straight off `MONTH_PARTS` -- so a
    Product miss is the same blue here, on the month chart and on the cards, and a
    reader who has learned the month chart has already learned this one. It replaced
    two bar charts of the same categories ranked two different ways, which is a block
    that asks the reader to do the join the chart should have done.
    """
    if frame is None or frame.empty:
        st.info(f"Chart cannot be rendered because required fields are missing: {label_col}.")
        return None
    rows = list(frame[label_col].astype(str))
    widest = max([int(v) for v in frame["Emails"]] or [1])
    floor = max(widest * 0.045, 1.5)
    fig = go.Figure()
    for part, colour, meaning in MONTH_PARTS:
        if part not in frame.columns:
            continue
        values = [int(v) for v in frame[part]]
        if not any(values):
            continue
        fig.add_bar(
            y=rows, x=values, orientation="h", name=MONTH_NAMES.get(part, part),
            marker=dict(color=colour, line=dict(width=0)),
            text=[str(v) if v >= floor else "" for v in values],
            textposition="inside", insidetextanchor="middle",
            textfont=dict(size=12, color=_on_fill(colour)),
            hovertemplate="%{x} " + esc(MONTH_NAMES.get(part, part).lower())
                          + f" — {esc(meaning)}<extra></extra>")
    fig.update_layout(
        barmode="stack", template="plotly_dark", plot_bgcolor="#1b1f26",
        paper_bgcolor="#1b1f26", font=dict(color="#f3f4f6", size=13), title=title,
        margin=dict(l=20, r=40, t=54, b=28), legend_title_text="",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, traceorder="normal"),
        uniformtext=dict(minsize=9, mode="hide"), hovermode="y unified",
        # The cap was 760px when this drew a top twelve. It draws all twenty-six now,
        # and 760 squeezed them to 24px a row with the labels colliding. A long ranked
        # list is the honest shape -- the alternative was the silent head this replaced.
        height=max(340, min(1180, len(rows) * 30 + 150)))
    # Longest bar at the top. Plotly builds a category axis bottom-up, so the frame's
    # own order (already sorted by misses) is reversed here rather than in the data.
    fig.update_yaxes(categoryorder="array", categoryarray=list(reversed(rows)),
                     tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846", title="")
    fig.update_xaxes(tickfont=dict(size=12, color="#f3f4f6"), gridcolor="#303846",
                     title=x_title)
    st.plotly_chart(fig, width="stretch")
    return fig
