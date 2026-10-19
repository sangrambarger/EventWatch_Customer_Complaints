# EventWatch Customer Complaints

Streamlit dashboard over a complaint tracker that exists in two synced forms:
`customer_tracker.csv` (preferred source) and `EventWatch_Customer_Complaints_2026.xlsx`
(Data sheet + a live Dashboard).

`app.py` hardcodes no owner, repo or branch. `data_sources()` resolves, in order:
`GITHUB_CSV_URL`/`GITHUB_WORKBOOK_URL` (secret or env), then the data files sitting
next to `app.py` (the zero-config path a Streamlit Cloud deploy takes), then a raw URL
built from `GITHUB_REPO` + `GITHUB_BRANCH`. `scripts/smoke_app.py` deliberately writes
no secrets so it exercises that middle path.

## The shape of the code

`app.py` is **61 lines** and holds no logic: configuration, the data load, the one shared
filter call, navigation, and a dict from page name to page module. It was 3,389 lines,
which is why nobody could find the rule behind a figure without reading the lot.

| Module | What lives there |
| --- | --- |
| `dashboard/config.py` | titles, `PAGES`, `DESCRIPTIONS`, `NAV_GROUPS`, where the data sits |
| `dashboard/styles.py` | `CSS`, `NAV_CSS`, `RED_BLUE`, `BLUE_RAMP`, `ROOT_COLOURS`, `esc()` |
| `dashboard/taxonomy.py` | `PLAIN_SUBTYPE`, `OWNED_SUBTYPE`, `failure_label`, `DRIVERS`, `REASON_CATEGORIES`, `owner_pills` |
| `dashboard/data.py` | `data_sources()`, `load_data()` |
| `dashboard/filters.py` | `sidebar_filters()`, `date_filter()`, `customer_names()` |
| `dashboard/metrics.py` | every number: miss buckets, exposure, totals, trend windows, reconciliation |
| `dashboard/components.py` | cards, tables, charts, page furniture -- drawing only, no arithmetic |
| `dashboard/staging.py` | the All customer emails entry form and its session rows |
| `dashboard/sections.py` | the `render_*` sections the summary and the internal pages share |
| `dashboard/pages/` | one module per page, each exposing `render(df, filtered, selected_page)` |

**The import graph is strictly one-way** and there is no cycle:

```
config -> styles -> taxonomy -> filters -> metrics -> components -> staging
                         \__________________________________________> sections -> pages
```

Two placements are load-bearing rather than tidy. `esc()` sits in `styles` because
`owner_pills()` is the one function that writes HTML into a cell, and it belongs with the
classification vocabulary in `taxonomy`; putting `esc` in `components` would make
`taxonomy` import from `components` and close a loop. `source_page()` sits in `sections`,
not `components`, because it calls the section renderers -- in `components` it dragged
`sections` back in the other direction. **If a new import makes the graph bidirectional,
the symbol is in the wrong module; move the symbol, do not add a function-local import.**

**`dashboard/pages/` is inside the package on purpose.** Streamlit auto-discovers a
`pages/` directory sitting **next to the entry point** and turns every file in it into a
page of its own, which would draw a second navigation beside the one `PAGES` builds.
Inside the package it is an ordinary module directory and Streamlit never looks at it.
Do not move it to the repository root.

**`APP_DIR` is `Path(__file__).resolve().parent.parent`, and the second `.parent` is the
whole point.** `data_sources()` looks for the tracker beside the *entry point*, which is
the zero-config path a Streamlit Cloud deploy takes. Written the obvious way inside
`dashboard/config.py` it points at `dashboard/`, finds nothing, and every page renders
"No data source found" -- which is exactly what happened on the first run of the
refactored app, and what `smoke_app.py` caught.

**`validate.py` and `audit_pages.py` import from `dashboard.taxonomy`, not from `app.py`.**
They used to do `from app import REASON_CATEGORIES`, which executed the entire Streamlit
application to read a dict. One copy of each map, and a gate that no longer has to boot a
web app to check a value.

**The refactor was proved, not asserted.** Before it, the rendered text of all seven pages
and the sidebar was captured from the DOM -- 171 KB -- and all four gates were recorded.
After it, both were identical byte for byte. **Any further structural change here should
clear the same bar**: snapshot the pages first, refactor, diff. A green gate alone does
not prove a layout or a wording survived.

**The tracker read is cached; the sidebar lines around it are not.**
`read_tracker(src, fingerprint)` carries `@st.cache_data` and is deliberately free of
Streamlit calls -- a cached function replays the elements written inside it, so caching
`load_data()` whole would have made the cache responsible for the four sidebar lines as
well as the data. Streamlit reruns the whole script on every click, so before this every
interaction re-read and re-parsed the file: ~10ms against a local checkout, and a full
HTTP round trip on a deploy whose source is a URL, paid on every filter change, every
page click and every keystroke in the search box. Measured after: 1.6ms.

**`source_fingerprint()` is `(mtime, size)`, and it is why the cache is safe to keep.**
The source path alone never changes, so without it a tracker edited on disk would go on
serving whatever the process first read -- and `audit_pages.py` and `smoke_app.py` would
check a stale frame. A URL has nothing cheap to fingerprint and caches for the life of
the process, which is what a Cloud deploy wants: a redeploy restarts it.

## Run these before exploring by hand

```bash
python3 scripts/validate.py                 # data + workbook integrity, exits non-zero on failure
python3 scripts/smoke_app.py                # loads all 7 pages, flags exceptions/empty charts
python3 scripts/jira_sync.py                # EAO tickets vs tracker, prints only the delta
python3 scripts/jira_sync.py --describe EAO-7 EAO-9   # bodies, when prose judgement is needed
python3 scripts/refresh_caches.py --dry-run # what in the workbook has drifted from the CSV
python3 scripts/refresh_caches.py           # rewrite the drifted caches
python3 scripts/sort_tracker.py Jul Aug     # put those months back in date order, both files
python3 scripts/sort_tracker.py --all       # ...or the whole tracker
python3 scripts/selftest.py                 # prove each validate.py rule still fires
python3 scripts/audit_pages.py              # every rendered figure vs the tracker, page by page
python3 scripts/export_definitions.py       # regenerate definitions.json from the workbook sheet
python3 scripts/append_row.py --json r.json # add one record to the CSV and the Data sheet together
python3 scripts/update_row.py --json c.json # change fields on records already in both files
python3 scripts/delete_row.py --json d.json # remove records from both files, renumbering the sheet
python3 scripts/add_definition.py --json t.json # document a new taxonomy value on the Definitions sheet
```

