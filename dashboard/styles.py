"""Shared CSS and the visual constants every chart draws from.

`RED_BLUE` and `BLUE_RAMP` are the app's only chart palette: no view introduces a hue
of its own, which is the rule that keeps the pages reading as one product.
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

from dashboard.config import NAV_GROUPS, PAGES



CSS = """
<style>
:root{--bg:#0f1115;--panel:#1b1f26;--panel2:#202631;--ink:#f3f4f6;--muted:#b6beca;--line:#3a414d;--line2:#515a68;--slate:#8a94a8;--blue:#8ab4f8;--teal:#80cbc4;--amber:#f6c177;--red:#f28b82;--green:#a8dab5}
html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"]{background:var(--bg)!important;color:var(--ink)!important}.main .block-container{padding-top:.75rem;max-width:1450px;background:var(--bg)!important}[data-testid="stHeader"],[data-testid="stToolbar"]{background:#0c0e12!important}[data-testid="stSidebar"]{background:var(--bg)!important;border-right:1px solid var(--line)}[data-testid="stSidebar"] *{color:var(--ink)!important}[data-testid="stSidebar"] label{color:var(--muted)!important}
[data-testid="stSidebar"] div[role="radiogroup"]{gap:0!important;margin-top:4px}[data-testid="stSidebar"] label[data-testid="stRadioOption"]{width:100%;box-sizing:border-box;background:transparent!important;border:0!important;border-left:3px solid color-mix(in srgb,var(--nav,var(--blue)) 42%,transparent)!important;border-radius:0!important;padding:11px 16px!important;margin:0!important;display:flex!important;align-items:center!important;box-shadow:none!important;cursor:pointer;transition:background .12s ease,border-left-color .12s ease}[data-testid="stSidebar"] label[data-testid="stRadioOption"]:hover{background:color-mix(in srgb,var(--nav,var(--blue)) 9%,transparent)!important;border-left-color:var(--nav,var(--blue))!important}[data-testid="stSidebar"] label[data-testid="stRadioOption"] p{font-size:13.5px!important;font-weight:500!important;color:var(--muted)!important;margin:0!important;line-height:1.3}[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"]{border-left-color:var(--nav,var(--blue))!important;background:color-mix(in srgb,var(--nav,var(--blue)) 15%,transparent)!important}[data-testid="stSidebar"] label[data-testid="stRadioOption"][data-selected="true"] p{color:#fff!important;font-weight:700!important}[data-testid="stSidebar"] label[data-testid="stRadioOption"] div:has(+[data-testid="stMarkdownContainer"]){display:none!important}[data-testid="stSidebar"] label[data-testid="stRadioOption"] input{display:none!important}
h1,h2,h3,h4,h5,h6,p,span,div,label{color:var(--ink)!important}.page-hero,.section-card,.kpi,.insight-box,.excel-table.wide{width:auto;min-width:100%}.excel-table.wide td,.excel-table.wide th{white-space:nowrap}.excel-table.wide td:first-child{overflow-wrap:normal}.excel-table.wide td.wrap,.excel-table.wide th.wrap{white-space:normal;overflow-wrap:anywhere;text-align:left;min-width:280px;max-width:520px;vertical-align:top}.excel-table.record td{text-align:left;overflow-wrap:anywhere;white-space:normal}.excel-table.record td:first-child{width:220px;color:var(--muted)!important;font-weight:700}.definition-group{background:var(--panel)!important;border:1px solid var(--line);box-shadow:0 2px 8px rgba(0,0,0,.28)}.page-hero{position:relative;overflow:hidden;border-left:5px solid var(--accent,var(--blue));padding:14px 18px;margin-bottom:16px}.page-hero:after{content:"";position:absolute;inset:0;background:linear-gradient(120deg,rgba(255,255,255,.05),transparent 55%);pointer-events:none}.page-kicker{display:flex;align-items:center;gap:7px;font-size:11px;font-weight:800;letter-spacing:.09em;text-transform:uppercase;color:var(--accent,var(--blue))!important;margin-bottom:5px}.page-kicker .dot{width:7px;height:7px;border-radius:50%;background:var(--accent,var(--blue));box-shadow:0 0 0 3px color-mix(in srgb,var(--accent,var(--blue)) 25%,transparent)}.page-hero h1{margin:0 0 4px 0;font-size:25px}.page-hero p,.section-card p{margin:0;color:var(--muted)!important;font-size:14px;line-height:1.4}.section-card{border-left:4px solid var(--accent,var(--blue));border-radius:8px;padding:12px 14px;margin:18px 0 10px;display:flex;flex-direction:column;gap:2px}.section-card h3{margin:0 0 2px 0;font-size:20px;display:flex;align-items:center;gap:8px}.section-card h3:before{content:"";width:9px;height:9px;border-radius:3px;background:var(--accent,var(--blue));display:inline-block;flex:none}.kpi-grid{display:grid;grid-template-columns:repeat(5,minmax(145px,1fr));gap:10px;margin:10px 0 14px}.kpi{position:relative;min-height:92px;border-top:4px solid var(--accent);border-radius:8px;padding:11px 13px;transition:transform .15s ease,box-shadow .15s ease}.kpi:hover{transform:translateY(-3px);box-shadow:0 10px 22px rgba(0,0,0,.4)}.kpi-label{font-size:11px;color:var(--muted)!important;font-weight:800;text-transform:uppercase;letter-spacing:.04em}.kpi-num{font-size:29px;font-weight:900;line-height:1.05;margin:6px 0 4px;background:linear-gradient(180deg,#fff,var(--ink));-webkit-background-clip:text;background-clip:text}.kpi-foot{font-size:12px;color:var(--muted)!important}.section-rule{height:1px;background:var(--line);margin:30px 0 14px}
.root-card{background:var(--panel)!important;border:1px solid var(--line);border-top:5px solid var(--accent);border-radius:10px;padding:14px 16px;box-shadow:0 2px 10px rgba(0,0,0,.3);min-height:150px}.root-card .rc-name{font-size:12px;font-weight:900;letter-spacing:.07em;text-transform:uppercase;color:var(--accent)!important}.root-card .rc-num{font-size:42px;font-weight:900;line-height:1.02;margin:8px 0 0}.root-card .rc-base{font-size:13px;color:var(--muted)!important;font-weight:700}.root-card .rc-share{display:inline-block;margin-top:8px;font-size:15px;font-weight:900;color:var(--accent)!important}.root-card .rc-desc{font-size:13px;color:var(--muted)!important;margin-top:8px;line-height:1.35}
.takeaway{border-left:4px solid var(--accent,var(--blue));background:var(--panel)!important;border-radius:8px;padding:13px 15px;margin:14px 0 4px;font-size:15px;line-height:1.45}.takeaway b{color:var(--accent,var(--blue))!important}
.insight-row{display:grid;grid-template-columns:repeat(2,minmax(260px,1fr));gap:10px}.insight-box{border-left:4px solid var(--accent);border-radius:8px;padding:11px 12px;font-size:14px}
.table-wrap{overflow-x:auto;border-radius:8px;border:1px solid var(--line);box-shadow:0 2px 8px rgba(0,0,0,.22)}.excel-table{width:100%;border-collapse:collapse;background:var(--panel)!important;font-size:13px}.excel-table th{background:#2d3542!important;color:#fff!important;border:1px solid var(--line2);padding:9px 10px;text-align:center;font-weight:800;font-size:12px;text-transform:uppercase;letter-spacing:.03em;position:sticky;top:0}.excel-table td{border:1px solid var(--line);padding:8px 10px;background:#1f242d!important;color:var(--ink)!important;font-size:13px}.excel-table tr:nth-child(even) td{background:#242a34!important}.excel-table tbody tr{transition:background .1s ease}.excel-table tbody tr:hover td{background:#2c3542!important}.excel-table td:first-child{text-align:left;overflow-wrap:anywhere;font-weight:600}.excel-table td:not(:first-child){text-align:center}.bar-cell{padding:0!important}.bar-box{position:relative;min-height:32px;display:flex;align-items:center;justify-content:center;overflow:hidden;border-radius:4px}.bar-box:before{content:"";position:absolute;inset:0 auto 0 0;width:var(--w);background:linear-gradient(90deg,rgba(138,180,248,.7),rgba(138,180,248,.18))}.bar-box span{position:relative;z-index:1;font-weight:900;color:#fff!important;text-shadow:0 1px 2px #000}.definition-group{border-left:4px solid var(--teal);border-radius:8px;padding:12px 14px;margin:12px 0}.stDownloadButton button,.stButton button,.stFormSubmitButton button{background:#374151!important;color:#fff!important;border:1px solid var(--blue)!important;border-radius:7px!important;font-weight:800!important;transition:border-color .15s ease,transform .1s ease}.stDownloadButton button:hover,.stButton button:hover,.stFormSubmitButton button:hover{border-color:var(--teal)!important;transform:translateY(-1px)}[data-testid="stDataFrame"],[data-testid="stTable"]{background:var(--panel)!important;border:1px solid var(--line)!important;border-radius:8px!important;overflow:hidden}
/* The Complaint Tracker's reading grid. It is `.wide` plus a restyle, so the sideways
   scroll and the bounded wrap columns still come from there. A full box grid, centred
   text and zebra fills read as a spreadsheet export rather than a table someone is meant
   to read: with rows of very unequal height -- one wrapped Comments cell can be five
   lines against a neighbour's one -- the vertical rules draw ragged columns and the
   alternating fills emphasise the raggedness. Hairline row separators and a hover band
   carry the row instead. Cells align top so a short value sits beside the first line of
   a long one rather than floating in the middle of it, and the first column is sticky so
   the month stays on screen through twenty-six columns of sideways scroll. */
.excel-table.grid{border-collapse:separate;border-spacing:0;background:transparent!important}
.excel-table.grid th{background:#161a21!important;border:0;border-bottom:1px solid var(--line2);padding:11px 15px;text-align:left;font-size:10.5px;letter-spacing:.075em;color:var(--muted)!important;font-weight:800}
.excel-table.grid td{--cell-bg:#0f1115;border:0;border-bottom:1px solid rgba(58,65,77,.5);padding:11px 15px;background:transparent!important;text-align:left;vertical-align:top;line-height:1.5}
.excel-table.grid tr:nth-child(even) td{background:transparent!important}
.excel-table.grid tbody tr:hover td{--cell-bg:#181d27;background:rgba(138,180,248,.06)!important}
.excel-table.grid tbody tr:last-child td{border-bottom:0}
.excel-table.grid th:first-child,.excel-table.grid td:first-child{position:sticky;left:0;z-index:2;background:#161a21!important;border-right:1px solid var(--line);white-space:nowrap;font-weight:700}
.excel-table.grid td:first-child.wrapcol,.excel-table.grid th:first-child.wrapcol{white-space:normal;min-width:140px;max-width:170px}
.excel-table.grid th:first-child{z-index:4}
.excel-table.grid tbody tr:hover td:first-child{background:#1d232c!important}
.excel-table.grid td.num{font-variant-numeric:tabular-nums;color:var(--muted)!important}
.excel-table.grid td.key{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;letter-spacing:-.01em}
.excel-table.grid td.wrap{min-width:320px;max-width:600px;color:var(--muted)!important}
.excel-table.grid td.wrap.narrow,.excel-table.grid th.wrap.narrow{min-width:170px;max-width:200px}
.excel-table.grid td.wrap.mid,.excel-table.grid th.wrap.mid{min-width:220px;max-width:260px}
.excel-table.grid td.wrap.bullets{white-space:pre-line}
.excel-table td.nowrap,.excel-table th.nowrap{white-space:nowrap}
.excel-table.roomy td{padding:12px 14px;font-size:13.5px;line-height:1.5}.excel-table.roomy th{padding:11px 14px;font-size:11px;letter-spacing:.06em}.excel-table.roomy td:first-child{font-weight:700;font-size:14px;line-height:1.4;padding-right:18px}.excel-table.roomy td.wrap,.excel-table.roomy th.wrap{text-align:left;font-weight:400;color:var(--muted)!important}.excel-table.roomy td:not(:first-child):not(.wrap){font-variant-numeric:tabular-nums}.excel-table.wide.roomy td.wrap,.excel-table.wide.roomy th.wrap{min-width:340px;max-width:640px}.excel-table.wide.roomy td.wrap.tight,.excel-table.wide.roomy th.wrap.tight{min-width:150px;max-width:190px}.owner-pill{display:inline-flex;align-items:baseline;gap:5px;padding:2px 9px;margin:1px 4px 1px 0;border-radius:999px;font-size:11.5px;font-weight:800;letter-spacing:.02em;white-space:nowrap;background:color-mix(in srgb,var(--c) 15%,transparent);border:1px solid color-mix(in srgb,var(--c) 40%,transparent)}.excel-table td .owner-pill,.excel-table td .owner-pill b{color:var(--c)!important}.excel-table td .owner-pill b{font-weight:900;font-size:12.5px}.excel-table td.owners{text-align:left!important;white-space:normal}.excel-table tbody tr.total td{background:#1a202a!important;border-top:2px solid var(--line2);font-weight:800;color:var(--ink)!important}.excel-table.stickytotal tbody tr.total td{position:sticky;bottom:0;z-index:2;box-shadow:0 -2px 6px rgba(0,0,0,.45)}.excel-table tbody tr.total td .bar-box:before{opacity:.35}
.excel-table.grid tbody tr.total td{--cell-bg:#1a202a;background:#1a202a!important;border-top:2px solid var(--line2);border-bottom:0;font-weight:800;color:var(--ink)!important}
.excel-table.grid td.wrap>.cell{max-height:100px;overflow-y:auto;background:linear-gradient(var(--cell-bg) 32%,rgba(0,0,0,0)) top/100% 22px no-repeat local,linear-gradient(rgba(0,0,0,0),var(--cell-bg) 68%) bottom/100% 22px no-repeat local,radial-gradient(farthest-side at 50% 0,rgba(138,180,248,.42),rgba(0,0,0,0)) top/100% 11px no-repeat,radial-gradient(farthest-side at 50% 100%,rgba(138,180,248,.42),rgba(0,0,0,0)) bottom/100% 11px no-repeat}
.excel-table.grid td.wrap>.cell::-webkit-scrollbar{width:8px}
.excel-table.grid td.wrap>.cell::-webkit-scrollbar-thumb{background:var(--line2);border-radius:4px;border:2px solid transparent;background-clip:content-box}
.excel-table.grid td.wrap>.cell::-webkit-scrollbar-track{background:rgba(255,255,255,.04);border-radius:4px}
@media(max-width:1200px){.kpi-grid{grid-template-columns:repeat(2,minmax(180px,1fr))}.insight-row{grid-template-columns:1fr}}@media(max-width:760px){.kpi-grid{grid-template-columns:1fr}}
/* The card popups. One anatomy on all eight; colour carries only who fixes it, and
   every stat card prints its own number and label so nothing rests on colour alone.
   The number leads and the label sits under it -- the version this replaced ran the
   label across the panel with the figure stranded at the right edge, which is the
   arrangement where the words are read and the number is not. */
.pop{display:flex;flex-direction:column;gap:15px;font-size:14px}
.pop-chain{font-size:11px;color:var(--muted)!important;border-bottom:1px solid var(--line);padding-bottom:11px}
.pop-chain .pop-here{color:var(--ink)!important;font-weight:700}
.pop-chain .pop-sep{color:var(--line2)!important;margin:0 3px}
.pop-q{font-size:19px;font-weight:700;line-height:1.3}
.pop-hero{display:flex;align-items:baseline;gap:13px}
.pop-num{font-size:46px;font-weight:900;line-height:1}
.pop-base{font-size:13px;color:var(--muted)!important;line-height:1.35}
.pop-lead{font-size:14.5px;line-height:1.5;font-weight:600;border-left:3px solid var(--accent);padding-left:12px}
.pop-rule{height:1px;background:var(--line)}
.pop-stack{display:flex;gap:2px;height:12px;border-radius:4px;overflow:hidden}
.pop-stack span{display:block}
.pop-keys{display:flex;flex-wrap:wrap;gap:16px;font-size:11px;color:var(--muted)!important;margin-top:-6px}
.pop-key{display:inline-flex;align-items:center;gap:6px}
.pop-key i{width:9px;height:9px;border-radius:3px;display:inline-block;flex:none}
/* A fixed-column grid, not a flex row: five cards over three columns read as 3 + 2 of
   equal width, where a flex row stretches the trailing two to half the panel each and
   makes a 1 look like an 8. */
.pop-stats{display:grid;grid-template-columns:repeat(var(--cols),minmax(0,1fr));gap:10px}
.pop-stat{background:var(--panel2)!important;border-top:3px solid var(--c);border-radius:8px;padding:12px 13px}
.pop-sv{font-size:28px;font-weight:900;line-height:1;font-variant-numeric:tabular-nums}
.pop-sl{font-size:12.5px;font-weight:600;line-height:1.35;margin-top:6px}
.pop-sn{font-size:10.5px;color:var(--muted)!important;line-height:1.35;margin-top:6px}
.pop-bars{display:flex;flex-direction:column;gap:8px}
.pop-bar{display:flex;align-items:center;gap:11px}
.pop-bname{font-size:12px;color:var(--muted)!important;width:30px;flex:none}
.pop-track{flex:1 1 auto;height:10px;background:rgba(255,255,255,.05);border-radius:0 4px 4px 0}
.pop-fill{display:block;height:100%;border-radius:0 4px 4px 0}
.pop-bval{font-size:12px;font-weight:700;width:34px;text-align:right;font-variant-numeric:tabular-nums}
.pop-bnote{font-size:11px;color:var(--muted)!important;width:46px;text-align:right;font-variant-numeric:tabular-nums}
.pop-foot{display:flex;justify-content:space-between;align-items:baseline;gap:14px;flex-wrap:wrap;
  font-size:12px;color:var(--muted)!important;border-top:1px solid var(--line);padding-top:12px}
.pop-eq{font-size:13px;font-weight:800;color:var(--ink)!important;font-variant-numeric:tabular-nums}
/* The trigger strip reads as the card's own footer rather than a control bolted under
   it: panel ground, a hairline above, and the card's bottom corners. */
/* The whole card is the click target. A real `st.button` is laid over the card and
   made invisible: the click stays inside the session, so the sidebar filters survive
   it, where an `<a href="?card=...">` would navigate, hand back a fresh session and
   clear every filter. The label is hidden with a transparent colour and a zero font
   size rather than removed, so a screen reader still announces the card it opens.
   Every property carries `!important` because Streamlit's own rule is
   `.stButton > button` -- specificity (0,2,1) against the (0,1,1) of a `.st-key-...`
   descendant, which is why the first cut rendered as a default blue pill. */
.st-key-kpi-row-1 [data-testid="stHorizontalBlock"],.st-key-kpi-row-2 [data-testid="stHorizontalBlock"]{gap:10px!important}
.st-key-kpi-row-1,.st-key-kpi-row-2{margin:10px 0 14px}
/* `display:block` and `gap:0` on the hit container, and `height:auto` on the element
   container Streamlit wraps the card in: the vertical block reserves its 16px row gap
   and Streamlit sizes the element container itself, and between them the container
   stayed 16px shorter than the card it holds -- which is exactly how far the click
   target fell short of the card's bottom edge, twice, before this was measured rather
   than assumed. */
/* The card and the container that positions its overlay are pinned to ONE height,
   `--kpi-h`, instead of letting the overlay inherit whatever Streamlit measured.
   Three attempts at the latter each landed 16px short: Streamlit lays the markdown
   out through a flex wrapper with a definite height, the card overflowed it, and
   every ancestor came back under the card -- so the bottom strip of each card was
   not clickable. Matching two heights that this stylesheet owns is the version that
   cannot be broken by a Streamlit release renaming a wrapper. */
[class*="st-key-kpi-hit-"]{--kpi-h:118px;position:relative;display:block!important;gap:0!important;height:var(--kpi-h)}
[class*="st-key-kpi-hit-"]>[data-testid="stElementContainer"]{height:var(--kpi-h)!important;min-height:0!important}
/* `height:100%` here resolved against an auto-height parent, so it was ignored, the
   card grew to its content and its own container stayed 16px shorter -- which is
   exactly how far the click target fell short of the card's bottom edge. A min-height
   instead keeps the row even and lets the container wrap the card exactly. */
[class*="st-key-kpi-hit-"] .kpi{height:var(--kpi-h);min-height:0;box-sizing:border-box}
/* The ELEMENT CONTAINER is what gets positioned, not `.stButton` inside it. Streamlit
   gives `.stElementContainer` its own `position:relative`, so an absolutely placed
   `.stButton` resolves against that container -- which sits in flow below the card --
   and the overlay rendered as a 2px sliver underneath instead of covering anything.
   The container carries the button's own `key` as a class, which is what this targets. */
[class*="st-key-kpi-open-"]{position:absolute!important;top:0!important;left:0!important;right:0!important;height:var(--kpi-h)!important;margin:0!important;width:auto!important;z-index:3}
[class*="st-key-kpi-open-"] .stButton{width:100%!important;height:100%!important}
[class*="st-key-kpi-hit-"] .stButton>button{width:100%!important;height:100%!important;min-height:0!important;background:transparent!important;border:1px solid transparent!important;border-radius:8px!important;box-shadow:none!important;padding:0!important;font-size:0!important;color:transparent!important;cursor:pointer}
[class*="st-key-kpi-hit-"] .stButton>button p{font-size:0!important;color:transparent!important;line-height:0!important}
[class*="st-key-kpi-hit-"]:hover .kpi{transform:translateY(-3px);box-shadow:0 10px 22px rgba(0,0,0,.4)}
[class*="st-key-kpi-hit-"]:hover .kpi:after{content:"Break it down \\2192";position:absolute;right:12px;bottom:9px;font-size:10px;font-weight:800;letter-spacing:.06em;text-transform:uppercase;color:var(--accent)}
[class*="st-key-kpi-hit-"] .stButton>button:focus-visible{border-color:var(--accent,var(--blue))!important;outline:2px solid var(--accent,var(--blue))!important;outline-offset:2px}
</style>
"""
NAV_ACCENT = {page: colour for colour, names in NAV_GROUPS.values() for page in names}
NAV_CSS = "".join(
    f'[data-testid="stSidebar"] div[role="radiogroup"]>label:nth-of-type({i + 1})'
    f'{{--nav:{NAV_ACCENT.get(name, "#b6beca")}}}'
    for i, name in enumerate(PAGES))


def esc(v):
    return html.escape(str(v)) if pd.notna(v) else ""

GRID_STYLES = {"Email/JIRA Date": "num", "Resolution Date": "num", "Delay (Hours)": "num",
               "Month_Sort": "num", "Number of Customers": "num", "Jira Key": "key"}

WRAP_COLUMNS = ("Event/Bulletin Title", "Reason", "What went wrong", "Automation Opportunity",
                "Comments", "RCA Details")


# The app's own CSS tokens, not new hues. Every chart on every page draws from --blue,
# --amber and --red, and a new page in a different set of blues reads as a different
# product even when each chart is individually fine; one palette across the dashboard
# beats a locally optimal one. BLUE_RAMP is --panel graded up to --blue, so the heatmap
# sits on the same surface the panels do.
#
# The pair that matters is still checked: --red against --blue scores CVD dE 17.0
# (protan) and 21.1 to normal vision through scripts/validate_palette.js, comfortably
# clear of the dE 8 floor. What is deliberately NOT used is the obvious red/green for
# rising and falling, which collapses to dE 3.6 under deuteranopia -- direction carries
# a signed label too, so it never rests on colour alone.
RED_BLUE = ("#f28b82", "#8ab4f8")           # --red, --blue
BLUE_RAMP = ["#1b1f26", "#24384f", "#2f5580", "#4e7bb8", "#8ab4f8"]   # --panel -> --blue


TAGS = re.compile(r"<[^>]+>")

# Who owns the fix, in the same three colours everywhere they appear on the page.
ROOT_COLOURS = {"Product": "#8ab4f8", "People": "#f28b82", "Process": "#f6c177"}

# **A grey is chrome OR a category, never both.** That rule exists because the opposite
# shipped: `--line2` was the fill for `Reported, but wrong` -- a real category, 17
# emails -- *and* the colour of every table border, header rule and scrollbar thumb on
# the dashboard. A category wearing the border colour reads as furniture, which is
# exactly what a reader reported: too many greys, none of them clearly meaning anything.
#
# `--slate` is the one grey that is a CATEGORY and appears nowhere as chrome. It is
# 5.4:1 against `--panel`, so it reads as a deliberate fill rather than a rule, and
# 2.3:1 clear of `--line2`, so the two can never be confused.
#
# `Reported, but wrong` is owner-NEUTRAL on purpose and that is a data fact, not a
# style preference: those 17 emails are 9 Product, 7 People and 1 Process. Painting
# them `--red` would print "analyst" over nine Product-rooted records. Any segment
# spanning every owner has to take a colour that names none of them.
CAT_SLATE = "#8a94a8"

# `--muted` carried three unrelated jobs -- secondary text, "an owner we could not
# identify", and a fallback fill for anything unmapped. It keeps the first two. The
# third is gone: an unmapped category now surfaces under its own name rather than
# borrowing the colour of the page's quiet text.
UNKNOWN_OWNER = "#b6beca"


# The two style blocks the entry point injects, in the order it injects them: the base
# stylesheet first, then the per-group navigation accent that depends on `PAGES`. They
# are a list rather than two module-level `st.markdown` calls because a module that
# writes to the page on import cannot be imported by a script or a test.
CSS_BLOCKS = (CSS, f"<style>{NAV_CSS}</style>")