`validate.py` covers every bug class that has actually shipped here: characters decayed
to `?` (both shapes — beside a letter, and standing alone between words where an arrow
was lost), records sitting in the wrong month, a status value the Dashboard's fixed
tables don't list (so it silently drops from a chart total), a month with records but no
row in the monthly trend block, CSV/workbook drift on **any** shared column, stripped
dynamic-array metadata, stale caches, a `ComplaintTracker` table ref left short after an
append (which silently undercounts every Dashboard COUNTIFS), Data rows appended in
a different font, the same complaint logged twice, a tracker column with no row in the
workbook's own data dictionary, a resolution date that contradicts
its own record (dated but still `Pending`, or dated before the record was raised --
a negative cycle time), an enumerated *value* in use with no row in that
dictionary (six event types, four reason labels and the `Pending` fix status were all
in circulation undefined), a `DefinitionsTable` ref left short after an append, and a
`ComplaintTracker[...]` reference on any sheet
naming a column that no longer exists (which turns the Management Readout -- twelve
formulas, no cached values -- into #REF! on next open). Read its output instead of re-deriving the checks.

`selftest.py` is why you can trust that list. It breaks the data on purpose, one fault
per failure mode (21 fixtures over 20 rules), and asserts the rule blocks — a validator nobody has watched fail is a
validator nobody should trust. Two checks here were silent no-ops when first written,
and the mojibake pattern passed clean for months over four corrupted cells because its
regex needed a letter beside the `?` and the real corruption had spaces both sides.
Add a rule to `validate.py`, add a case to `selftest.py`. A **warning**-level rule needs
its fixture asserted differently: the exit code stays 0, and mere presence of the warning
proves nothing when the rule already fires on the real data -- so the case carries
`"warn"` and `selftest.py` compares the count the warning reports against the baseline's.
Written the obvious way, the `cause_agreement` fixture passed with its fault commented
out.

`refresh_caches.py` (with `dashboard_calc.py`) re-derives every cached value in the
workbook from the CSV, by reading each Dashboard cell's own formula -- COUNTIFS, the
`LET`/`TAKE` arrays, the `ANCHORARRAY` columns -- and evaluating it. It rewrites the
six chart `<numCache>`/`<strCache>` blocks and the three dynamic-array spill regions,
including an array's `ref` and its Total-row styling when the array has grown. Nothing
about the layout is hardcoded; move a block or add a row and the values still come from
the formula that row carries. `validate.py` calls its `audit()` and fails if anything
is stale, so this is a gate, not a habit. It is idempotent -- a second run reports
nothing.

Why it matters even though `fullCalcOnLoad` is set: Excel recalculates on open, so the
caches are not what *Excel* reads. They are what everything else reads -- GitHub's xlsx
preview, a Google Sheets or LibreOffice import, `openpyxl(data_only=True)`, a file
manager's preview pane. Four of six charts and all three Top Customers columns were
showing the pre-EAO 80-row figures against a 93-row tracker before this landed.

`sort_tracker.py` is the fix for `validate.py`'s `row_order` warning. Rows get appended
in triage order, not event order, so the tracker drifts; this re-sorts a chosen set of
records by date across the CSV and the Data sheet together. Records are sorted among
the positions they already occupy, so naming two months never disturbs the rest. It
moves whole rows, so a highlight fill (`fillId=2` -- rows a human has flagged, e.g.
Data row 55) travels with its record, and it rewrites the CSV line-by-line rather than
re-serialising it, so quoting stays byte-identical and the diff shows only what moved.
It also restyles cells appended in the wrong font: sorting scatters them, turning a
tidy odd-looking block at the bottom into odd-looking rows throughout.

`append_row.py` is the only supported way to add a record. Appending by hand is the
most error-prone edit here and has gone wrong before: the workbook's column order is
not the CSV's -- `Jira Key` is the third CSV column and column W on the sheet -- so a
positional write lands one column off and only the full-width `parity` check notices.
`ComplaintTracker`'s ref must grow with the row or every Dashboard COUNTIFS silently
undercounts. `Month` is `Sep 2026` in the CSV and a first-of-month serial on the sheet,
while `Reporting Month` is an inline string in both. The script reads the sheet's own
header row for column order, derives Month / Reporting Month / Month_Sort / Number of
Customers / Routed To, refuses to write unless all ten required fields are present, and
writes both files or neither. It deliberately does not refresh caches: run
`refresh_caches.py` then `validate.py` after.

`update_row.py` is its counterpart, for the edit that always follows. A row is staged
from an open ticket before anyone knows why the event was missed, and the answer lands
days later in a comment: EAO-41 and EAO-42 were both staged as `Source Coverage` misses
and both turned out to be keyword gaps in the same bankruptcy algorithm, a week apart.

**The staging default is `Keyword Update`, not `Source Coverage`, on a bankruptcy,
insolvency or utility miss** -- changed on the owner's call after the old default went
0 for 3 (EAO-41, EAO-42, EAO-52, all three a keyword gap in the algorithm). **Its record
since is five right and one wrong**: those three, plus both EAO-54 rows, against EAO-53.
It is a good default and it is not a law -- this line said it had been right every time
it was tested, which stopped being true the moment EAO-53 closed, and a rule that cannot
record its own exception is a rule nobody can check.

**`Source Coverage` means the story never arrived at all**, so reach for it only where
the evidence says the feed was not received. Two cases are what that evidence looks
like: the Bombardier / STELIA thread ("the feed associated with that URL has not been
received by our application"), and **EAO-53**, where engineering wrote "Neither of the
sources is part of the vendor's network. We have requested them to add it." Either way
the Comments say the `Sub-type` is a staging guess, because it is one.

**Non-capture is a symptom, not a cause, and this is where the sub-type is most often
got wrong.** `Source Coverage` and `Keyword Update` produce the identical symptom --
nothing in the system, nothing shown to the customer -- so a finding that "neither the
exact titles nor similar articles were found for that date window" settles nothing by
itself. **One question separates them: was the carrying outlet monitored.** Monitored
means the article arrived and the matching terms missed it, which is a keyword gap;
not monitored means it never arrived, which is a source gap. Ask that before filing
either, and record the answer in `RCA Details` with the reason it is not the other one.

**The two EAO-54 rows are the first where that question was actually asked**, rather
than the cause being inferred from the symptom. Belden raised one ticket covering a
Reuters report on gallium and germanium under Chinese export curbs and a DigiTimes
report on GaAs and InP epiwafer prices; the owner confirmed both outlets are in the
monitoring network, which ruled out a source gap and established the keyword gap
positively. It took two corrections to get there -- the row was filed `Source Coverage`
on a reading of "the sources were not captured" that the owner then narrowed -- and that
is the round trip the question above is meant to save.

**EAO-51 is the case that shows how far a staged guess can travel, and that the owner
ends it.** It was staged `Product` / `Source Coverage`, corrected to `People` / `Review`
on one engineer's comment, corrected again to `Product` / `Keyword Update` on the owner's
reading of the overall miss, and settled by the owner as a **People issue**: `People` /
`Review`, routed to EventWatch Ops, focus `WarRoom & Decision Validation`. Four rounds on
one row. None of the intermediate guesses was evidence; the investigation never concluded
and still has not -- EAO-51 is `Sent to PM` with no resolution, and three of the four
articles are unaccounted for.

What settled it is the analyst-overlooked test, not the count of failures. Engineering
traced the one article that *was* captured (undercodenews) to a cluster later marked
`Not Impactful`, and the owner confirms a person made that call. The story was ingested,
it reached the portal, and a human closed it -- all three conditions, so `People` /
`Review`. The keyword gap on the other three is real and still open with PM, but it is
not what the row is filed under: **a record carries the failure that stopped delivery,
not every failure in the incident.**

**An incident with two causes still gets one row.** The tracker holds one `Root Cause`,
and the Murata pair (CSV rows 27 and 28) looks like a precedent for splitting and is not:
those are two customer emails a day apart, and **a row is a customer email**. EAO-51 is
one email, so a second row would invent one -- taking the tracker to 121 emails and the
headline miss count to 83 for an event that was missed once -- and it would need a
different title to get past `validate.py`'s `duplicates` rule, which is gaming the gate
rather than passing it. Showing two owners on one record would need a second owner
column, a rewritten Data sheet, a wider `ComplaintTracker` ref and three scripts changed;
it has not been asked for.

That is four fields on a row that already exists in two files, with the same failure
modes as appending by hand. It takes `{"match": {...}, "set": {...}}`, refuses a match
that selects anything other than exactly one row, re-serialises every CSV line and
compares it to itself before touching anything (so a file whose quoting it could not
reproduce byte-for-byte is refused untouched), locates the sheet row by position and
then *verifies* it against the CSV row's own key columns, and keeps each cell's
existing style. Same rule on caches: `refresh_caches.py` then `validate.py` after.

`delete_row.py` completes the trio, and was missing the first time it was needed. A row
logged in good faith turns out not to be a record at all -- a customer's follow-up
question on a query already in the tracker is part of that query, not a second incident
-- and taking it back out by hand is worse than putting it in: every `<row r>` and every
`<c r>` below the gap has to be renumbered, and the sheet `dimension` and
`ComplaintTracker`'s ref both have to shrink, that ref being the one that silently
undercounts every Dashboard COUNTIFS when it disagrees with the data. It carries the
same guards, and resolves every target against the original row numbers before applying
any of them, so deleting two rows at once cannot have the first shift the second out
from under it.

`add_definition.py` documents a new taxonomy value, which `enum_definitions` requires
before that value may appear on a record. Introducing one is two edits, not one -- the
value on the row, and its row on the Definitions sheet -- and the second was the fiddly
one: a row appended to sheet3, `DefinitionsTable`'s `ref` extended and the sheet
`dimension` extended, all three or the workbook opens with the table short and the new
row outside it. It reads the style ids off the sheet's own last row rather than
hardcoding them, so a row it adds cannot be the one in the wrong font that `styling`
blocks, and it refuses a term the sheet already carries. Run `export_definitions.py`
after it.

**Pass `source`, not just `allowed`.** The entry is
`{"section", "term", "definition", "allowed", "source"}` and the docstring says the last
two may be omitted -- true only for an operational term. For a *value* taxonomy, `source`
is the tracker column the value belongs to (`"Event type"`, `"Root Cause"`, ...), and
`enum_definitions` keys on exactly that: it groups documented terms by their Source
column, so a row written without one defines a term the rule can never match. Adding
`Price Fluctuation` without `source` wrote a complete-looking row -- section, term,
definition, notes, `DefinitionsTable` ref and sheet `dimension` all correct -- and
`validate.py` still failed with "used in the tracker but have no row in the Definitions
sheet". There is no script to edit a Definitions row, so the fix was a direct zip-member
patch of the one empty `<c r="E153">`, then `export_definitions.py` again. An `Event type` needs nothing on the Dashboard -- the Event Type block is a
dynamic array -- but `Root Cause`, `Fix Status`, `Severity` and `Automation Focus` still
need their hand-listed Dashboard row as well.

## The Jira scheduler

A Routine (scheduled Claude session) runs daily with the Atlassian connector attached,
and it has **two** jobs. The first is the key diff: search the EAO project, diff the
keys against the tracker, classify each new ticket, append it with `append_row.py`,
refresh the caches, run the full gate and push.

**The second is a silent re-check of every row still marked `Pending`.** A row staged
from an open ticket is a placeholder, and nothing used to go back and finish it -- the
diff is keyed on tickets the tracker has never seen, so a ticket already recorded is
invisible to it forever after. The re-check pulls each `Pending` row's ticket and acts
on what moved.

**Silent means the dashboard gains nothing from it.** No marker, badge, highlight,
banner or "last re-checked" note, and **no change to `app.py`** -- the dashboard's job
is to show corrected data, not to advertise that a correction happened. (The
`Under investigation` card and section on All customer emails predate this and stay:
they are a view of the tracker's own column, which the owner confirmed, not an artifact
of the re-check.)

**What the re-check may apply on its own is bounded, and the boundary is judgement.**
Mechanical where the ticket settles it in terms -- moving `Short Term Fix Status` off
`Pending` once an outcome is stated, taking `Resolution Date` from the ticket's own
`resolutiondate` (never a guessed one), putting a comment's RCA text into `RCA Details`
close to its wording. It **holds and proposes** anything touching `Root Cause`,
`Sub-type`, `Missed_Flag`, `Issue Type` or `Standard Automation Focus`: the owner has
reversed classifications here more than once, and the record's own fields usually do not
settle them. `update_row.py` carries established causes back either way. **No API credentials exist anywhere in this repo or in Streamlit** -- the
connector belongs to the scheduled session, not to the app, which is why `app.py` still
makes no network calls. Appended rows follow the house convention for pre-triage
records: `Comments` opens with `Staged from Jira EAO-NN (<status>).` so a row a human
has not yet reviewed is identifiable at a glance. If any gate fails the run opens a PR
instead of pushing, so a bad row cannot reach the dashboard silently.

`Resolution Date` is what makes any timing metric possible, and the app treats it as
the record's closing date. `days_to_close()` is the cycle time and is what
`days_to_close()`, `days_open()` and `age_days()` are all gone with the pages that used
them, so **no cycle-time figure is computed anywhere in the app**. The column is blank on 73 closed records: those predate the
EAO project and carry no ticket to read a date from, so every cycle-time figure names
its own denominator rather than treating a blank as zero. Backfill came from each
ticket's Jira `resolutiondate` via the connector -- never guessed, and never taken for
a merged incident unless every one of its keys resolved.

`date_filter()` is one control in the sidebar, not one per page. Every page used to own a
private copy, so narrowing Executive Summary to September and then opening Root cause
showed the full year with nothing to say the two disagreed -- a reader comparing the
pages was comparing different populations. It now sits beside Customer and Severity,
inside `sidebar_filters()`, and `filter_note()` prints the surviving count at the top of
each page so a thin page still reads as a filter choice rather than broken data. It
filters on `Email/JIRA Date`, and re-seeds its own date boxes when the data moves. Streamlit ignores a widget's `value` once its key exists in session state,
so the pickers froze at whatever span the tracker had when the page first rendered:
records that arrived afterwards -- a merge to main, a row staged on the Complaint
Tracker, a sidebar filter changing the population -- fell outside an end date nobody
chose, and the page went on showing the old set while looking like a working filter.
It now remembers the span the widgets were built from and moves a bound only while that
bound still sits on the old edge, so growth is followed and a range narrowed on purpose
is left alone. It used to prefer `Reporting Month`,
which holds the first of the month on every row, so "2 Sep to 30 Sep" matched nothing
while nine September records existed and the end-date box read 01-Sep against a newest
record of the 14th. It now also prints how many rows survived, so an empty page reads as
a filter choice rather than a broken dashboard -- which is exactly how that bug went
unreported for months.

**Eight pages were removed**, on the owner's instruction and in two rounds: Delivery
performance, Open items and Definitions, then SOURCE 02 Fix status, SOURCE 03 Severity,
SOURCE 06 Automation focus, Repeat patterns and Automation urgency. Their functions went
with them (`close_stats`, `close_trend`, `open_items`, `days_open`,
`definitions_payload`, `repeat_patterns`, `urgency_table`, `recommendation_for_focus`,
`filled`, `rate_chart`). **`PAGES` is seven**, and each one now answers a different
question:

| Page | What it is |
| --- | --- |
| Executive Summary | the whole story, in seven sections |
| All customer emails | the records, and the vocabulary every other tab uses |
| Monthly trend | volume by month, then the summary's own trend block |
| Root cause | the summary's root-cause block, then the deeper one the summary no longer carries, the heatmap and the per-owner drill-downs |
| Top customer complaints | the summary's Customers impacted block, then one account at a time from a dropdown |
| DETAIL Event workload | the summary's Event types block |
| Dynamic Source Discovery | the source and keyword deep dive |

**The six Executive Summary sections are functions now** -- `render_root_cause`,
`render_customers`, `render_event_types`, `render_nature`, `render_trend`,
`render_deeper_root_cause` -- and the internal pages call the same ones. Two of them
have since left the summary itself and run only on an internal page (`render_trend` on
Monthly trend, `render_deeper_root_cause` on Root cause), which costs nothing precisely
because they were already functions: the move is one call deleted, not a block of code
rewritten somewhere else. That is the
only honest way to satisfy "put the summary's views on the internal pages" and "stop
repeating the same details" at once: the internal page runs the summary's code, so the
two cannot drift, and then adds the cuts that do not belong on a summary. Where a page
now renders one of these, `source_page(..., summary=False)` drops the generic
count-table-and-chart pair it used to draw, because that was the same numbers a second
time in weaker words.

SOURCE 01 is the case that proves it: the page drew its own miss-rate line from
`missed_rate()` while the Executive Summary drew `trend_chart()` from pooled three-month
windows. Two charts of one number, comparing different months, with nothing on either
saying which was real. What the first of
them used to say is kept here because the reasoning still binds anything that quotes a
cycle time:

The Delivery performance page answered "how well are we responding", which no page did.
**Time to close** (`close_stats`, `close_trend`) is median, p90, worst and the share
closed inside 14 days -- and every one of them prints its denominator, because only 28 of
116 emails carry a `Resolution Date` and a median quoted bare invites a reader to apply
it to the whole book. A month whose median rests on fewer than three closes is named as
thin rather than drawn like the rest. That is now the whole page: the RCA funnel that sat
under it is gone, with `rca_funnel()` itself.

The page briefly carried a third block charting `Fixed` against `RCA Shared` as a share
of each month, and it was removed because it was an artifact, not a finding. `Fixed` ran
at 100% of January and reached 0% by September while `RCA Shared` went the other way,
crossing in June -- which reads as operations changing until you check what else changed
in June. The EAO project did. Jan-May had 5 ticketed records of 53; Jun-Sep had 49 of 58,
and records with no Jira key split 36 `Fixed` to 4 `RCA Shared` while ticketed ones split
9 to 25. Before there was a ticket to record an RCA against, work got written down as
`Fixed`. **Any trend that starts in June is suspect for this reason**: the tracker's
recording practice changed then, so a shift in what the fields say is not evidence that
the work changed. Test the June hypothesis before publishing a trend line.

**Top customer complaints is one account at a time**, chosen from a dropdown. The three
tables it used to end with were `long_pair_table` dumps -- one row per customer-and-value
pair, thirty-three accounts deep, unranked and ungrouped, so reading one account meant
scanning past thirty-two others, and "Customer root-cause patterns" said only Product /
People / Process, which names the team and not the problem. `render_account_view()`
replaces all three: a KPI row for the account, one computed sentence
(`account_headline()`), `account_failures()` keyed on the **(Root Cause, Sub-type)** pair
so the owner is a pill and the failure sits beside it in the dashboard's own words, then
the reason categories and the event types with a chart each. The selector narrows that
block only; the tables above keep following the sidebar.

`account_scorecard()` is gone, on the owner's call. It was one row per account across
five columns, and every one of those columns is now either on the dropdown view above or
on the Customers impacted table this page already carries.

## No RCA figure is published anywhere

**`RCA Requested`, `RCA Details` and `Short Term Fix Status` do not agree about whether an
RCA was delivered**: 85 emails are marked `RCA Requested`, 38 carry any text in
`RCA Details`, and 31 are marked `RCA Shared`. Three numbers for one thing, none of them
matching, so every share quoted from them picked one of three and hoped. **No count,
share, funnel or "owed" figure derived from those fields appears on any page.** Removed
together, not one page at a time: hiding a wrong number on one page while two others
still show it leaves the pages disagreeing, which is worse than showing it everywhere.

What went: the Executive Summary's RCA card, Delivery performance's RCA funnel
(`rca_funnel()`, deleted), Open items' `RCA never delivered` and `RCA on file` cards and
its "RCA promised but never delivered" table, `open_items()`'s second return value
(`owed`), `age_days()` (it existed only for that mixed open/closed table), and the
`RCA owed` column on the account scorecard, itself since removed.

What stayed, and why: **the RCA text itself**, on Open items' "Root cause analyses on
file" table and on the record card -- that is what somebody wrote, not a statistic. And
`urgency_table()` used to score `RCA Requested` on the Automation urgency page; that
page and that function are both gone, so **no RCA field is read anywhere in the app at
all** now. The reasoning for the exception is kept because it is the one that would
apply if any RCA figure came back: the defect is on the *discharge* side, whether the
customer asked is one field with no contradicting sibling, and it is the three delivery
fields that disagree.

Before any RCA figure comes back, the three fields have to be reconciled on the records
themselves. Publishing one again without that is republishing the same guess.

`definitions.json`, `scripts/export_definitions.py` and `validate.py`'s
`definitions_export` all stay although no page renders the glossary any more: they are
what keeps the workbook's Definitions sheet honest, and `enum_definitions` -- the rule
that refuses a taxonomy value with no row on that sheet -- rests on the same sheet. The
page went; the guard did not.

`insights()` is gone, and with it the "What stands out this period" panel at the foot of
the Executive Summary. It computed sub-type drift over two windows, customer
concentration, accounts whose every email was a miss and the worst recurring
customer+sub-type pair. Every one of those is now said better by a section above it: the
eight cards carry the concentration, the trend section carries the movement, and the
root-cause table carries the recurring failure with its own denominator beside it. A
panel that restates the page in different words is a panel a reader has to reconcile.

## The card popups

Clicking any of the eight cards opens that card's own breakdown in an `st.dialog`;
a **Break it down** hint appears on the card on hover, and there is no separate strip.
`metrics.card_details()` builds one payload per card and
`components.detail_panel()` draws it -- the same split the rest of the package keeps, so
a panel can be restyled without touching a total and a total cannot move on a styling
edit.

**Every figure is computed off the frame on screen, and from the functions the cards
already use.** The eight panels were designed as mockups first, with their numbers
typed into the markup, and they went stale in three days. `card_details()` reads
`miss_bucket_series()`, `miss_by_customer()` and `trend_windows()`
rather than recomputing anything: a popup that re-derives a figure its own card prints
is a second implementation waiting to disagree with the first. The panels follow the
sidebar filter for the same reason -- they are built from `filtered`, so a popup can
never describe a different population from the card that opened it.

**One anatomy on all eight**, because eight panels that each invent their own shape are
eight things a reader has to learn: a chain line saying where the figure sits in the
funnel (`127 emails > 103 complaints > 86 misses`), the question, the figure with its
base, **one** short sentence, a rule, a row of **stat cards**, a rule, and one footer
line carrying the arithmetic on the left and the single caveat on the right. **The chain
is the anti-confusion device**: the eight cards quote five different denominators, and
"42 of what" was the question every one of them left open.

**A stat card puts the number first and its label under it**, and that is a correction.
The first cut ran each breakdown as a line of prose with the figure at the right edge
and a sentence of gloss beneath -- the owner's reading was that the numbers were
stranded at the corner, which is exactly what that arrangement does: the words are read
and the number is not. The cards sit on a **fixed-column grid**, not a flex row, so five
cards over three columns read as 3 + 2 of equal width; flexed, the trailing two stretch
to half the panel each and a 1 looks like an 8. The paragraph under every row and the
stack of note boxes under that are gone with it, on the same instruction -- a panel
exists to answer the one question the card raises, not to brief the reader.

**Two cards must not be told apart only by their count.** `Supplier left off` (1) on
the analyst panel and `A system fault` (1) on the delivered-but-wrong panel read as the
same kind of thing in different words, and the owner asked what the difference was.
They are different fields entirely: the first is META / EAO-15, where the supplier was
on file under two names, the analyst checked one, **no WarRoom was created and nothing
reached the customer** -- a miss. The second is Hitachi, where **a bulletin was
delivered** and the Disruption Agent then returned only Tier 1 suppliers -- a confirmed
defect, `Missed_Flag` No. They now read `They missed a supplier / On file, never
selected, so no WarRoom` and `A confirmed software bug / The bulletin landed; the
platform then failed`. **A label that could sit on either panel is not a label.**

**A card that says "a confirmed software bug" twice has told an ELT nothing.** The
label appears on two panels and they are two different defects with two different
outcomes -- Harman's impact-confirmation requests that never went to four Tier 2 sites
(a miss), and Hitachi's Disruption Agent returning only Tier 1 suppliers after a
bulletin had landed (not a miss). The bug groups carry `NAME_THEM` in place of a note
and `defect_name()` reads each record's own `Event/Bulletin Title`, so the panels now
print the defects rather than the category.

**`NAME_THEM` is on the bug groups and nowhere else, and that is not timidity.** The
house title convention is `<event> - <what went wrong> (<Customer>)`, which names the
defect on a `Platform Bug` row and names the **event** on most others: put it on the
clustering group and the panel explains a defect with "Fire at the Isselguss GmbH
Facility", which is worse than the generic line it replaced. **Read what the titles
actually say before putting it on another group.**

**One short name per cause, and `SHORT_CAUSE` is where it lives.** Card 8's owner
cards read `4 failures · biggest 12` in the first cut, which is two words a reader
cannot act on: "failures" names nothing and "biggest" ranks something they cannot see.
They now read `no monitored source 12 · keywords missed it 7 · and 3 more` -- the same
short words the stat cards on cards 3, 5 and 6 print, from one map rather than a
wording per panel. It is keyed on the sub-type with the owner-aware overrides
`OWNED_SUBTYPE` already makes, because `Review` under Product is the model deciding and
under People is a person deciding; `short_cause()` is the accessor and `named_causes()`
builds the line. The long plain label is still what the tables print -- at 46 characters
it is a paragraph under a 28px number in a box a third of the panel wide, and Root cause
is one click away for the full taxonomy.

**No popup prints a number that has to be remembered.** Card 6's late bucket read
"18 hours to 25 days", a figure typed from a reading of the twelve `Reported late`
rows, which is the fault this file exists to prevent. It says "Published, but not in
time to act" -- a definition, which cannot go stale.

**Card 1's four account cards do not sum to its hero, and the foot says so.** Accounts
split on the slash, so the five emails naming two accounts are counted for both and the
column adds to 132 against a tracker of 127. There is no partition to be had and the
card is not wrong; a reader who adds four numbers under a hero of 127 and finds 81 will
challenge the page, which is exactly what happened to the Customers impacted table
before its caption explained the same overshoot. Both figures are computed. **Where a
panel's parts cannot sum to its headline, say why on the panel** -- the same rule as
"a total row is a reconciliation, not a sum".

**The groupings are tables with a fall-through, not a fixed list.** `ANALYST_ACTIONS`
folds the People-rooted misses onto what the analyst did and `WRONG_GROUPS` folds the
delivered-but-wrong complaints onto what was wrong with the bulletin; both apply in
order, each group claims only what the ones before it did not, and a sub-type outside
every group keeps its own plain label and its own card. Nothing lands in an `Other`
bucket, for the reason `miss_categories()` has none: a residue row is how a mis-filed
record stays mis-filed, and it hides a sub-type added tomorrow.

**Colour carries one thing and nothing else: who fixes it.** Product `--blue`,
EventWatch Ops `--red`, a delivered bulletin that was wrong `--amber`, a row that
belongs to nobody `--muted`. **Nothing is shaded by its own size.** The first cut faded
each bar by its value -- darkest first, palest last -- which spends the only free
channel restating the bar's own length; `dataviz` names it as a value ramp on nominal
categories. Every pair that actually sits on one panel clears the colourblind floor
(`--blue` against `--red` is dE 17.0 protan, against `--amber` 20.6). `--red` against
`--amber` is the one weak pair at dE 13.9 and never co-occurs, because Process carries
no misses; if it ever does, that panel needs a different encoding, not a new hue.

**The whole card is the click target, and there is no button.** The first cut put a
quiet strip under each card; the owner's answer was that the card itself should open
its own breakdown. That leaves two ways to do it and only one that is safe. An
`<a href="?card=...">` would need no widget at all and is the wrong answer: a real
anchor navigates, Streamlit hands back a fresh session, and **every sidebar filter
resets** -- a popup that silently clears the filters is a worse bug than the one it
fixes. So `clickable_kpis()` draws each card in its own `st.container(key=...)` and
lays a real `st.button` over it, made invisible with a transparent colour and a zero
font size rather than removed, so a screen reader still announces which card it opens.
The click stays in the session and the filters are untouched. `kpi_card()` is the one
source of the card markup, so the plain grid and the clickable row cannot drift.

**Both rows of cards are drawn on every rerun, and `opened = opened or clickable_kpis(...)`
is why they were not.** Python short-circuits `or`: once a card in the top row returned
its key, the right-hand side was never evaluated, so the second row of four was never
drawn -- the reader clicked a card, closed the dialog, and the bottom four cards had
vanished. Call both rows, then combine. **Never fold a call that draws something into
a boolean expression.**

**The overlay is pinned to `--kpi-h`, and three attempts to let it inherit a height
each landed 16px short.** Streamlit lays the markdown out through a flex wrapper with
a definite height; the card overflowed it, so every ancestor measured under the card
and the bottom strip of each card was not clickable. The card and the container that
positions the overlay now share one height this stylesheet owns, which a Streamlit
release renaming a wrapper cannot break. **Measure the box chain before changing it** --
the two wrong fixes before this both guessed at the row gap.

**Every button property carries `!important`.** Streamlit's own rule is
`.stButton > button`, specificity (0,2,1) against the (0,1,1) of a `.st-key-...`
descendant, so the unqualified version lost every declaration and the first cut
rendered as a default blue pill. Only a screenshot caught it; the DOM probe had
confirmed the buttons existed and said nothing about how they looked.

`st.dialog` is applied at call time rather than at module level so each panel's title is
its own card's eyebrow, and `width="medium"`: at `large` the panel stretches past
1200px and the gloss under each row becomes a line nobody tracks back to its start.

**`audit_pages.card_detail_problems()` is what keeps them honest.** The panels are only
in the DOM once a reader clicks, so the scrape that reconciles every rendered figure
never sees them -- which would leave eight panels of numbers outside the only gate that
says whether a figure is right. The payloads are plain data, so the check is a pure
call with no browser: the rows a panel prints must match the equation printed under
them, and that equation must be true. Only the blocks marked `partition` are compared against the equation, so a block
that is context rather than a split is not matched against one. **This is the whole reason a
popup prints a visible `N + M = T` line at all.**

`kpis(items, columns=n)` sizes the grid to the count. Both the auto-fitting variant and
a fixed five were wrong: auto-fit wrapped a five-card row to four-plus-one on any window
under about 1200px -- which is the width these are actually read at -- and a fixed five
leaves a hole when there are four. Pass the count. The ticket-
traceability finding was dropped: it measured when the EAO project started, which is
the same recording artifact the June rule above warns about.

**`miss_categories()` has no `Other` bucket, and that is deliberate.** `MISS_BUCKETS`
holds only the four rules where the **owner changes the answer** -- `Source not in our
vendor or monitoring network` (Sub-type `Source Coverage`), `Keyword Miss` (`Keyword
Update`), `An analyst let it through` and `The model did not spot it` (both `Review` /
`Model Classification Defect` / `Analyst Review Miss`, split on `Root Cause` People
against Product).
The first two take their wording from `PLAIN_SUBTYPE` rather than repeating it, so a
label cannot be renamed in one place and not the other. The last two are the only labels
on the page that may name an actor, because the owner is part of the rule that selects
their rows rather than a property of the sub-type.

Every other missed email takes a bucket **named after its own sub-type**, generated in
`miss_bucket_series()` from `PLAIN_SUBTYPE`. Eleven buckets on the current data: an
analyst let it through 29, source not in our network 23, keyword miss 12, the model did
not spot it 6, then supplier not mapped by the customer 2, published but not visible 2, reporting
guidelines clarified 1, incorrect industry selection 1, captured but notified late 1,
scoring or rules 1, WarRoom missed 1.

A residue bucket is how eleven real and different failures became one grey slice nobody
could act on, and it also hides a sub-type added to the tracker tomorrow -- which would
land in `Other` and never be seen. Generating the tail means a new value appears under
its own name, because `plain()` falls back to the value itself.

Eleven categories is past where a donut works, so the block is a **ranked horizontal
bar**, biggest first, and colour says *who fixes it* (`miss_colours()`: the four named
buckets keep theirs, the rest take their dominant owner's) rather than trying to give
eleven buckets eleven hues. Every bar carries its own name, count and share, so nothing
rests on colour alone.

`audit_pages.py` recomputes every bucket from the CSV **under the same names** -- the
four rules independently, the tail by sub-type through an imported `PLAIN_SUBTYPE` -- and
asserts they sum to the miss count. A bucket renamed in `app.py` and not in the audit
fails it rather than quietly ceasing to be checked (the audit records a label it cannot
find as "not rendered", not as a mismatch).

`miss_bucket_series()` is the one implementation: it returns the bucket for each row and
`miss_categories()`, the per-account table and everything else aggregate it, so no two
blocks on the page can disagree about which bucket an email is in. Non-misses start out
claimed, so they can never take a bucket.

Those were 20 / 9 / 25 / 13 / 10 until six records were found whose `Automation
Opportunity` read "Source coverage expansion" or "Keyword expansion" -- the team's own
name for the fix -- while `Sub-type` read `Event Identification`. The buckets key on
`Sub-type`, so all six counted as model misses. `validate.py`'s **`cause_agreement`**
now compares the two fields, as a warning rather than a failure because which of them
is wrong is a judgement. Data row 29 was the case that proves the point: a
People/Prioritization record whose Product half is row 28, already `Source Coverage`, so
reclassifying it would have counted one Murata incident as two source misses. There the
**remedy text was the wrong field**, and it was rewritten rather than the `Sub-type`.
The rule reports nothing on the current data.

EAO-12 was the same fault the rule does **not** catch, found by reading the ticket. Its
`Standard Automation Focus` said `Dynamic Source Discovery` and its `Sub-type` said
`Event Identification`, but the thread says plainly that the articles *were* captured by
the vendor and by the Spanish-language algorithm and *were* clustered -- what failed was
the cluster's own state (`Update` while also `Not Impactful`), which kept them off the
analyst portal. Neither a source gap nor a model miss: `Visibility`, `Cluster Integrity &
Duplicate Prevention`, and the third **`Bug`** in the tracker, since the thread asks
whether it is a recurrence of a cluster-state defect fixed in the June-end release.
A loose rule keyed on "source discovery" would have caught it and eight correctly
classified rows with it, which is why `cause_agreement` stays narrow: **the umbrella
automation programme is not evidence of the cause**, and a record whose focus is
`Dynamic Source Discovery` may legitimately be a keyword gap.

**`Dynamic Source Discovery` deliberately spans source AND keyword gaps.** It is the
umbrella automation programme, not a claim about the cause: of the twelve `Keyword
Update` records it holds five, including EAO-41 and EAO-42 whose own RCA text says "Not
a source-coverage gap" in terms. That contradiction is **known and accepted** -- it was
put to the tracker's owner and left as it stands, because the alternatives were to
invent a language cause the records do not support (`Multilingual Keyword Expansion`
means multilingual: Swedish on Data row 2, Spanish on row 61, and the Turkish, Chinese
and foreign-language border-closing rows) or to bury an algorithm keyword gap in a
catch-all. Do not "fix" it. `Multilingual Keyword Expansion` takes a record **only with
explicit language evidence in its own Comments**.

Two `Keyword Update` records, Data rows 15 and 58, keep `Dynamic Source Discovery`
because their Comments say "Feeds not ingested" and "Feed ingestion investigation
raised" -- there the focus is right and it is the `Sub-type` that is doubtful.

The focus was `Dynamic Source Discovery` on three records that were
not source problems at all -- it is the largest value and had become the default anything
unclassified fell into. Row 24 (an SEC notification delivered late, whose own remedy is a
regulatory-feed timeliness check) is `Other Control Automation`, which is where eight of
the fourteen `Process Clarification` records already sit; row 29 (an analyst
misclassification fixed by retraining) is `WarRoom & Decision Validation`, with the
nineteen `Review` records. When a focus and a `Sub-type` disagree, check which one the
record's own `Comments` support before assuming the taxonomy field is the right one.

**The slide this block reproduces (38 total, 53% source) is not reproducible from this
tracker at any cut** -- through June it holds 48 missed records with 9 source misses
(19%), not 38 with 20 (53%), and no complaints-only or other subset gets there either.
Whatever built that deck, it was not this file. Do not reconcile to it.

**And the cumulative ring hides the quarter.** `miss_recent_note()` prints a line under
the donut naming the last three months whenever the frame spans more than six, because
reading the ring as "the picture" gets the wrong two priorities: over nine months the
source bucket is 30% and second, over Jul-Sep it is 38% and first, while the model bucket
falls to zero -- no email in the last three months is a model miss at all. It lists only buckets that moved 5 points or more, biggest recent share first -- the
same threshold rule `insights()` applies. This exists because a claim that source misses
"had not moved" survived review here, on the coincidence that the slide's 20 equals
today's 20; 11 of those 20 had landed in the previous three months. **Two equal numbers
taken from different totals are not evidence that nothing changed** -- check the monthly
series before saying a bucket is flat.

Analyst and model are two slices because they have **different owners**: an item a human
reviewer saw and did not raise is EventWatch Ops' to fix, one the model did not identify
is Product's. They were briefly merged, and merging them threw away the only part of the
number that says who acts on it. The last bucket is the other honest part -- the named
categories do not cover the taxonomy (Mapping, Tagging, Visibility, Policy/Logic,
Captured Late, WarRoom Creation, and a Process-rooted `Review`), and folding them into
the analyst number would overstate it by the size of the residue. Buckets apply in order
and the last claims whatever is left, so the slices always sum to the missed count
however the taxonomy grows. `audit_pages.py` recomputes all five from the CSV
independently, so a bucket quietly redefined in `app.py` fails the audit rather than
agreeing with itself.

Colour: the source and keyword buckets are one family in two steps of `BLUE_RAMP` (both
are "it never reached a person"); the analyst and model buckets take `--red` and
`--amber`; the residue is
`--muted`. `--green` is **deliberately unused here even though it measures clean** --
`--red` against `--green` is dE 9.7 deutan and 20.5 normal, so the dE 3.6 pair warned
about above is a saturated red/green, not these two tokens -- because every slice on this
chart is a failure and green would say one of them went well. The five-slot palette
passes CVD separation (dE 8.5 worst all-pairs, 10.7 worst adjacent) and fails the
normal-vision floor on the grey residue against `--blue` (dE 9.5), which is legal only
with secondary encoding: every slice and every card carries its own label, count and
share. A hue from outside the app's tokens would clear it and break the one-palette rule,
which is worse.

`Severity split` and `Automation opportunities` are not on this page. They were moved to
SOURCE 03 and SOURCE 06, and those pages have since been removed too, so neither figure
appears anywhere -- which is the point: the owner's call was that they add no value, and
half-removing a view leaves the summary and an internal page disagreeing about whether
it matters.

**The `Event type` value is `Legal Action`, not `Litigation/Legal`.** Renamed on both
rows that carry it (EAO-17 and EAO-46) with `update_row.py`, and on the Definitions
sheet -- that row is an inline string appearing once on sheet3, so it was renamed in
place rather than added and pruned, which leaves the row, its styles, `DefinitionsTable`'s
ref and the sheet `dimension` untouched. `refresh_caches.py` then rewrote the Event Type
spill cache on the Dashboard, which carried the old value.

## The Executive Summary, section by section

The page is a story in eight parts, separated by `add_rule()` -- a full-width hairline,
because the heading card alone was not enough and two adjacent sections read as one.
Every section is chart-then-table, in that order, so the eye learns the shape once.

**The order is a reading order, not a granularity one, and that is a correction.** A
coarse-to-fine sort was tried -- cards, rings, months, categories, event types, root
causes, the taxonomy, then every account -- on the reasoning that the widest table
belongs last. It put **Customers impacted eighth**, and the owner reversed it in terms:
that section is the one a reader comes to this page for, and burying the account view
under five blocks because its table has seventeen columns optimises for layout against
the question being asked. It is back at **fourth**, directly under the failure analysis
it belongs to.

The order now is: what came in (the cards), **when it arrived and where it failed**
(the monthly breakdown, moved to second on the owner's call), **how much of it was
ours** (the rings), **why we missed** (the root causes and their drivers), **who it
hit** (Customers impacted), **what kind of event**, and last **what the customer
themselves called it** (Nature of complaints,
moved to the foot on the owner's call -- it is the customer's own vocabulary and reads
as the coda to the story rather than the opening of it). **Do not re-sort this page by
table width.**

**Every table on the page carries a Total row** (`excel_bar_table(..., total_row=True)`,
which is the default). It is summed inside the table function rather than by a generic
helper, because the share column is a formatted string: "29.5%" cannot be added up after
the fact, and the total of a column of shares is 100% of whatever base the table was
built from, not the sum of the strings in it.

1. **Eight cards**, two rows of four via `kpis(..., columns=4)`. Never eight across: at
   the width this is read at that is 180px a card, and the number is the first thing to
   shrink.

   **Row one is the funnel** -- emails, complaints, confirmed misses, complaints that
   were not a miss. **Row two is where the misses stopped, and it carries all THREE
   stages**: `Never reached us` 42, `Lost before an analyst` 9, `An analyst saw it` 35,
   then the last three months' rate.

   **The middle card is the fix for a real defect.** The row used to carry two stages
   and one account's share, so a reader adding 42 and 35 against a headline of 86 came
   up **nine short with nowhere to put them** -- the stage where we had the story and
   no person ever saw it had no card at all. The owner found it by adding the two
   numbers on screen, which is the first thing anyone does with a row of figures. The
   three stages come from `_miss_parts()`, the same function the popups use, so they
   are a partition by construction.

   **A line under the row printed `42 + 9 + 35 = 86` and the owner removed it.** What
   went is the restatement, not the guarantee: `_miss_parts()` is what makes the three
   a partition, and each card's own panel still prints the equation for the split it
   shows. Do not read its absence as licence to put a stage on this row that is not
   part of that partition.

   **The account card went to make room, and it was the right one to lose.** Ford's
   share was on card one's own panel, on this page's Customers impacted section and on
   Top customer complaints -- a fourth telling is a fourth thing to reconcile, and the
   owner named the repetition before the arithmetic. `_account_card()` and
   `_account_share()` went with it.

   **Every foot says what the number means in plain words**, not what field it came
   from: `we did not get the event to them in time`, `we had the story and no person
   ever saw it`, `a person had it, and it still did not go out`.

   **A card's eyebrow is its popup's title.** The dialog is headed with the words on
   the card the reader clicked; a panel headed something else reads as the wrong panel.

   **No label says "Product fixes it".** The owner asked what that meant, and the
   question is the right one -- it names no team a reader could take the number to.
   The two values of `Routed To` do: `Product & Platform` and `EventWatch Ops`.
2. **Month by month: what came in, and where it failed** -- `render_monthly_breakdown()`,
   moved here from sixth on the owner's call. It is the view a VP comes to this page
   for, and it sat behind five other blocks.

   **One bar per month, five segments**, and every level of the hierarchy sums into the
   one above it:

   ```
   Emails     = Complaints + Inquiries
   Complaints = Misses + Reported, but wrong
   Misses     = Product + Analyst + Process
   ```

   That is a **nest, not two competing cuts of one total** -- which is the fault that
   made the event-type table read as broken arithmetic. `monthly_note()` prints all
   three lines under the table so nobody adds Complaints to Misses.

   **It replaced a grouped complaint-against-inquiry pair that was volume only**: how
   many arrived, and nothing about how many we got wrong, which is the whole of what
   the block was asked for. `monthly_breakdown()` reads `_miss_parts()` and
   `Root Cause`, the same source the eight cards use, so a month here cannot disagree
   with the headline above it.

   **Colour comes straight from `ROOT_COLOURS`** -- Product `--blue`, Analyst `--red`,
   Process `--amber` -- so a Product miss is the same blue here as on the cards. The
   two segments that are not a miss owner take neutral tokens: `--line2` for
   `Reported, but wrong` and `--teal` for an inquiry. The blue-against-green pair this
   replaced carried no meaning at all. **One cost, accepted:** `--red` against
   `--amber` is the weak colourblind pair at dE 13.9 and they would sit adjacent the
   day the first Process miss lands. Every segment prints its own count and the table
   carries all of them, which is the secondary encoding that makes it legal -- but it
   is a real constraint, not a non-issue.

   **Process is zero in every month and the column stays.** All four Process misses
   moved off the flag in the October rulings, so the honest answer to "what about
   process errors" is *none, all year*. A VP who sees no Process column concludes
   nobody measured it. Process is not absent from the book -- it sits inside
   `Reported, but wrong`, which is where it belongs.

   **The miss rate rides above each bar**, so the chart answers "is it getting worse"
   without the reader going to the table. **A month under `THIN_MONTH` emails prints
   its rate muted**: Jan is 3 of 4, where one record moves the figure 25 points, and a
   rate that thin in the same white as a 19-email month invites a comparison that is
   not there. Same rule `missed_verdict()` applies to the trend windows.

   **Three layout facts, each measured rather than guessed.** A segment under about a
   sixteenth of the tallest bar gets no label -- plotly clips the digit vertically
   rather than dropping it, `uniformtext` does not catch it because the text fits
   *horizontally*, and a clipped `1` reads as a stray mark on the bar. The legend needs
   `traceorder="normal"` or a stacked chart lists it upside down against its own stack.
   And the table is **`roomy`, not `wide roomy`**: naming the bases in the headers
   (`Miss rate (of emails)`, `Product share (of misses)`) ran it 300px past its panel,
   and even shortened it was 44px over at content width, so the last column lived
   behind a sideways scroll. Full width fits twelve columns; `nowrap` on `Month` stops
   "Jan 2026" wrapping and doubling every row.

   **No descriptive paragraph under the heading**, on the owner's call -- `add_section`
   now emits no `<p>` at all when `desc` is empty, rather than an empty one the card's
   flex gap spaces as though it held a sentence. The one caption line is a
   reconciliation, not commentary.

   **Click a month and it opens its own root-cause breakdown** in an `st.dialog`:
   `render_root_tier()`, the owner cards and driver bars split out of
   `render_root_cause()`, run against that one month. The popup looks like the Root
   cause page because it **is** the Root cause page's code -- a second implementation of
   those cards would be a second set of numbers waiting to disagree.

   **The month is the click target, not the segment, and that is a correction to the
   obvious design.** A segment of one or two emails is about 10px tall, which is the
   fault already recorded on the driver bars: *"a one-miss bar is fourteen pixels wide,
   and Other and Needs Review are exactly the short ones -- the rows a reader most wants
   explained were the hardest to hit."* Vertically it is worse. There are also 19
   non-empty owner cells against 10 months, **four of them holding two records or
   fewer** and six drawing a single bar, so segment panels would be more panels and
   thinner ones. And the figure the owner asked this to look like shows two owners side
   by side, which is a month, not a segment.

   **`selected` and `unselected` marker opacity are both pinned to 1.** Streamlit's
   selection styling dims every bar the reader did not click, so the chart sat washed
   out behind the dialog and **stayed that way after it closed**, reading as broken
   rather than as a selection. Verified by reading computed opacity back off every bar
   after an Escape, not by assuming.

   **Only the Executive Summary passes `clickable=True`.** The chart's widget key is one
   piece of session state; two pages sharing it would have a month opened here open
   again on Monthly trend.

   The dialog is **`width="large"`**, the one departure from `medium` on this dashboard.
   `large` was rejected for the card popups because a line of prose stretches past
   1200px and nobody tracks it back to its start -- cards and bars have no such problem,
   and two owner cards with their driver charts do not fit 700px.

   **Two chart-furniture facts, both found by screenshotting.** Plotly's modebar floats
   over the top-right of the graph on hover, exactly where the click hint sits, so the
   modebar is docked `orientation="v"` down the right edge instead -- cheaper than
   hiding it, which would take the download and zoom buttons with it. And under
   `hovermode="x unified"` the box already prints the month as its header, so a
   hovertemplate carrying `%{x}` reads "May 2026 · 9 product miss" under a heading that
   says May 2026.

   **`audit_pages.month_panel_problems()` is what keeps the dialogs honest.** A month
   panel is only in the DOM once a reader clicks, so the scrape never sees it -- the
   same hole `card_detail_problems()` closed for the eight cards. The panel reuses the
   renderer rather than carrying a payload, which is what stops it drifting and also
   means there is nothing to read back, so the check **recomputes both levels from the
   CSV**: a month's owner cards sum to that month's confirmed misses, and each owner's
   driver bars sum to that owner's card. It derives `Month Label` the way `data.py`
   does, because a check that silently found no months would pass on every tracker. Ten
   panels, thirty assertions; seeding one wrong owner count fires all three levels.

   **The table is a scroll box, not an expander.** A collapsed expander lays out at zero
   height, so `innerText` reads empty and `audit_pages.py` silently stops reconciling
   every row it hides -- eleven rows and the Total among them. `stickytotal` keeps the
   foot on screen. If it ever does need to collapse, the expander has to come with a
   line in the audit that opens it before scraping.

   It is shared with **Monthly trend**, for the same reason every other shared block
   is: two pages drawing the same months from two copies is how they end up disagreeing.
3. **What customers sent us** -- two donuts, side by side. `overview_split()` is all 115
   in three mutually exclusive parts (78 misses / 17 complaints that were not / 20
   inquiries); `miss_owner_split()` is the 78 by who fixes them. Three slices each, which
   is what a donut is for.

   **The second ring was briefly deleted here on the reasoning that the three cards in
   section 3 say the same 46 / 29 / 3. Nobody asked for that, and it was restored.** The
   overlap is real but it is not a reason to remove a view the page's owner wanted: the
   rings answer "what came in and how much of it was ours", the cards answer "and what do
   we do about each". Do not remove it again.

   Both rings name the tracker's own values -- `Product` / `People` / `Process` -- so the
   ring and the cards below speak one vocabulary. It read "The platform / Our analysts /
   How we work" here and the tracker's names in the section underneath, which is two
   words for one thing on one page; `PLAIN_ROOT` went, and the ownership line moved to
   each slice's hover, which is where the plain English belongs.

   **Every slice explains itself on hover** (`SPLIT_MEANING`, `ROOT_OWNERSHIP`), wrapped
   at 44 characters before it reaches plotly for the same reason the driver bars are --
   plotly's hover label neither wraps nor is clipped to the panel. The share is formatted
   `%{percent:.1%}`: plotly's default gives two significant figures, so the 3-miss slice
   printed `3.85%` beside a table saying `3.8%`.

   **Driving a pie's hover needs a real mouseover on the slice, not `Plotly.Fx.hover`.**
   `Fx.hover` silently does nothing for a pie trace -- it returned empty text for all six
   slices. Dispatching `mouseover` then `mousemove` on the slice's own `g.slice` element
   works, and is how the six tooltips above were read back.
4. **Why the events were missed** -- two tiers, and the page's headline above both:
   *N of 78 misses never entered our system*, computed from the source and keyword
   buckets so it cannot go stale. That sentence is the number Product sizes the
   source-and-keyword problem with; what to buy against it is deliberately not on the
   dashboard.

   **Top tier**: `root_summary()` gives one card per root cause, biggest first -- the
   count, its share of all confirmed misses, and who owns it (`ROOT_OWNERSHIP`: Product
   *Detection and system coverage*, People *Analyst assessment and review*, Process
   *Workflow and control*). Blue, muted coral and amber, the app's own `--blue`, `--red`
   and `--amber`.

   **Card and bars sit in one column each**, not in two rows of three. As two separate
   `st.columns` calls the cards were one row and their drivers another, so at the width
   this is read at the eye had to carry "Product" down past a card border to know whose
   bars it was looking at, and three equal-height cards pushed every bar a full card
   below the fold.

   **All three driver charts share one x scale** (`driver_bar(..., xmax=widest)`). Each
   autoscaled before, so Process's 2-miss bar drew almost as long as Product's 24 --
   three panels side by side are read as a comparison whether or not they are labelled
   one, and bar length is what a reader takes from a bar chart before the number beside
   it. The axis stays hidden; the count still rides on the end of every bar.

   **The driver table is `wide roomy` with a wrapped meaning column.** This was the
   worst thing on the page: `wide` sets `white-space:nowrap` on every cell, and
   `excel_bar_table` had no wrap support at all, so a column of sentences ran the table
   off the right of the panel and the reader scrolled sideways to read an explanation.
   `excel_bar_table` now takes `wrap` (columns that hold a sentence: left-aligned,
   340-640px, `white-space:normal`), `raw` (columns whose value is already HTML --
   the owner pills, and nothing else; everything a human typed still goes through
   `esc()`), `classes` and `caption`. The `roomy` variant is the typography: 12px
   padding, 1.5 line-height, a 14px first column, tabular figures on every number and a
   quieter header. Measure the result with
   `table.getBoundingClientRect().width` against `.table-wrap` `clientWidth` -- every
   table on the page now fits its panel except Customers impacted, which scrolls
   sideways by design.

   **The Owner column is one pill per owner** (`owner_pills()`), in that owner's colour
   from `ROOT_COLOURS`. It was the string "Product 12 · People 3", which reads as a
   single value and makes a reader parse two names and two numbers out of one run of
   text, in the column a VP actually looks for. `downloads()` strips the tags on the way
   out, so the CSV reads "Product 12 People 3" rather than a span.

   **Bottom tier**: `root_drivers()` under each card, the top four drivers biggest first,
   then one `Other` row -- unless the tail holds exactly one driver, which is shown by
   name instead: "Other: 1 smaller driver: Industry Selection (1)" is longer than
   "Industry Selection" and hides a name to save no space. All three charts pad their
   axis to the longest list (`slots`)
   rather than stretching their bars to fill the panel: equal panel height with three
   different bar thicknesses compares shapes, not numbers. `takeaway()` states the
   finding underneath in one computed sentence, and `driver_table()` lists every driver
   with its meaning and a Total row -- it calls `root_drivers(top=99)`, so nothing is
   folded there and the chart's `Other` can always be looked up in full.

   **`Other` names itself on hover.** An `Other` row on a leadership chart is only honest
   if the reader can find out what is in it without leaving the chart, so its tooltip
   lists every driver it swallowed with each one's count -- "2 smaller drivers: Portal
   Visibility Issue (1), System Limitation (1)". Three things had to be true for that to
   work, and two of them were not:

   * **`hovermode="y"`**, so the tooltip fires anywhere along the row rather than only on
     the bar. A one-miss bar is fourteen pixels wide, and `Other` and `Needs Review` are
     exactly the short ones -- the rows a reader most wants explained were the hardest to
     hit.
   * **The text is wrapped with `<br>` at 44 characters before it reaches plotly.**
     Plotly's hover label does not wrap and is not clipped to the panel: at a third of
     the page width the meaning ran off both edges and lost its own ends.
   * `plural()` writes "1 confirmed miss" and "2 confirmed misses". A leadership page does
     not print "miss(es)".

   **Verifying a tooltip needs plotly's own API, not a synthetic mouse.** Playwright's
   `mouse.move` fires no hover on any chart on this page -- checked against all eight, not
   assumed -- so the test drives `Plotly.Fx.hover(gd, [{curveNumber, pointNumber}])` and
   reads `g.hoverlayer`'s text back. That tests the hovertemplate and its customdata,
   which is the part that can actually be wrong. The clipping was only visible in a
   screenshot taken while the label was up.
5. **Customers impacted** -- `miss_by_customer()`, the eight worst as a stacked bar and
   **every** account in a scrolling table. The row carries **both bases**: `Emails` with
   `Complaints` and `Inquiries` beside it (every email that named the account), then the
   failure columns and `Misses` (confirmed misses only, a smaller number from a different
   base). "44" on its own does not say 44 of what. It is a scroll box, not a collapsed
   expander: a collapsed expander lays out at zero height, so `innerText` reads empty and
   `audit_pages.py` silently stops reconciling every row it hides. All 33 accounts are
   audited because of that choice, and the table is `variant="wide"` so seventeen columns
   do not wrap every header into seven lines. The total row is `position:sticky` at the
   foot of the box (`stickytotal`, added only when `height` is set -- on a table that does
   not scroll, `bottom:0` would pin the row to the *page's* scroll instead), because
   otherwise the one row a reader opens the table for sits twenty-three rows below the
   fold.

   **Its total row does not add the columns up, and that is the fix for a real bug.** The
   rows deliberately double-count: accounts split on the slash, so an email naming two of
   them appears on both rows. Adding the columns gave **120 emails against a tracker of
   115**, 81 misses against 78, and 27 / 24 / 13 where the miss chart directly above said
   26 / 23 / 12 -- a table whose own total contradicted every other number on the page,
   which is the first thing a reader challenges. Exactly five emails name two accounts
   (three `Ford/GM`, one `Eaton/Ford`, one `Penske/Ford`), three of them misses.
   `customer_totals()` returns the distinct counts and `excel_bar_table(..., totals=...)`
   prints those, with a computed caption naming the overshoot so the gap is explained
   rather than noticed. The `% of Total` column keys on the tracker's own miss count too
   -- it was a share of the exploded 81, a base that appears nowhere else.

   **The general rule: a total row is a reconciliation, not a sum.** Where the rows
   double-count on purpose, the foot has to carry the figure the rest of the dashboard
   uses, and the caption has to say why they differ.
6. **Complaints by event type** -- two charts and one table. `all_event_types()` is
   every email by the kind of event it was about; `missed_event_types()` is the confirmed
   misses only. Neither is readable alone: nine misses is a different fact depending on
   whether ten emails named that event type or forty.

   **One split per table.** `event_type_pairs()` briefly carried `Reported timely` and a
   `Miss rate` as well, which put **two different partitions of the same 16 emails on one
   row** -- 14 complaints + 2 inquiries, and 13 misses + 3 reported timely. A reader lands
   on 14 against 13, tries to reconcile them, and cannot, because they are not the same
   cut. The page's owner read that as broken arithmetic, which is the correct reading of
   two partitions printed as one table. The columns are now
   **Emails = Complaints + Inquiries**, and the caption names the misses column as a
   **subset of the complaints** rather than a third part of the split, with the Factory
   Fire row spelled out: 14 complaints of which 13 were misses, the fourteenth reported
   and complained about for some other reason.

   **The general rule: a table carries one partition.** A second one that happens to sum
   to the same total is not extra information, it is an invitation to subtract two
   numbers that do not belong to each other. Put it in its own table or name it as a
   subset.

   **`event_type_note()` works the biggest event type through, and every figure in it is
   computed.** The caption used to end "the fourteenth was reported, and the customer
   wrote in about something else on it", and the owner asked the obvious question: what
   else. A caption that waves at a category without naming it is the fault it was written
   to prevent. It now names the customer's **own `Reason` wording**, not the folded
   category -- "Classified wrongly" is still a bucket name, where *Incorrect Industry
   selection* says we reported the fire and the Automotive tag was missing, which is a
   different complaint from not reporting it. Three wordings at most, then "and N other
   reasons", and it follows the filter so it cannot go stale.
7. **Is it getting better** is NOT on this page -- it was removed on the owner's call
   and lives on Monthly trend alone. What it does, unchanged: `trend_chart()` is **one
   bar per month**, its percentage printed on it, the last three months blue and the
   three before grey, months outside both windows dark so they cannot be mistaken for
   part of the comparison. It was a line with two flat shelves drawn over it and a
   signed delta on the plot, and a reader had to be told what the shelves meant before
   the chart said anything. The comparison is stated in words by `missed_verdict()`
   above the chart instead of drawn into it, and `trend_table()` puts the months
   underneath with a total whose rate is **pooled, not averaged**.

8. **Nature of complaints** -- the eight `REASON_CATEGORIES`, the same vocabulary the
   All customer emails tab defines and lists the wordings behind. **The bar is stacked
   on the miss split**, darker for the emails in that category that were a confirmed
   miss and grey for the ones where the event did reach the customer, and a computed
   caption states the arithmetic: `Event missed` carries 63 misses against 78 on the
   cards, and the other 15 sit in categories where the event *was* reported and
   something else went wrong. That gap reads as an error every time somebody meets it,
   and it is not one -- the category is what the customer wrote about, the flag is
   whether the event reached them in time. Showing the split on the bar, and printing
   `63 + 15 = 78` under the table, is what stops it being asked a third time.

**The deeper root cause is NOT on this page.** `render_deeper_root_cause()` was the
seventh section here and the owner moved it to the internal page, where it already
ran: Root cause calls the same function directly under this page's own root-cause
block, so nothing was lost and nothing was duplicated -- the summary simply stops at
the three root causes and their drivers, and the reader who wants every failure in the
taxonomy clicks through. What it does, unchanged:

**The deeper root cause** -- `root_frame()` and `grouped_bar()`: every failure in the
taxonomy on its own row, two bars each -- how many emails named it, and how many of
those were confirmed misses. Both numbers together is the point: `Review` is 22 emails
of which 19 were misses, `Process Clarification` is 13 of which 2 were, and a chart of
misses alone cannot say which failures we mostly get away with. It replaced two
sunbursts whose outer rings were unequal wedges where past the biggest four no label
would fit. Keyed on the failure, **not** on failure-and-owner: the same sub-type sits
under two owners on several rows and a y axis that repeats a label silently merges
them, so the owners are a column naming them with their counts -- as pills now, not
as a run of text. It groups on the **label**, not the tracker value, so the two
clubbed pairs are one row each and both their tracker values are listed on it.
**Nothing is folded into an `Other`**, however few emails carry it.

**`Alerting Gap` is a `Sub-type`, and it is not `Captured Late`.** The owner's definition:
a relevant article or feed *was* captured by the Product-controlled harvesting flow, but an
ingestion, database, portal, UI or workflow failure stopped it reaching analysts as a usable
item in time. It explicitly excludes a source or vendor that never captured it, a keyword
miss, wrong clustering, an analyst marking it Not Impactful, and a published item the
customer could not see. Four rows carry it: Bain Fire and Thales (Collins Aerospace), EAO-12
(Ford) and EAO-39 (Belden), all `Notification Visibility Monitoring`. **Three of the four
are misses.** EAO-39's TSMC row keeps the sub-type -- the gap was real, the article was
captured and never surfaced to analysts -- but Belden confirmed on 22-Sep-2026 that TSMC
is not mapped in their BOM, having mapped Taiwan Semiconductor Co., Ltd., a different
company in different commodities with a near-identical name. **No notification was owed
to Belden, so it is an inquiry and not a miss.** The defect stays recorded as what
happened; the customer-specific miss claim does not survive their own confirmation.
**EAO-39 covers two separate events on two rows** -- the TSMC capacity reduction and a
Murata MLCC product line discontinuation, People / `Review`, still a miss. Match on the
title, not the key.

**`("Product", "Captured Late")` must not share the `Alerting Gap` label**, and it briefly
did -- the label was invented here before the owner defined the category, so the Suntory row
would have been counted as an Alerting Gap on Root cause. `Captured Late` is "our first
usable capture came late"; `Alerting Gap` is "we had it and the analyst never saw it". The
elapsed hours do not decide it -- **the failure stage does**: Bain Fire and Sandy Fire are
hours apart and sit under different owners, because Bain never reached the portal and Sandy
reached an analyst who deprioritised it.

## The V1 cause taxonomy

Ten `Sub-type` values were added on the owner's call and seventeen rows migrated onto
them, in three commits on one branch: Definitions, then rows, then the app's maps. **That
order is not a style preference.** `validate.py`'s `enum_definitions` refuses a value in
use with no row on the Definitions sheet, so rows before definitions cannot be pushed;
and a row whose `(Root Cause, Sub-type)` pair is not in `DRIVERS` renders as
`Needs Review` on Root cause, so the middle state is visibly wrong by design and the
branch is not merged until the third commit closes it.

| Sub-type | What it means | Owner it sits under today |
| --- | --- | --- |
| `Published Late` | available to analysts in time, published or escalated materially late | People |
| `Methodology Weakness` | the workflow ran as designed and the guidance itself was deficient | Process |
| `Deliberate Rule` | the published rule applied, and the customer queried the rule | Process |
| `Platform Bug` | a confirmed defect that is none of the four specific Product ones | Product |
| `Mapping / Routing Defect` | wrong data, coordinates, tenant or entity linkage selected the wrong target | Product |
| `Supplier / Site Not Shared` | the site was never in the customer-provided data | Process |
| `Analyst Review Miss` | a person had it and closed, deprioritised or under-researched it | People |
| `Supplier Selection Miss` | the supplier was on file and left off the initial selection | People |
| `Clustering / Duplication Defect` | stories grouped, split or duplicated wrongly | Product |
| `Model Classification Defect` | an automated model assigned the wrong event, relevance or impact | Product |

**A documented root cause is not a delivered RCA, and the two fields say different
things.** EAO-49's cause is established -- the analyst did not research beyond Bangkok --
and the ticket is still Open with no RCA attached, so it is `Clarification Provided`, not
`RCA Shared`. The row left `Pending` only because the sub-type it needed did not exist;
the status followed the evidence, not the migration.

**`Methodology Weakness` is `Process`, not `Product`.** A deficient methodology is a
Process failure by definition however the model behaved under it, so EAO-13 moved owner
and routing with its sub-type. The same row carries the file's one worked example of
**superseding** an explanation rather than deleting it: its RCA had named the company's
absence from the supplier database as a ground for the Not Impactful call, that wording
had already gone to the customer, and supplier mapping was not in fact a dominant input
to the classification. Both `RCA Details` and `Comments` were rewritten together and both
end with an explicit supersession sentence. **Correcting one and leaving the other is the
failure mode here** -- the row then contradicts itself, and the stale half is the one a
reader meets first on the record card.

**New values do not retire old ones.** `Policy/Logic`, `Mapping` and `Prioritization` each
still carry a row that was deliberately not migrated for want of evidence, and
`Captured Late` now carries none yet stays defined: `DRIVERS` holds
`("People", "Captured Late")` against a future row, and the `Alerting Gap` definition
names `Captured Late` as the category it is not. A value with no rows costs nothing; a
value removed from under a definition that cites it costs a gate failure.

**`Event Identification` was retired on 18-Oct-2026, and the reason is the test for
retiring any value: it named no failure of its own.** The owner's definition was "the
product classified it incorrectly, or the analyst", and both halves were already taken --
the model's wrong call is `Model Classification Defect`, the analyst's is `Review`. Its
label, "Classified as not impactful, wrongly", therefore read as a second wording for
`Review` on every chart that drew the two side by side, which is how it was found: the
owner asked why two rows of one popup said the same thing.

**Reading the ten rows it held showed the same thing from the data end, and four of them
were not classification failures at all.** The record's own `Comments` carried the cause
even where `RCA Details` was blank:

| Row | Its own Comments | Now |
| --- | --- | --- |
| Ford, Stark Manufacturing closure | "Feed harvesting gap" | `Product` / `Keyword Update` |
| Ford, Highway 57 blockade | "source coverage + keyword gap identified" | `Product` / `Keyword Update` |
| Caterpillar, Isselguss fire (EAO-9) | "captured by feeds but incorrectly clustered" | `Product` / `Clustering / Duplication Defect` |
| Ford, Linamar facility fire | "human review missed company-facility validation" | `People` / `Review` |
| Ford, Snowstorm forecast | "moved to monitoring incorrectly" | `People` / `Review` |
| Ford, Mexico highway blockades | "AI correctly classified, but analyst assessed as localized" | `People` / `Review` |
| Ford, Canadian wildfire smoke (EAO-21) | analyst did not assess the event correctly | `People` / `Review` |
| Eaton, Schaeffler CO2 leak (EAO-4) | an analyst overlooked it | `People` / `Review`, routing moved |
| Caterpillar, Spain railway strike | event notified with no WarRoom attached | `People` / `WarRoom Creation` |
| Ford, Severe weather, Midwest | monitored correctly, escalated after the customer email | `People` / `Published Late` |

**Linamar is the one that was nearly filed as a Process miss, and the owner settled it
as People.** The analyst skipped the company-mapping check before marking the story Not
Impactful, which reads as a process failure -- but the process existed and worked; a
person did not follow it. `People` / `Review` with the process-adherence finding in
`Comments`, and **Process still carries zero confirmed misses**, which is what keeps the
Executive Summary at two root-cause cards.

**Severe weather, Midwest is the worked example of `Published Late` against `Review`.**
The guidance notifies thunderstorms and tornado warnings only on confirmed impact, and
while the event was at warning stage it was correctly held under monitoring -- so no
decision was wrong. What came late was the escalation once structural damage in Hardin
County and Kenton met the criteria, and the bulletin went out only after Ford wrote in.
`Review` would say we looked and declined; we did not. The Collins Aerospace Sandy Fire
row is the precedent, filed `Published Late` on the same shape. **The line between the
two is whether a decision went wrong or a clock did.**

`Model Classification Defect` took `Event Identification`'s place in both `MISS_BUCKETS`
rules and in `audit_pages.miss_buckets()`, rather than the Product rule losing a member:
that rule exists to say "the model misjudged a captured event", and it is now the only
Product-rooted value that means it.

**Three more rows left `Mapping` on 18-Oct-2026, and the common fault is the same one
that emptied `Event Identification`: a record's own `Comments` describe the symptom, and
`Mapping` is what a symptom of "nothing reached them" reads like.**

* **Ford, Eason & Co factory fire.** Its Comments read "Event not triggered due to
  company not mapped as Ford supplier", and it was filed `Product` / `Mapping` for
  years. The owner settles it as **the same failure as the ADM data breach row
  (EAO-51)**: the articles were captured, the classification models categorised them
  Not Impactful, and the human-in-the-loop review did not correct it. `Product` /
  `Model Classification Defect`, with a supersession sentence on the Comments. **Its
  `Automation Opportunity` and `Standard Automation Focus` still carry the mapping
  theory** ("not mapped" explanation template, `Entity & Supplier Resolution`) and were
  left as they are pending the owner's wording -- the Bombardier precedent says the
  remedy follows the cause, so this is an open loose end, not a settled row.
* **Harman, Murata cyber attack (CAN-3298).** 45 Murata sites met the impact criteria
  and impact-confirmation requests went to 41. The four omitted Tier 2 sites met the
  customer settings and the impact-region criteria, so **the targets were on file and
  the system did not send to them** -- an engineering shortfall, not a mapping gap.
  `Product` / `Platform Bug`, still a miss. Its `Improvement VS Bug` still reads
  `Improvement`; the row's own RCA records that no root cause was ever documented, so
  the field was not flipped to `Bug` on inference.
* **META, Samsung DRAM (EAO-15).** This one crosses owners, and it is the case for
  reading a normalization RCA sceptically. The RCA said the Samsung Electronics sites
  are normalized under Samsung and that normalization "was not applied during the
  impacted-site assessment" -- which reads as a platform defect, and it is not.
  **Samsung Electronics is also mapped as Samsung in the portal for this customer**, so
  the supplier was on file under a second name. The analyst checked Samsung Electronics
  and did not check Samsung, so the sites were never selected and no WarRoom was
  created. `People` / `Supplier Selection Miss`, routed to EventWatch Ops, `Missed_Flag`
  still Yes because nothing reached META. Both `RCA Details` and `Comments` were
  rewritten together with an explicit supersession sentence, per the EAO-13 rule.

**`Supplier Selection Miss` now carries its first miss.** The other two rows on it
(Caterpillar / Dana, META / Bangkok) are `Missed_Flag = No`, matching the original
People / `Mapping` precedent where the WarRoom was published and the supplier was left
off it. EAO-15 is the other shape: the supplier was left off and **no WarRoom was
created at all**, so nothing reached the customer. **Leaving a supplier off a published
WarRoom is not a miss; leaving one off so completely that no WarRoom exists is.**

**The Executive Summary's "Seen, but overlooked" card selects on the OWNER, not on a
bucket index.** It read `bucket(MISS_BUCKETS[2][0])`, which counted only the sub-types
that one rule happens to name, so a People miss whose sub-type moved out of that rule --
`Prioritization` becoming `Published Late`, `Review` becoming `Analyst Review Miss` --
silently left the summary while still counting as a miss on every other page. The card's
own words, "captured, but an analyst did not raise it", are true of every People-rooted
miss by definition, so `int((flag.eq("Yes") & root.eq("People")).sum())` is both the
honest reading and the one a sub-type added tomorrow cannot go stale against. **Do not
put this back on a bucket index.**

**`MISS_BUCKETS` and `audit_pages.miss_buckets()` name the same sub-types or the audit
fails.** `Analyst Review Miss` joined the analyst and model rules in both, in one commit.
The audit recomputes the buckets from the CSV independently, so a sub-type added to one
list and not the other does not drift quietly -- it fails, which is the point.

**Every pair in the tracker is mapped, and that was the last fix.**
`("Process", "Mapping")` -- the Ford Sandy Fire mapping clarification -- predates this
taxonomy and rendered as `Needs Review` for want of a label rather than for want of a
decision, which is the one thing `Needs Review` must never mean. It took a display
mapping (`Mapping Clarification`) and no change to the row. **Check this after any
migration**: a correctly classified row sitting in `Needs Review` turns a data-quality
signal into noise, and a reader who learns to ignore it will ignore the real one.

**`DRIVERS` is keyed on `(Root Cause, Sub-type)` -- never on the display wording.**
It gives each pair EventWatch's own name for the failure and the same thing in plain
English: the term is what the chart prints, the plain English rides on the hover and
fills a column of the table, so the page reads to a VP without costing an analyst the
word they file records under. `Source Coverage` is `Source Miss`, `Keyword Update` is
`Keyword Miss`, Product-rooted `Review` and `Relevancy` are both `Model Miss`,
People-rooted `Review` is `People / Analyst Miss`, and `Visibility` and `WarRoom
Creation` are both `WarRoom Issue` -- the tooltip for which says "missing, delayed,
duplicated, or not visible", which is why both belong to it.

**`WarRoom Creation` is mapped under People as well as Process**, and the Caterpillar
Spain row is why. Notifying an event and raising its WarRoom are two steps issued
together; there the event went out with no WarRoom attached and one was created only
after the customer wrote in. Only the Process-rooted pair had a mapping, so a correctly
classified record would have rendered as `Needs Review` -- the bucket that must only
ever mean "nobody decided".

**A pair that is not in the map counts as `Needs Review`, and never folds into `Other`.**
Talking an unmapped pair into the nearest plausible heading is how a taxonomy stops
meaning anything, and burying it in `Other` is how a mis-filed row stays mis-filed.
`Needs Review` is a data-quality signal, so it is always its own row.

**It found three mis-filed rows on its first run.** All three were data faults rather
than gaps in the map -- the `Sub-type` did not describe what had failed -- and **all three
were settled by the tracker's owner, not by reading the record**. The first pass got every
one of them wrong, and how it went wrong is the lesson:

* **Bombardier / STELIA ransomware** (CSV row 52) is `Product` / `Source Coverage`.
  Its Comments read "STELIA is listed supplier but no WarRoom/notification created",
  which reads as a WarRoom that failed to fire on a correctly mapped supplier. The email
  thread says otherwise: *"the feed associated with that URL has not been received by our
  application."* **It never entered the portal at all** -- a source miss, not a WarRoom
  issue. A supplier being listed says nothing about whether the story arrived. Its
  `Automation Opportunity` read "Mapping validation" and its focus
  `Entity & Supplier Resolution` -- both of them the mapping theory the thread disproves,
  and both since corrected on the owner's instruction: the remedy is feed-receipt
  verification on a source URL raised in an escalation, and the focus is
  `Dynamic Source Discovery`, where the four other feed-not-ingested source misses
  already sit (CSV rows 16, 18, 20, 23). `RCA Details` was blank and now carries the
  thread's own finding -- the URL raised was the page URL, not the news source URL, and
  the feed behind it had not been received -- kept close to the wording rather than
  elaborated, per "Do not invent RCA narrative".
* **Sandisk / EAO-37** (CSV row 103) is `People` / `Review` -- an analyst overlooked it.
  Its own RCA says "delayed in reporting", which reads as a timing failure and was filed
  under `Captured Late`. The delay was the *symptom*; the analyst missing the story was
  the cause. **An RCA describing what the customer experienced is not an RCA naming the
  cause.**
* **HPE / SEC notification** (CSV row 24) is `Process` / `Process Clarification`. The
  news was not available in the public domain and a clarification went back. "Not
  captured/provided on time" reads as lateness and was filed under `Captured Late`.

**The pattern in all three: the symptom the record describes was mistaken for the cause,
and in each case the cause sat somewhere the tracker does not hold** -- an email thread,
or the owner's own knowledge. Where a row's fields do not settle it, the honest move is to
leave it in `Needs Review` and ask, not to reclassify it into something plausible. That is
what `Needs Review` is for, and these three are why it earns its place.

`DRIVERS` carries `("People", "Captured Late")` although no row uses it: the People
vocabulary has no word for lateness, so a future row on that pair would land in
`Needs Review` for want of a label rather than for want of a decision.

## The miss definition: delivery and timeliness

**This is the governing test and it supersedes the "did a bulletin reach the customer"
wording in the October rulings below.** Settled on 15-Oct-2026 after the six October
cases were re-read against each other and found to disagree.

> **Did an EventWatch notification reach THIS customer, and reach them in time to act?**
> Reached them in time -> **not a miss**. The complaint is about scope, supplier
> selection, WarRoom handling, duplication, accuracy or visibility.
> Reached them late, or not at all -> **miss**.

Three clauses do the work, and each exists because a row broke without it.

**"THIS customer", not "published".** Published to the world and invisible to one
account is not reached. TS-22695 is the proof: the Uber Freight bulletin went out on
13-Aug-2026 and incorrect industry selection kept it off the Red Cross portal, so for
them nothing arrived. The October ruling read "published" as "delivered" and filed it
`Missed_Flag` No; it is a miss. **Any ruling that turns on "a bulletin was published"
is resting on an assumption the tracker does not record** -- there is no field holding
what appeared on a customer portal on a given day, and that gap decides the hard rows.

**"In time to act", not "eventually".** Customer awareness through news, suppliers,
internal operations or public reports does not remove a miss; the obligation is timely
EventWatch notification. Without this clause the twelve `Reported late` rows -- 18 hours
to 25 days, Collins Aerospace carrying four of them -- all stop being misses, and
`Published Late` becomes a sub-type that can never hold one. In every one of the twelve
the customer learned of the event from their own channels and then asked us why we had
not told them. **Reported Late is a valid miss category.**

**A notification has to be owed.** It is owed where the affected supplier or site is
mapped from customer-provided data, **or where another detection path should have carried
the event** -- reporting is not driven solely by supplier mapping, which is the Eaton
Axios npm precedent, where a product connection made a record a miss although the
supplier mapping did not. Where neither holds, non-delivery is not a miss: Belden
confirmed TSMC was not in their BOM (EAO-39, below) and NVR had never shared the Kinston
site, so nothing was owed to either.

**Timing of the correction is not the test and was tried as one.** "We only notified or
corrected it after the customer emailed" classifies Spain, EAO-6 and EAO-49 as misses,
and all three are records where the customer already had the bulletin and complained
about its contents. Do not reach for it.

**Three populations, and they partition the tracker:**

| | |
| --- | --- |
| **Miss** | not delivered, or delivered too late |
| **Process Issue** | delivered in time; supplier selection, impacted entities, geofence, scope, WarRoom decision, duplication or impact assessment was wrong afterwards |
| **Inquiry** | clarification, configuration, policy explanation or informational request |

`Root Cause` and `Missed_Flag` are **independent axes**. A Product defect that did not
stop delivery is a Process Issue with a Product root cause -- CAN-3242 is one, where a
query timeout kept a delivered notification off the supplier portal. "Product Miss" means
Product root cause **and** `Missed_Flag = Yes`, not Product fault alone.

**Baseline on 18-Oct-2026**, and every figure below reconciles:

```
127 emails     = 103 complaints + 24 inquiries
103 complaints = 86 confirmed misses + 17 process issues
 86 misses     = 51 Product + 35 Analyst
Product 51 = source 24 + keyword 18 + model classification 4
           + alerting gap 3 + platform bug 1 + clustering 1
Analyst 35 = analyst miss 28 + published late 4
           + supplier selection 1 + industry selection 1 + tagging 1
```

**Counts written into prose elsewhere in this file are historical snapshots.** 78 misses,
115 emails, 97 complaints and 17 or 20 non-miss complaints all appear below and all
predate this baseline; they are kept where they explain why a thing was built, and are
not a second source of truth. The four gates are.

## The October rulings: what counts as a miss

Six cases were settled by the owner against one test: **did a bulletin reach the
customer.** If it did, the record is a publishing-quality complaint and `Missed_Flag`
is **No**, however wrong the bulletin was. If it did not, it is a miss, and the
sub-type names where delivery stopped. **That wording is superseded by the section
above** -- it says nothing about whether delivery reached *this* customer, and nothing
about lateness. Five of the six rulings survive the correction unchanged; the sixth
is marked below.

| Case | Now | `Missed_Flag` | Why |
| --- | --- | --- | --- |
| Spain railway strike (Caterpillar, 20-Feb) | `People` / `WarRoom Creation` | **No** | the event was notified with no WarRoom attached; one was created after the customer wrote in. Sub-type corrected 18-Oct; the flag is unchanged |
| LPG/LNG shortage (Caterpillar, 18-Mar) | `Product` / `Model Classification Defect` | Yes | the model classified the captured event Not Impactful; review did not correct it |
| HPE SEC notification (25-Mar) | `Process` / `Process Clarification`, **Inquiry** | **No** | the news was not in the public domain, so there was nothing to report |
| EAO-13 FXI foam fire (Ford) | `Product` / `Model Classification Defect` | Yes | captured, then classified Not Impactful by the model |
| EAO-15 Samsung DRAM (META) | ~~`Product` / `Mapping / Routing Defect`~~ **`People` / `Supplier Selection Miss`** | Yes | **superseded 18-Oct.** The supplier was on file under two names and the analyst checked only one. See below |
| Uber Freight (Red Cross, TS-22695) | `People` / `Industry selection` | ~~No~~ **Yes** | **superseded 15-Oct.** Published on 13-Aug, but incorrect industry selection kept it off the Red Cross portal and a customer-specific treatment existed only after they chased it. Nothing reached them. The ownership was right; the flag read "published" as "delivered" |

**The discriminator that now does the most work is who made the Not Impactful call.**
A model that misjudges a captured event is `Product` / `Model Classification Defect`; a
person who does is `People` / `Review`. The tickets answer this where anyone asked.
EAO-1 is explicit -- *"incorrectly classified as Not Impactful by the analyst"* -- and so
stays `People` / `Review`. EAO-23 is the opposite: Ankit Gupta states *"the AI initially
classified the news as not impactful"*, which makes it a model defect by this rule. **It
was left as `People` / `Review` on the owner's instruction**, along with EAO-33 and
EAO-25; they are known and not in scope. Do not "fix" them.

**Process now carries zero confirmed misses.** All four moved: two to Product, one to
People, one off the miss flag entirely. The Executive Summary and Root cause therefore
draw **two** root-cause cards and one fewer driver chart, and `smoke_app.EXPECTED` was
lowered to match -- which is only legitimate because the missing chart is a real absence
in the data. **Check that before lowering a minimum again**; otherwise it is a gate being
filed down to pass.

`Methodology Weakness` carries no rows. It stays defined, for the same reason
`Captured Late` does. `WarRoom Creation` carried none until the Spain row moved onto it.

**Two things could not be verified and were not guessed.** Jira attachments are not
readable from here -- the content endpoint returns 403, no credential is available to the
shell, and the MCP exposes no download tool -- so where an RCA lives only in an attached
document, the ticket's comments are the whole of the evidence -- EAO-10, EAO-14 and
EAO-34 are all in that position, and none of them was edited on the strength of a
document nobody here can open. **And EAO-13 and
EAO-25 give contradictory accounts of the same FXI Cuautitlan fire**: EAO-13's RCA says
EventWatch captured the reports and the model misjudged them, while EAO-25's engineering
comment says *"Not captured by vendor due to source miss"*. The owner's ruling follows
EAO-13. The contradiction is recorded here because it is unresolved, not because it is
settled.

## The definitions, settled against the original tracker

**When a classification is in doubt, read the 80 rows the humans filed before any of
this existed** -- `git show a497a0d:customer_tracker.csv` (cp1252, not utf-8). That is
the authority, not the taxonomy derived here afterwards, and the owner said so in terms.
It settles the three cases that keep recurring:

**"Analyst overlooked" has a precise meaning, and it is the test for `People` / `Review`.**
The owner's definition: *the news came on the portal, but the analyst did not look at it
carefully and moved it to Not Impactful.* Three things have to be true, and each one
rules out a neighbouring sub-type:

| | and so it is not |
| --- | --- |
| the story **was ingested** -- a monitored source carried it | `Source Coverage` |
| it **reached the analyst portal**, so it was retrievable and visible | `Keyword Update`, `Visibility` |
| **a human had it in front of them** and closed it as Not Impactful | `Product` / `Review`, which is the model making that call |

The failure is the quality of the look, not the reach of the system. That is why
"the customer says we missed it" never settles the file on its own: a miss whose story
never arrived and a miss whose story arrived and was waved through are the same event to
the customer and two different problems to us, with two different owners.

**`People` / `Review` -- we had the story, a human reviewed it, and the human did not
raise it.** The original rows say it outright: *"analyst classified event as Not
Impactful"* (Eaton, row 57), *"Event was captured successfully but incorrectly assessed
as Not Impactful"* (Western Digital, 63), *"Human-in-the-loop review did not escalate the
event"* (Ford/EAO-23, 70), *"human review incorrectly marked"* (Merck, 80 and 81). Of the
fifteen original `People`/`Review` rows, thirteen carry `Missed_Flag = Yes` -- because
nothing reached the customer. **This is the analyst miss, and it is not a source gap.**
An event we captured and then declined to publish has nothing to do with coverage, so
`Product`/`Source Coverage` is the wrong file for it however the customer worded the
complaint.

**`People` / `Mapping` -- the event WAS published; the supplier was left off the
WarRoom.** One original row, and it is the template: Caterpillar, *"Dana Holding
Corporation was not included in impacted supplier selection during initial WarRoom"*,
`Missed_Flag = No`. The humans' own call was **No**, because the customer did receive the
event -- what they did not receive was their own supplier on it. EAO-49 is the same
shape and carries the same flag.

**`Product` / `Source Coverage` -- the story never arrived.** Nothing to review, nothing
to publish, because no monitored source carried it.

**So `Missed_Flag` tracks delivery of the event, not the quality of what was delivered.**
Yes when the event did not reach the customer at all or in time; No when it reached them
and something about its scope, tagging or supplier list was wrong. That is why two
records both rooted in an analyst error -- EAO-48 and EAO-49 -- carry different flags.

Applied on the owner's instruction:

* **EAO-48** (Ford, South Africa port and corridor congestion) was `Product` /
  `Source Coverage` with a regional-monitoring remedy. It is an **analyst miss**: we had
  it and overlooked it. Now `People` / `Review`, routed to EventWatch Ops, focus
  `WarRoom & Decision Validation`, remedy rewritten to a Not-Impactful decision check.
  `Missed_Flag` stays `Yes` -- nothing reached Ford.
* **EAO-49** (META, Delta Electronics site missing from the initial WarRoom) needed no
  change. `People` / `Mapping`, `Missed_Flag = No`, matching the Caterpillar precedent
  exactly. **It is not a missed event**: the WarRoom was published, the supplier was not
  on it.
* **EAO-50** (Ford, planned strike at AGC Display Glass, Taiwan) is the clearest case of
  the pattern: monitoring picked up the 30-Sep report and editorial review classified it
  `Not Impactful`, so no alert and no WarRoom were published. `People` / `Review`,
  `Missed_Flag = Yes`. The ticket asked EventWatch to confirm whether an analyst or
  automated logic made that call, and **the owner confirmed an analyst**: the story
  reached the portal and was moved to Not Impactful without a careful assessment. The
  row stands; had it been automated logic it would be `Product` / `Review`.

## The vocabulary, and the two rules that hold it together

`PLAIN_SUBTYPE` was rewritten wholesale on the owner's wording. `Source Coverage` is
**Source not in our vendor or monitoring network**, `Keyword Update` is **Keyword Miss**,
`Review` is **We saw it and chose not to report it** -- the second pass at that label,
because "Seen at review, and not raised" never said what review *is*, and the sub-type
sits under both People (an analyst) and Product (the model). Describing the **decision**
is the one thing true of both. `Mapping` is owner-aware and explained below,
`Visibility` is **Published, but not visible to the customer**, `Process Clarification`
is **We had to clarify the reporting guidelines**, `WarRoom Creation` is **WarRoom
Missed**, `Relevancy` is **Judged not relevant to this customer**.

**Two pairs deliberately share a label**, which is what the owner meant by clubbing them:
`Prioritization` and `Captured Late` are both **Captured, but notified late**; `Tagging`
and `Industry selection` are both **Incorrect industry selection**. Both tracker values
survive and ride together in the `Tracker value` column ("Prioritization · Captured
Late"). The cost is stated plainly because it is real: a ranking judgement and a pipeline
delay are now one row, so the dashboard can no longer separate "we deprioritised it" from
"we were slow". The owner asked for the customer-visible outcome, and that is what the
label now says.

Everything that aggregates on a label has to **sum into it, never key on the sub-type**,
or the second value of a pair silently overwrites the first. Three places do this and all
three were changed together: `root_frame()` groups on the label, `account_failures()`
groups on the label, and `audit_pages.miss_buckets()` uses `+=`. Written the obvious
way, `Incorrect industry selection` read 1 where the tracker holds 2.

**`Mapping` is the one sub-type whose meaning changes with its owner, and the three
meanings are different failures rather than variants.** The owner settled this:

| Owner | What actually happened | Label |
| --- | --- | --- |
| Product | the supplier is not in the customer's mapped supply chain at all -- they never shared the company with Resilinc, so there was nothing for the event to match against | Supplier was not mapped by the customer |
| People | the supplier **was** mapped, and an analyst left it off the WarRoom or its geofence when the WarRoom was built | Supplier mapped, but left off the WarRoom |
| Process | neither: the customer asked why the mapping behaved as it did, and a clarification went back | Supplier mapping queried by the customer |

**The three owner counts were 6 / 2 / 3 when this was written and the tracker now holds
one Product row and one Process row.** `Mapping` has been the collecting bucket for
every miss whose symptom is "nothing reached them", and the V1 taxonomy has been taking
its rows back one evidenced ruling at a time -- People's two to `Supplier Selection
Miss`, and on 18-Oct Eason to `Model Classification Defect` and Murata to `Platform
Bug`. **The owner-aware labels stay regardless of the counts**: `OWNED_SUBTYPE` must go
on handling all three, because the next row filed under `Mapping` will be filed under it
for the same reason, and `failure_label()` is what stops the Product wording appearing
over a People row.

**A customer-side data gap is not automatically `Product`, and the NVR row is why.**
NVR, 09-Oct-2026: their MasterBrand Kinston site was never shared with Resilinc, so the
Kinston layoff bulletin published with no WarRoom for them. The Product wording -- "the
supplier is not in the customer's mapped supply chain at all" -- describes that exactly,
and it was filed `Product` / `Mapping` as a Complaint. **The owner reversed both.** It is
`Process` / `Mapping` and an **Inquiry**: nothing in the platform and nothing an analyst
did failed, the customer is only asking why no WarRoom appeared, and the remedy the owner
named is **our process for gathering site data from the customer**, not a platform change.

So the discriminator between the Product and Process rows of this table is **not** whose
data was missing -- it can be the customer's in both. It is whether the customer asserted
a failure or asked a question, and whether the fix lands on the platform or on how we
collect their data. Where it is a question and the fix is a process, `Routed To` follows
`Root Cause` to EventWatch Ops and `Severity` goes `Low`, matching the two
`Process` / `Mapping` inquiries already on file.

**And a source-coverage question asked alongside is not an allegation of a miss.** NVR
also asked whether four named outlets are in the monitoring network. EventWatch had
already published a bulletin on the event, so monitoring plainly carried it -- the ask is
coverage *validation*, and reading it as evidence of a gap would have manufactured a
second failure out of a customer's reasonable question.

`PLAIN_SUBTYPE` is keyed on the sub-type alone and printed the Product wording over all
three, which **blamed the customer for a supplier they had mapped** on Caterpillar EAO-6
and META EAO-49. `OWNED_SUBTYPE` overrides it where the owner is known and
`failure_label(root, subtype)` is the one accessor; `labels_for(frame)` applies it row by
row. Every block that knows the owner goes through it -- the sidebar filter, the record
grid, the miss-bucket tail, the heatmap, `owner_accounts`, `owner_insight`,
`account_failures`, `root_frame` and `name_subtypes(..., root=)`. `DRIVERS` already had
this right (`Supplier Impact / Mapping` against `Supplier Selection`); only the sub-type
label lagged.

**`audit_pages.miss_buckets()` keys on the pair too**, not the sub-type alone. No missed
record carries People/Mapping today, which is exactly why an owner-blind lookup there
would have filed the first one that did under the Product wording and disagreed with the
app silently.

**Do not look for a single wording that covers two owners.** Where the owner changes what
happened, the answer is two rows, not a vaguer label -- the same argument that keeps
`Review` split across two `MISS_BUCKETS`.

**No label names an actor where the tracker puts that sub-type under more than one
owner.** `Review` is 26 People and 2 Product, `Mapping` sits under all three, and
`Relevancy`'s single record is Product -- so "an analyst classified this"
is a false statement on every Product row. The owner asked for analyst-named wording and
it was not taken literally for that reason; the actor is carried instead by the Owner
column and by the two `MISS_BUCKETS` rules that select on owner, which are the only two
labels on the page allowed to say "analyst" or "model" because the owner is part of the
rule that picks their rows.

**The vocabulary is now on every tab, not just the Executive Summary.**
`name_subtypes()` puts the label beside a tracker Sub-type on Root cause's drill-downs,
`subtype_matrix()` labels the heatmap's rows with it, and `owner_accounts()` and
`account_failures()` print it on the Root cause and Top customer complaints tabs. Ford read
"Source Coverage" on Top customer complaints and "Source not in our vendor or monitoring network" on
the Executive Summary -- two vocabularies for one failure on two tabs a reader moves
between.

**`PLAIN_SUBTYPE` still translates the taxonomy for the tables, and does not replace it.**
`Sub-type` is the vocabulary of the people who file the records, and on a leadership page
it says nothing -- `Review`, the largest People bucket, is the vaguest word in the file.
The tracker keeps its own wording because that is the record; only the label is
translated, and the tracker value travels beside it in the table so an analyst can tie
any row back to a field. `plain()` falls back to the value itself, so a term added
tomorrow appears as itself rather than vanishing. `Review` reads "Reviewed, and not
raised" rather than naming the analyst, because it sits under **both** People and Product
and a label naming the analyst is wrong on the Product rows.

**No RCA figure appears on this page**, for the reason set out under "No RCA figure is
published anywhere" above -- and it is gone from every other page too, so the dashboard
does not contradict itself.

**Three tabs were renamed** on the owner's call: `SOURCE 01 · Monthly trend` is
**Monthly trend**, `SOURCE 04 · Root cause` is **Root cause**, `SOURCE 05 · Top
customers` is **Top customer complaints**. The `SOURCE nn` prefixes were a map of the
Excel workbook's chart sources, which is a thing no reader of this dashboard has ever
needed. The names are the key in `PAGES`, `PAGE_KICKERS`, `DESCRIPTIONS`, `NAV_GROUPS`,
`smoke_app.EXPECTED` and `audit_pages.expectations()`, so a rename touches all six --
grep the old string across `app.py` and `scripts/` rather than editing `PAGES` alone.

**The sidebar is `--bg`, and the nav accent is per group.** The sidebar was `#171b22`
against a `#0f1115` page -- two greys four points apart, which reads as a mistake rather
than a separation; the 1px `--line` border is the split. `NAV_GROUPS` gives the twelve
pages four colours by the job they do, not twelve hues: repeating a hue across unrelated
pages claims a kinship that is not there, and twelve is confetti. The index is derived
from `PAGES`, so reordering or renaming a page cannot leave a rule pointing at the wrong
row, and each option reads its colour from a `--nav` custom property the generated CSS
sets -- the hover and selected rules no longer hardcode `--blue`. Verify
`div[role="radiogroup"]>label:nth-of-type(N)` against the live DOM after a Streamlit
upgrade, along with the two selectors named further down.

**`REASON_ALIASES` / `normalise_reason()` are gone, and they were already dead.** They
folded the `Reason` wordings onto one `Missed Event` label for the Nature-of-complaints
table -- and that table has been built from `REASON_CATEGORIES` / `reason_category()` for
some time, so the pair sat in the file as a second, unreachable implementation of the
same fold. This file documented them as live, which is how a dead code path survives a
reading: **the prose said it ran, and nobody checked whether anything called it.** A
repository-wide search found the definition and no call site. Deleted with the refactor.
`PICKLISTS` went the same way, for the same reason.

`missed_verdict()` answers the miss-rate question in a sentence above the trend chart,
because a grid of nine monthly percentages does not answer "are we getting better" and
nobody was reading one out of it: the last three months' pooled miss rate against the
three before, on **counts, not the mean of monthly percentages** -- a month with 4 emails
must not weigh the same as one with 18. A move under 5 points reads as "Not improving"
rather than being dressed up as a trend, and a thin latest month is flagged so nobody
leans on a point that will move, and `plural()` writes that flag -- the first email of a
new month made it read "has only 1 emails so far" on the Executive Summary, which is
exactly when a reader is most likely to see it. At 117 emails over ten months the answer
is 64% against 68%, a 4.4-point move the rule calls noise rather than dressing up as a
trend; the windows moved to Aug-Oct the moment October opened with one record, which is
the flag earning its place. It is not on the Executive Summary at all any more -- it
opened that page once, and now lives on Monthly trend, which is the page for it.

**The per-owner drill-downs are three tables stacked full width, not two squeezed into
`st.columns(2)`.** Side by side, a `count_table` with six numeric columns and a wrapped
meaning column had about forty characters of width each: every header wrapped to three
lines and the meaning column was unreadable, which is the opposite of what a drill-down
is for. `render_owner_drilldown()` gives each owner a computed sentence
(`owner_insight()`) and then three tables that answer three different questions --
**what failed** (the taxonomy, with the plain label beside the tracker value), **what the
customer called it** (their own wording, folded onto the categories), and **which
accounts carry it** (`owner_accounts()`).

That last one replaces a `long_pair_table(root_df, "Customer", "Reason")` dump: one row
per customer-and-wording pair, forty wordings against thirty-three accounts, long and
unranked and saying nothing the two tables above it had not. The question a drill-down
exists for is *whose problem is this*, and that needs the account's own base beside the
count -- 26 Product failures at Ford is a different fact from 2 at an account that only
ever sent 2 emails, which is why `Share of their emails` is a column. It carries **no
Total row**: an email naming two accounts is counted for both, so the column would add
to more than the tracker holds, and the rule here is that a total is a reconciliation or
it is absent.

"Which failures are growing" (the `subtype_drift` dumbbell) was removed on the owner's
call, with `subtype_drift()` and `dumbbell()`.

`Sub-type` sits beneath `Root Cause` in the taxonomy and was charted nowhere until
Root cause gained a heatmap of the two together, with a customer selector above it. The
selector narrows that block only -- the drill-downs below keep following the sidebar --
because the question the page exists to answer is "for Ford, how many were a source
miss", and answering it should not depend on knowing the sidebar has a filter at all. The shape is the point: `Review` is 18
People and 0 Process, `Source Coverage` is 20 Product and 0 anything else -- two
sub-types tied at 20 records that are entirely different failures with different owners.
Sixteen sub-types is far past the 7-8 ceiling where categorical colour stays readable,
which is why it is a single-hue heatmap and not sixteen coloured bars.

**Every chart draws from the app's own CSS tokens.** `RED_BLUE` is `--red`/`--blue`
and `BLUE_RAMP` grades `--panel` up to `--blue`; no chart introduces a hue of its own.
This was briefly not true -- the first cut of these three used darker, individually
better-validated steps, and the pages read as a different product. One palette across
the dashboard beats a locally optimal one, and a new view is never the place to
introduce a new colour.

Within that constraint the pair that carries meaning is still checked with
`scripts/validate_palette.js` (bundled `dataviz` skill) against the `#1b1f26` surface:
`--red` against `--blue` scores CVD dE 17.0 protan and 21.1 to normal vision, clear of
the dE 8 floor, and `BLUE_RAMP` is monotonic in luminance. What is deliberately never
used is the obvious red/green for rising and falling, which collapses to **dE 3.6 under
deuteranopia**; direction carries a signed label as well, so it never rests on colour
alone. In-bar labels wear `--panel` rather than `--ink`: white on `--red` is 2.2:1,
dark is 6.9:1, and the label sits on the fill rather than the surface.

Three forms beyond the bar charts, each chosen for its job rather than for variety:
a **heatmap** for the Root Cause x Sub-type grid, and **proportion bars** for ratios such as each
account's confirmed-miss share -- ratios on a shared 100% baseline, where a two-slice
pie is the classic wrong answer. Both layout faults found by screenshotting them are
worth remembering: a delta label anchored to the end dot printed across its own
connector on every falling row, and proportion bars sorted by raw count do not rank by
rate no matter what the caption claims.

`audit_pages.py` covers what `smoke_app.py` cannot: whether the numbers are *right*.
It scrapes every `excel-table` off every page and reconciles each label against counts
computed independently from the CSV. A page bound to a stale frame, a filter quietly
dropping rows, or a chart truncating a category all look identical to `smoke_app.py`;
this names the label and both numbers. It found the app showing Ford as 41, 37 and 32
on three pages at once.

**It also checks every Total row** (`total_row_problems`), because a foot that disagrees
with its own column is arithmetic nobody sees, and a foot that disagrees with the tracker
is worse -- a reader trusts the foot over the rows. Both have shipped here. Each rendered
Total is compared against the sum of the column above it, except for the columns in
`reconciled_totals()`: Customers impacted double-counts on purpose, so its foot is
checked against the CSV instead. The check paid for itself on the run that introduced it,
naming three bucket columns still adding to 27 / 24 / 13 where the chart above them said
26 / 23 / 12. Columns whose foot is a formatted string -- a share, a blank -- carry no
plain integer and are skipped. 16 feet across 6 pages today.

**The reconciled figures belong to a TABLE, not a page.** `reconciled_totals()` is keyed
by page, and `total_row_problems()` applied it to every Total row on that page -- which
was harmless while Customers impacted was the only table there with a foot. The first run
after Top customer complaints gained per-account tables failed with "Total row shows 44
for EMAILS, the tracker says 115": 44 is Ford's own total and perfectly correct. A table
is the double-counting one only if it carries a **miss-bucket column**, which is the
signature of Customers impacted and of nothing else, so that is the guard.

**A shared renderer needs a shared registration.** The first run after Top customer complaints started
calling the Executive Summary's own `render_customers()` failed here with the same
120-against-115 this check was written for: the table reconciles its own total, but
`reconciled_totals()` named only the Executive Summary. Both pages are registered now.
When a page starts rendering another page's block, check this map.

`miss_buckets()` in that script is the one recomputation of the miss buckets, used by
both the label check and the Total-row reconciliation, so the two cannot drift apart.

Every page counts **all records — complaints and inquiries together** — and every count
table carries explicit `Complaints`, `Inquiries`, **`Misses`** and **`Reported timely`**
columns beside the total, with the charts stacked to match.

**`Reported timely` is the remainder, named.** Every row of every count table read "25
emails, 24 misses" and left the reader to work out what the 25th was -- which is exactly
the question that got asked of `Source Coverage`, and there is no answer on the row.
Now **Records = Misses + Reported timely** on every row of every table, nothing
unaccounted for, and the caption says so in one line instead of a paragraph. It also
answers `Reported late` (12 emails, 11 misses): the twelfth was reported before the
customer wrote in. `Misses` is built in `count_table()` itself
rather than on each page, which is how one edit put it on every tab at once: a count
column alone does not say whether those emails were a failure, and `Process
Clarification` at 12 emails beside `Review` at 23 ranks the wrong way round until you
see that 1 of the first were misses and 20 of the second. It is a clean partition of
`Records`, so the Total row adds up and `audit_pages.py` reconciles it like any other
column. `excel_bar_table`'s default `extras` is `("Complaints", "Inquiries", "Misses")`
for the same reason. The Excel Dashboard still counts complaints only, so its Top
Customers figures differ from the app on two axes; Top customer complaints shows the workbook's basis
in its own table so the two reconcile.

The sidebar navigation is a list with a left accent bar, not twelve radio buttons.
It is still `st.radio` underneath -- that is what carries the selection -- but the dot is
hidden and the pill boxes are gone, because a column of bordered boxes stacked in a narrow
column read as compressed and the dot duplicates what the highlight already says. Two
selectors matter and neither uses Streamlit's hashed emotion classes, which are rewritten
between releases: `label[data-testid="stRadioOption"][data-selected="true"]` carries the
active state, and `div:has(+[data-testid="stMarkdownContainer"])` matches the radio circle
by its position before the label text. Check both against the live DOM after a Streamlit
upgrade; a silently failing selector here brings the dots back or loses the highlight.

**`Reason` holds forty distinct strings for about seven real things**, and every page
used to inherit that: "Missed Event", "Missed insolvency alert" and "WarRoom should have
been created but was not" are one category written three ways, so no chart of `Reason`
could rank anything. `REASON_CATEGORIES` / `reason_category()` / `with_reason_category()`
fold them onto **seven** reusable categories -- Event missed 63, Classified wrongly 14,
Question about coverage 14, Reported late 12, Supplier not included 7, Published but not
visible 4, Duplicate published 2 -- and that wording is what every tab shows, with
`CATEGORY_MEANING` giving each one a sentence that says what happened rather than
naming a field. The Executive Summary's table carries that sentence too, so the two
tabs explain a category the same way.

Two changes were made on the owner's instruction. `Supplier not linked` is now
**`Supplier not included`** -- the supplier was left off the WarRoom, which is a thing
somebody did, where "not linked" reads like a data-model state.

**`Supplier not included` (a `Reason` category) and `Supplier was not mapped by the
customer` (a `Sub-type` label) are different fields saying different things, and
confusing them is a mistake that has already been made here.** The category is what the
customer wrote about; the sub-type label is what the investigation found. An email can be
`Supplier not included` and turn out to be a customer mapping gap, or an analyst
omission -- the Root Cause is what separates them, which is why `Mapping` carries three
owner-aware labels above. And **`Hidden by the
customer's own filter` was folded into `Published but not visible`**, reversing the
call recorded below. The owner's framing is that the bucket means "we reported it
correctly and it never reached their portal", and on that definition it does not matter
whether the industry tag, a fault, or their own source preference is what hid it. **The
cost is real and is written into the meaning text**: the bucket now mixes our settings
with theirs, so it can no longer be read as a pure measure of our failure. **`Question about coverage` now holds 14 inquiries, no
complaints and no misses**, which is the shape it should have: it is the category for
asking how something works, so a record in it that turned out to be a failure belongs
somewhere else.

**The category and `Missed_Flag` measure different things, and the gap needs saying out
loud.** 78 emails are confirmed misses but only 63 sit under `Event missed`: the category
is what the customer complained about, the flag is whether the event reached them in
time. An event reported eleven days late *was* reported, so it is not `Event missed` --
but it did not reach them in time, so it is a miss. The other 15 are 11 reported late,
2 supplier not linked, 1 classified wrongly, 1 published but not visible, and a caption
under the table spells that out rather than leaving a reader to subtract.

**`validate.py`'s `issue_type` warns when a confirmed miss is logged as an inquiry.**
A record flagged `Missed_Flag = Yes` is one we failed on, so it cannot also be one where
nothing went wrong. Eight records disagreed at one point: the five coverage questions
logged as complaints where no fault was found, and three inquiries that were confirmed
misses -- Ford's unmapped Eason & Co supplier, EAO-15's WarRoom that qualified and was
never created, and EAO-41's bankruptcy keyword gap, fixed by adding keywords. All eight
were settled by reading what the row says was *done*. A warning rather than a failure,
because the daily Routine stages a row before anyone triages it and a staged inquiry that
later proves a miss is a normal waypoint.

**All customer emails sits second in `PAGES`, right under Executive Summary**, because it
defines the vocabulary every other tab uses: a reader who stops on a category name finds
its meaning one click away rather than at the bottom of a list of twelve.

**Numbers in prose are computed, never typed.** The "forty different wordings for eight
real things" line reads both figures off the frame on screen. A prose figure that has to
be remembered is a prose figure that goes stale, which is the fault this tab exists to
fix. `DISPLAY_NAMES` does the same job for `Missed_Flag`, the one column whose tracker
name still reads as a database field; the rest are already English and renaming them
would only make the grid disagree with the CSV downloaded from the same page.

**Complaint or inquiry is settled by what went back to the customer.** An explanation
means inquiry; a bulletin, a correction or an admitted fault means complaint. It is not
about how the customer phrased it -- that rule was tried first and produced the wrong
answer five times over. All five coverage questions logged as complaints were
`Clarification Provided` with no fault found (Roche: the WarRoom was already published
and delivery verified; Hitachi: polygon methodology explained; EAO-24: no public source
existed to report from; EAO-29: a deliberate internal convention, not a defect) and are
inquiries. The Eaton Axios npm record went the other way: it was closed as not relevant
on supplier mapping and the absence of operational disruption, and that judgement was
wrong -- Eaton has a **product** connection to the compromised package -- so it is a
complaint and a miss, and `Event missed` rather than `Classified wrongly`: the customer
never received it, which is what that category means. People / `Review` carries the
cause -- the event was seen and judged, not missed by coverage.

**Two more went the inquiry way on 15-Oct-2026, and the ground matters as much as the
answer.**

* **UVM Health Network** (Stryker, 16-Mar) is an **Inquiry**. The WarRoom was published,
  linked and visible; the customer's own profile preference excluded Resilinc as a
  source, and what went back was advice to change a setting -- no bulletin, no
  correction, no fault admitted. **It is settled on the discharge test and the NVR
  precedent, NOT on "no EventWatch fault existed".** That ground was already rejected
  for Roche, EAO-24 and EAO-29, three complaints where the finding was explicitly no
  fault on our side; record it as the reason here and those three have to move too. The
  row's own `Automation Opportunity` still proposes defaulting Resilinc into the WarRoom
  view, so an owed product improvement now sits in the inquiry bucket -- it needs a home
  that does not depend on the classification. **UVM has a second email of the same
  date** (Intuitive Surgical phishing breach, Product / `Source Coverage`), which is a
  miss and untouched. Match on the title, not the customer and date.
* **Trinseo** (Ford, 05-May, SIC not triggered) is an **Inquiry**. A bulletin was
  published on the missed interest payments and Ford received it; no Supplier Impact
  Confirmation fired, and Ford asked whether SIC can be enabled for financial-risk
  events. **Supplier impact requests are deliberately not sent for these events, because
  the responses have consistently come back No Impact.** That rule was communicated and
  the customer did not question it. The test is **which rule was broken**, and none was
  -- the same reasoning that keeps the META NVIDIA Shield TV Pro row an Inquiry and an
  `Improvement` rather than a `Bug`. The remedy is the SIC trigger logic review carried
  in `Automation Opportunity`, which is an enhancement, not a defect.

**"An admitted fault" means a defect against our own stated guidance -- not agreeing
that a better treatment exists.** The two rules above and below looked contradictory
(one says an admitted fault makes it a complaint, the other says the customer's framing
decides), and the owner's answer dissolves it: **where the guidance was silent, agreeing
to a better treatment is a process enhancement, not a fault.**

META / NVIDIA Shield TV Pro (09-Oct-2026) is the case. Rick Freeman asked why a WarRoom
was raised when META does not buy Shield TV, EventWatch agreed a bulletin fits that
scenario, and the first draft of the row wrote that up as an admitted fault -- which
would have made it a complaint. It is not. **The WarRoom met the threshold the guidance
actually set**: NVIDIA is a mapped partner, and the Price Fluctuation guidance calls for
a WarRoom when a mapped supplier is directly involved. What the scenario exposed is that
the threshold tested supplier mapping and never tested whether the affected product is
one the customer buys. Nobody broke a rule; the rule had a gap. So the row stays an
**Inquiry**, `Improvement` rather than `Bug`, `Process` / `Process Clarification`,
`Missed_Flag` No -- and the remedy is the new threshold, carried in
`Automation Opportunity`.

**The test, before writing "we agreed we were wrong" into an `RCA Details`: which rule
was broken?** If you cannot name one, it is an enhancement, and saying otherwise
manufactures a fault out of a team improving its own guidance.

`inquiry_table()` gives inquiries their own table, because a column that counts
complaints and inquiries side by side hides what was actually asked and what went back.
Every table that footers a calculation carries a **Total row** (`styled_table(...,
total_row=True)`), built inside the table function rather than by a generic helper --
two of the columns are formatted strings and `"62 (100%)"` cannot be summed after the
fact, only before.

**`Pending` means the investigation is open, not that the paperwork is.** Four records
sat on the under-investigation list with finished RCAs in their own `RCA Details`. That
example has since turned over -- EAO-48's RCA went to the customer on 05-Oct-2026 and the
ticket closed on the 7th, so it is `RCA Shared` now and the daily re-check is what moved
it. When an investigation closes,
move `Short Term Fix Status` off `Pending` -- `RCA Shared` where an RCA went out, `Fixed`
where a corrective action was taken -- and leave `Resolution Date` blank unless a real
date exists, since a guessed one is worse than none.

**"We reported it" beats "they said we missed it" -- but only about the CAUSE.** EAO-47
was logged as a source miss because Western Digital said no Nidec event existed. The
investigation found otherwise: the event had been captured and created, and the analyst
classified it `Not Impactful` without checking whether Nidec is a mapped partner of
theirs, so it never reached them. That settles the cause -- People / `Review`, not
coverage -- and the principle holds: **a customer asserting a miss is not evidence of
one**, the investigation is.

**It was then filed as an inquiry with `Missed_Flag` No, and that was wrong.** The
reasoning recorded here was "the failure is the impact classification, not coverage",
which answers *what* failed and not *whether anything reached the customer*. Nothing did.
An analyst making an impact determination about Western Digital presupposes the
relationship, so a notification was owed; and the ticket title is "No EventWatch Event
Created", which is an asserted absence rather than a question. Corrected 15-Oct-2026 to
**Complaint, People / `Review`, `Missed_Flag` Yes**. **The lesson is the one the delivery
test exists for: establishing the cause does not settle the flag.**

**`Hidden by the customer's own filter` was one email and existed on purpose -- until
the owner folded it in, above. The original reasoning, for whoever wants to unfold it:**
UVM Health
Network's WarRoom was published, linked and visible; their own profile preference
excluded Resilinc as a source. Inside `Published but not visible` -- a category named for
our failures -- one of four being a customer-side setting overstated it by a quarter.

**A complaint is one where the customer asserted we failed; an inquiry is one where they
asked how something works.** It is about how they framed it, not about what the
investigation found: Roche, EAO-24 and EAO-29 are all complaints where the finding was no
failure on our side. `Missed_Flag` carries the outcome and is the field every miss number
keys on, so reclassifying an email between complaint and inquiry never moves the miss
count.

**Read `RCA Details` before `Comments` on any row that looks like an admission.**
`Comments` opens with the customer's accusation -- "No proactive alert was generated for
the July 21 fire" -- while `RCA Details` carries the finding: "No public source existed
to report from." EAO-24 and EAO-29 were both summarised here as admitted failures on the
strength of their `Comments` alone, and both RCAs say the opposite. EAO-12 was the same
mistake. The first comment states the suspicion; the answer arrives later.

It is **derived, not stored**. `Reason` keeps the customer's own words because that
wording is the record of what they wrote, and a category is a reading of it; storing it
would mean a 27th column, a rewritten Data sheet, a wider `ComplaintTracker` ref and
three scripts changed, for something the app computes in a millisecond.
`validate.py`'s **`reason_categories`** imports the map from `app.py` -- one copy, so it
cannot drift -- and **fails** if a tracker `Reason` is missing from it, since the
alternative is a new wording falling silently into `Uncategorised`, which is exactly how
forty values accumulated.

`category_table()` renders the fold as one row per category with **`Their exact wordings`
listing every `Reason` folded into it, each with its own count** -- "Missed Event (44) ·
Missed insolvency alert (4) · ..." -- so a reader can check the fold instead of trusting
it. Only wordings present in the current filter are listed, so the column narrows with
the date range. `audit_pages.py` recomputes all eight counts from the CSV using `app.py`'s
own map, so the table and the data cannot disagree.

Three layout facts that cost a round each and are not obvious:
`styled_table` puts a column's classes on the **`th` as well as the `td`**, so a width
rule naming only `td` leaves `.excel-table.wide th.wrap`'s 280px minimum sizing the
column -- three columns all measured exactly 280px until the `th` was named too.
`.wrap` does three things at once (wrap, cap at five lines, scroll shadow) and a short
cell wants only the first: on a one- or two-line cell the shadow's cover layers are
shorter than the shadows they hide, so a band shows on a cell with nothing to scroll --
`wrapcol` wraps without the cap or the shadow, and the category name uses it.
A **wrapped column holding one label rather than a sentence wants `tight`**: the
`wide roomy` wrap floor is 340px, and two such columns at 340 pushed the owner-accounts
table 350px past its panel -- wider than the nowrap version the wrap was added to fix.
`tight` is 150-190px. Shortening a header ("All their emails" to "Their total") bought
the last 46px; fighting the CSS for it would not have.
And measure the table against its panel (`table.getBoundingClientRect().width` against
`.table-wrap` `clientWidth`) rather than eyeballing a screenshot crop: a fixed-width crop
cannot tell a table that overflows from one the crop simply cut.

**The filters name the things the pages name, and nothing else.** `Severity`,
`Short Term Fix Status` and `RCA Requested` filtered on fields no page shows any more --
a control that narrows a population by something invisible leaves a reader unable to
explain their own numbers. `Routed To` is derived from `Root Cause` on every row, so it
was one filter twice under two names. `Standard Automation Focus` is how the Dynamic
Source Discovery page selects itself, not a cut a reader makes. And the raw `Reason`
dropdown offered forty wordings for seven real things, so nobody could use it.

**A filter's options come from the WHOLE frame, never from the frame the filters above
it have already narrowed.** Reading them off the running `out` made the lists cascade,
and a cascading list throws away a selection the reader has already made: choose
`Event type = Factory Fire`, then choose a Customer with no fire, and Factory Fire is no
longer among the options, so Streamlit drops it from the widget without a word. The chip
vanishes, the narrowing stops applying, and the click reads as "nothing happened" -- which
is the whole of the "filters and tabs were not working with a click, I had to constantly
refresh the tab" symptom. It was not subtle: choosing one account took the Event type list
from **26 options to 1**, so 25 of 26 possible prior picks would have been discarded.

The cost of a stable list is real and is accepted: a reader can now choose a combination
that matches nothing. `filter_note()` already prints the surviving count at the top of
every page, so an empty page reads as a filter choice rather than a broken dashboard --
which is exactly the job that line was written for. **Do not re-cascade the options to
avoid empty results.**

The expander's `(N active)` label is counted off session state before the widgets render,
and that is only accurate because the options are stable. While they cascaded, a selection
could be dropped during the render while session state still held it, so the label read
"1 active" over a filter that was no longer filtering anything.

What replaced them: the two **derived** vocabularies the pages are written in --
`What they wrote about` (the reason category) and `What went wrong` (the plain
sub-type) -- plus **`Confirmed miss`**, the field every headline number on the dashboard
keys on and which had no filter at all. `FILTERS` is `(label, kind, column)` and
`filter_values()` returns the options and the series to match against together, so a
derived filter cannot offer a label it then fails to match.

**The column filters and the search box sit in a collapsed `st.sidebar.expander`**,
labelled with how many are active so a narrowed view cannot hide behind a shut control.
They were always open, which made the sidebar taller than any screen -- the page list
scrolled out of sight below them and reaching a tab meant scrolling past ten dropdowns
nobody was using. The **date range stays outside it**, because it is the one control
touched on every visit, and Streamlit's own sidebar collapse (the arrow at its top) is
what widens the page for reading a table.

**A complaint is not automatically a miss**, and that gap is the first thing a reader
asks about: 18 of the 97 complaints are ones where the event *was* reported and the
failure, if any, was something else -- wrong classification, published twice, not
visible, the supplier left off the WarRoom, late. The KPI
row states it (`Complaints, not a miss  18 of 97`) and a table below breaks it down,
rather than leaving a reader to subtract. All 78 confirmed misses are now complaints and
no inquiry is one, which `validate.py`'s `issue_type` keeps true.

`% of these` rather than `% of emails`: the column is a share of whatever frame the table
was built from -- all 115 in one place, the 17 non-miss complaints in the other -- and
"% of emails" reads as a share of the whole tracker in both.

**Vocabulary: a row is a "customer email", not a "record".** `filter_note()` and the
count tables say so, and every KPI card prints the base inside the number (`78 of 116`,
not a bare `68%`), because a bare percentage beside a bare count is what made two
different denominators on one screen unreadable. `Inquiry` is the value in `Issue Type`,
so the app says "inquiries" -- not "questions", which invents a second word for one value.

**`add_section()` writes raw HTML, so backticks in its text render as literal backticks.**
Write the prose without them.

**And write tracker prose without question marks.** `validate.py`'s `mojibake` rule
**fails** on `[A-Za-z0-9]\?[ ,"]` -- a `?` at the end of a word, which is what a decayed
accent leaves behind (`caf?` plus a space). A real question mark ending a sentence is the
same shape, so the NVR row's two quoted customer asks failed the gate
(`'reated for the Kinston facility? NVR receiv'`). The rule's own docstring claims "a
genuine question mark attaches to the word before it, so neither shape is ordinary
punctuation", and **that claim is false** -- it held only because no prose in the tracker
had carried a question until then.

**The prose was rewritten, not the rule.** `caf? ` and `facility? ` cannot be told apart
by regex, so narrowing the pattern would weaken a failure-level corruption detector to
admit one row, which is the same move as skipping a test to get green. Phrase a customer's
question as a statement -- "ASK 1, why no WarRoom was created for the Kinston facility" --
and nothing is lost. If quoted questions ever need to survive verbatim, that is a
deliberate change to the rule with a `selftest.py` case proving the real shapes still
fire, not a quiet loosening.

The All customer emails table serves two readers without a second page. Someone reading
the tracker wants a grid they can scan; someone exporting a slice wants every field.
A `Show all fields` checkbox switches between the eighteen reading columns
(`TRACKER_COLUMNS`) and everything except `Month_Sort`, which is an internal sort key no
reader needs. `styled_table(variant="wide grid")` lets the table size to its content and scroll sideways
rather than be squeezed to `width:100%`, which is what turned every multi-word cell into
two and three lines, and `wrap=WRAP_COLUMNS` lets the free-text columns wrap inside a
bounded 320-600px width while every other column stays on one line.

`grid` is the restyle on top of `wide`, and it is **this page only** -- every other tab
keeps the bordered Excel look. A full box grid, centred text and zebra fills read
as a spreadsheet export rather than a table meant to be read, and they read worst exactly
here: rows are of very unequal height (a seven-line `Comments` cell beside a one-line
neighbour), so the vertical rules draw ragged columns and the alternating fills emphasise
the raggedness. Hairline row separators and a hover band carry the row instead, cells
align **top** so a short value sits beside the first line of a long one rather than
floating in the middle of it, and **the first column is sticky** so the month stays on
screen through twenty-six columns of sideways scroll. `styles=GRID_STYLES` gives dates
tabular figures so they line up down the column and the Jira key a monospace face.
A `td:empty:after` em-dash placeholder was tried and removed: it renders as tofu wherever
the monospace fallback lacks U+2014, which was the column it was meant to mark, and a
blank cell in a borderless grid already reads as absence.

**A wrapped cell is capped at five lines and scrolls in place.** Nothing is cut -- the
whole value is still there -- but one 350-character `Comments` no longer sets the height
of a row whose every other cell is one line: the tallest row went 160px to 123px against
a 62px median, and only 26 of 345 wrapped cells overflow at all, so the intervention is
surgical. The scroll is left to **chain** (no `overscroll-behavior:contain`), so reaching
the bottom of a cell carries on scrolling the page instead of trapping the wheel.

Two things about the affordance, both found by measuring rather than assuming. Setting
`scrollbar-width` makes Chromium use the standard scrollbar and **ignore every
`::-webkit-scrollbar` rule**, so the styled bar never painted; and even without it this
Chromium paints overlay scrollbars that take no layout width (`offsetWidth - clientWidth`
is 0) and do not render in a screenshot. A scrollbar is therefore not a cue that can be
relied on here. The cue is the **scroll-shadow** technique instead: two cover layers in
the cell's own background colour attached `local` so they scroll away with the text, and
two shadow layers attached `scroll` so they stay pinned to the edges -- the shadow shows
only while there is more text past that edge, and it always paints because it is a
background, not a widget. The cover colour is `--cell-bg`, redefined on the hover row so
the covers do not mismatch the surface under them. Those columns were
briefly truncated with an ellipsis instead, on the reasoning that the full text sat one
click away in the record card. It does, but **68 of 114 `Comments` run past 110
characters**, so nearly every row showed a sentence that stopped mid-thought and the
column a reader most wants to read was the one least readable. Wrapping costs row height;
that is the honest price of showing the whole value. A record picker below the grid still
opens any one record as a `variant="record"` card. Filtering
stays in the sidebar on purpose, so what this page shows is always the same population as
every other tab.

The entry form at the foot of **All customer emails** (`dashboard/staging.py`) writes
into `st.session_state`, and
`apply_staged()` appends those rows to the frame **before** `sidebar_filters()`. Every
page derives from that one frame, so an entry added there is counted immediately on all
seven -- Executive Summary's total goes 103 to 104, Top customer complaints's Ford tally 37 to 38.
The form's pickers are built from the tracker's own distinct values, so a staged row can
only carry terms the Definitions sheet already defines, and `derive_row()` fills Month,
Reporting Month, Month_Sort, Number of Customers and Routed To -- a staged row pasted
into the tracker passes `validate.py` unedited. Staging is **per browser session and not
persisted**: Streamlit Cloud's filesystem is ephemeral and `app.py` makes no network
calls, so the entry lives until the tab is closed. The "Download tracker CSV including
staged entries" button is the path to making it permanent. Durable in-app writes would
need a GitHub token or a database, and neither exists here.

`smoke_app.py` covers what `validate.py` cannot: the app itself. It starts Streamlit
against the local CSV, clicks every page, and fails on Streamlit exceptions, in-app
error text, or a page rendering fewer charts/tables than it should.

**It settles, then polls -- and both halves are load-bearing.** It used to sleep a fixed
1800ms after each click and count whatever existed. At 119 rows that window stopped being
enough for the heaviest page: Root cause reported 11 tables of 12 on every run,
reproducibly, while a 9-second wait showed all twelve present. A gate that fails because
the data grew is a gate that gets ignored, so the count is now polled to a 12s deadline
and returns the moment the page owes nothing -- the whole run still takes about 16s.
**Removing the settle wait in favour of polling alone was worse and shipped for one run:**
Streamlit swaps the page body a beat after the click, so an immediate poll reads the
*previous* page's DOM and exits satisfied. Every page then passed against its
predecessor's counts -- Monthly trend printed the Executive Summary's 10 charts and 7
tables -- which is a green gate measuring the wrong page. Settle first, then poll. Run against the
commit before the `chart()` argument fix it flags 8 pages with "required fields are
missing" and zero charts — the bug that previously only a screenshot caught. Prefer
it over screenshots; it costs a fraction of the tokens.

**Charts pass `width="stretch"`, never `use_container_width`.** Streamlit removed that
argument after 2025-12-31, and Streamlit Cloud resolves whatever `requirements.txt`
allows, so a loose pin gets the newest release and every one of the twelve
`st.plotly_chart` calls raises on it -- the deployed app stops loading while the local
one, on an older wheel, is fine. `requirements.txt` therefore pins `streamlit>=1.63`,
which is the floor that has `width`. `smoke_app.py` catches this, but only if it runs
against the same Streamlit version Cloud resolves; a local run on a pinned-back
environment will not see it.

## Python's job vs. the model's job

Deterministic work belongs in a script; it is cheaper, repeatable, and reviewable.

| Do in Python | Needs a model |
| --- | --- |
| Fetch and condense Jira; diff keys against the tracker | Deciding which customer a prose ticket body is about — Micron, Honeywell, GM and Liberty Blume were each named only in body text, never in a field |
| Every integrity check in `validate.py` | Matching a ticket to a row when the strings differ ("Dana Holding Corporation" vs "Dana Incorporated"; "Event title change request" → the Isselguss naming clarification) |
| Structural workbook audits (table refs, chart ranges, `cm=` markers) | Judging whether two rows are one complaint from two customers or two independent misses |
| Mechanical, idempotent edits (append rows, extend a chart range) | Classifying a new row's Root Cause / Reason / Severity / Automation Focus |

On that last row: the workbook computes those fields by formula, but ~20 of the
original 80 rows disagree with a literal recomputation of their own formula. The
humans override it. Treat the formula as a draft, not the rule, and match the
thematic precedent of comparable rows instead.

## Token traps specific to this repo

- **Jira through a conversational tool costs ~2600 chars/ticket where ~110 are
  useful** — self links, four avatar URLs per user, statusCategory objects. One
  `getVisibleJiraProjects` call returned 316KB and blew the context window. Prefer
  `scripts/jira_sync.py`. If you must use the MCP tools, pass `fields`, use one paged
  JQL search rather than per-issue calls, and never list all projects.
- **Read the module, not the application.** `app.py` is 61 lines and holds no logic;
  the code is under `dashboard/`, largest first: `metrics.py` ~1000, `sections.py` and
  `components.py` ~550 each, `taxonomy.py` ~470. Grep for the symbol, then read that
  one file. This line used to claim `app.py` was ~480 lines when it was 3,389 -- a
  seven-fold understatement in the one note written to stop a reader loading it whole.
- **Screenshots cost real tokens.** Run `scripts/smoke_app.py` first — it catches
  exceptions and empty charts from the DOM for ~1K tokens, where screenshotting all
  14 pages costs ~25K. Reserve screenshots for judging *appearance* (layout, colour,
  spacing) on pages you actually changed.

## Editing the workbook: do not use openpyxl load/save

`openpyxl.load_workbook(...)` then `.save()` on this file **silently destroys** the
Dashboard's dynamic arrays: it drops `xl/metadata.xml` and the `cm=` attributes that
make the `LET`/`UNIQUE`/`FILTER`/`SORTBY`/`TAKE` formulas in `Dashboard!A64`, `B64`,
`C64` and `I64` spill, and it strips chart style sidecars. It also converts shared
strings to inline strings, so you cannot swap one sheet's XML back in isolation.

Edit the zip members directly instead — unzip, patch `xl/worksheets/sheetN.xml` or
`xl/charts/chartN.xml` as text, rezip — then run `scripts/validate.py`. Sheet order:
`sheet1` Data, `sheet2` Dashboard, `sheet3` Definitions, `sheet4` Management Readout.

If a resave already happened, restore the four `cm="1"` attributes and
`xl/metadata.xml` from git history and re-register the part in `[Content_Types].xml`.

## Dashboard structure worth knowing

- Source tables sit under row 46. **The four bands share rows**: row 53 carries April's
  month serial in column A, the Root Cause Total in E, a Fix Status value in I and a
  Severity value in M. Inserting a row to grow one block therefore rewrites cells
  belonging to the others — an attempt at automating that replaced May's month serial
  with a duplicate of April's. Grow a block by writing its own two columns, never by
  cloning a row.
- The monthly trend block is pre-extended to all twelve months of 2026 (rows 50-61,
  Total at 62), so October, November and December land in rows that already exist and
  `chart1` already covers. Nothing needs doing when the month rolls over.
- Fixed enumerations (Root Cause, Fix Status, Severity, Automation Focus) are still
  hand-listed and still go stale when a new value appears; `validate.py`'s
  `enum_coverage` reports it and the row is added by hand. A new value costs **two**
  hand-edits, not one: the Dashboard's enum block (`enum_coverage`) and a row on the
  Definitions sheet (`enum_definitions`). Definitions rows append at the bottom, out
  of section order -- rows 138-150 already do -- so nothing shifts; extend
  `DefinitionsTable`'s `ref` and the sheet `dimension` to the new last row.
- Top Customers (`A64`) and Event Type workload (`I64`) are dynamic arrays; they
  resize themselves and need no maintenance.
- Charts bind to those source tables by fixed range (`chart1` monthly trend,
  `chart2` fix status, …), so extending a table means extending the chart's `<f>`
  range and its cached points too. Charts are not row-anchored in `drawing1.xml`, so
  shifting source rows does not move them on screen.
- Shifting rows also means rewriting A1-style references **inside** formulas
  (`ANCHORARRAY(A64)`, `SUM(F64:F72)`) and the `ref=` on each `<f t="array">`, plus
  `mergeCell`, `conditionalFormatting sqref` and the frozen `pane`. Renumbering only
  the `<c r="...">` attributes leaves the sheet loading but computing nonsense.

## Conventions

- Multi-customer rows use a slash: `Ford/GM`, `Penske/Ford`, `Eaton/Ford`, with `Number of
  Customers` set. One incident reported by two customers is **one row**, not two.
  A merged incident may also carry slash-separated Jira keys (`EAO-35/EAO-36`).
- **The app counts customers one way throughout: split on the slash.**
  `customer_exposure()` does it for the Executive Summary and Top customer complaints, and
  `customer_names()` / `names_match()` do it for the sidebar filter and the Root cause
  selector. It was not always so: the sidebar matched the whole cell, so filtering to
  Ford returned 37 records where the Executive Summary counted 42 -- the five
  `Ford/GM`, `Eaton/Ford` and `Penske/Ford` rows silently vanished, all of them
  complaints, which is why the complaint count moved but the inquiry count did not. The
  dropdown also listed those three combined strings as if they were companies, and left
  Penske unselectable because its only record is the `Penske/Ford` row. Selecting two
  accounts that share a row returns it once, not twice.
- **The workbook still counts customers the other way, and that is the remaining
  divergence.** Excel's `COUNTIFS` matches the whole string, so `Eaton/Ford` is its own
  category there and Ford reads 37. Top customer complaints shows the exact-match table too, labelled,
  so the two reconcile. Making Excel agree means rewriting `Dashboard!A64`, `B64` and the
  `B74` "Other customers" formula to be token-aware -- not done.
- `Jira Key` links to the `EAO` project (EventWatch_AI_Ops); older strays live in
  DATA/TS/BI/TENAR. **A record with no key is not necessarily pre-EAO**: the Eberhard AG
  / Infineon miss of 14-Aug-2026 has none because it was raised at a weekly sync and
  answered by Product Management with no ticket ever opened. `jira_sync.py` will never
  see it, so the daily Routine cannot find it; a row like that is added by hand with
  `append_row.py`, since it appends out of date order.
- **A key can arrive weeks after the row, and the answer is `update_row.py`, never a
  second row.** The ADM / General Mills miss of 16-Sep-2026 was the other no-key example
  here until **EAO-51** was opened for it on 08-Oct, three weeks after the CSM raised it
  by email. One incident is one row: the key went onto the existing row and the sentence
  claiming no ticket existed was corrected on it. The daily Routine diffs keys against
  the tracker, so a ticket opened late for an incident already recorded **looks exactly
  like a new one** -- before appending anything, check whether the tracker already holds
  that incident under a blank key.
- **Re-sort a back-dated append with `sort_tracker.py --all`, never with the month's own
  name.** `sort_tracker.py` sorts the chosen records **among the positions they already
  occupy**, which is what makes naming two months safe -- and is exactly what breaks
  here: the appended row's position is the end of the file, so `sort_tracker.py Aug`
  sorted the eighteen August records across positions 83-99 **and 119**, and put
  31-Aug at 119, after every September and October row. `validate.py`'s `row_order`
  caught it (`row 119: 2026-10-01 followed by 2026-08-31`) and `--all` fixed it in one
  run. Naming the month is right only when that month is the last one in the file,
  which is why the General Mills row never showed this.
- **NEVER invent an `Event type`. The twenty-four in the tracker are the portal's own
  selection list**, and customers and the ELT already read those names. `Event type` is
  not a taxonomy derived here, unlike `Sub-type` and the plain labels: it mirrors a
  fixed dropdown, so a value added to the tracker is a word nobody outside this file
  recognises and a category no portal selection can ever produce again.
  **`Power Outage` covers every grid and utility cut -- power, water, internet** -- and
  that is why its definition reads "grid and utility failures" rather than naming
  electricity.

  This is written as a rule because it was broken. A municipal water disruption at
  General Mills' Carlisle mill (EAO-52) was filed under a newly invented
  `Utility Disruption`, and `Power Outage` was then *narrowed to electricity* to make
  room for it -- which inverted the one row that already said where water cuts go. The
  owner's correction: water and internet cuts are notified under `Power Outage`, there is
  no `Utility Disruption`, and the portal offers no such option. The row was moved back,
  the invented Definitions row removed, and `Power Outage` restored and widened to name
  water and internet outright so the next reader cannot repeat it.

  The reasoning that produced it is the trap: no existing value looked like an exact fit,
  so a new one felt tidier than a slightly loose one. **A slightly loose fit inside a
  vocabulary everyone shares beats an exact fit nobody else uses.** When no `Event type`
  seems right, ask -- do not add one.

  **`Price Fluctuation` is the case where asking got a yes**, and it is the shape the
  rule is actually for. A META inquiry of 09-Oct-2026 (Rick Freeman, Expert Services)
  carried an NVIDIA Shield TV Pro price increase that the *portal itself* had classified
  `Price Fluctuation` -- so the evidence was not "no existing value fits", it was the
  bulletin's own category. It was put to the owner, confirmed as a real portal selection,
  and added as the twenty-fifth value. The distinction from `Utility Disruption` is the
  whole rule: there the portal offered no such option, here it does. **The test is
  whether the portal has it, never whether the tracker has it** -- the tracker only ever
  shows the values that have happened to come up.
- Removing a Definitions row is `add_definition.py` in reverse and has no script: drop
  the `<row>` from sheet3, then shrink **both** `DefinitionsTable`'s `ref` and the sheet
  `dimension`, or the workbook opens with the table claiming a row that is not there.
  A row appended at the bottom is the easy case, since nothing below it needs
  renumbering. Patch the Power Outage text **before** deleting, not after: its note
  named the invented type, so a "nothing mentions it any more" assertion fires on the
  surviving row and refuses the write -- which is the assertion doing its job.
  `export_definitions.py` after, then `validate.py`.
- `Short Term Fix Status` is `Fixed` / `RCA Shared` / `Clarification Provided`, plus
  `Pending` for tickets still open in Jira. Adding a new value means adding it to the
  Dashboard's Fix Status table too.

  **`Pending` is about whether an answer has gone back, not about whether a ticket
  exists.** This was written here one commit earlier as "`Pending` requires a Jira key",
  generalised from a single row, and **the next record disproved it**: Suntory Spirits of
  09-Oct-2026 is email-only, has no ticket, is genuinely under investigation and is
  `Pending` on the owner's instruction. The corrected rule:

  * **Do not leave a row `Pending` once the customer-facing answer has gone back.** The
    NVR row of 09-Oct-2026 was `Pending` while a clarification had already been sent on
    its first ask and only an internal source check remained. It is
    `Clarification Provided`, and the loose end is named in `Comments`, where a human
    reads it.
  * **A `Pending` row with no key still needs a human to carry it.** The daily re-check
    finds its work by scanning `Pending` rows and pulling each one's ticket, so a blank
    key means nothing automatic will ever move it. Say so in the row's own `Comments`
    rather than relying on somebody noticing.
- The app has **no live Jira or Outlook lookup**. Both pages were removed: the tracker's
  earlier months predate the EAO project, so a per-row lookup was empty for most records
  and the credential-gated "not configured" placeholder was all most viewers ever saw.
  Jira reconciliation lives in `scripts/jira_sync.py` and in the Atlassian MCP connector,
  which works for a model in-session and does nothing for the deployed app. Do not
  reintroduce `requests` or a network call into `app.py`.
- `Routed To` says which team a record is directed to, derived from `Root Cause`:
  People/Process go to `EventWatch Ops - Nitin Rindhe`, Product goes to
  `Product & Platform`. EventWatch Ops still owns the customer-facing RCA on
  Product-routed records — routing is who investigates, not who replies. It is a
  derived default; a human override is expected and nothing recomputes it.
- `RCA Details` holds the root cause summary from the linked ticket. Most RCAs went out
  as PDF attachments whose text is not in Jira, so those entries say so rather than
  paraphrasing a document nobody can read back. Do not invent RCA narrative.
- `definitions.json` is generated from the workbook's
  Definitions sheet by `scripts/export_definitions.py` and **pruned to terms in use**
  (a field definition survives if the tracker has that column, a taxonomy value if some
  record carries it, an operational term if it appears in the tracker's own text). Edit
  the sheet, re-run the script; never edit the JSON. `validate.py`'s
  `definitions_export` rebuilds it in memory and fails if what is committed is stale.
  It is a committed file rather than a runtime read of the workbook because the
  CSV-only deploy path has no workbook, and a JSON that ships with the app cannot fail
  to load. It replaced a hardcoded dict that had drifted badly -- no Event type or
  Sub-type section at all, and a `Confidence` term the tracker never had.
