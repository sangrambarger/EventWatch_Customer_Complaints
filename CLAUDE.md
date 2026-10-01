# EventWatch Customer Complaints

Streamlit dashboard over a complaint tracker that exists in two synced forms:
`customer_tracker.csv` (preferred source) and `EventWatch_Customer_Complaints_2026.xlsx`
(Data sheet + a live Dashboard).

`app.py` hardcodes no owner, repo or branch. `data_sources()` resolves, in order:
`GITHUB_CSV_URL`/`GITHUB_WORKBOOK_URL` (secret or env), then the data files sitting
next to `app.py` (the zero-config path a Streamlit Cloud deploy takes), then a raw URL
built from `GITHUB_REPO` + `GITHUB_BRANCH`. `scripts/smoke_app.py` deliberately writes
no secrets so it exercises that middle path.

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
after it. An `Event type` needs nothing on the Dashboard -- the Event Type block is a
dynamic array -- but `Root Cause`, `Fix Status`, `Severity` and `Automation Focus` still
need their hand-listed Dashboard row as well.

## The Jira scheduler

A Routine (scheduled Claude session) runs daily with the Atlassian connector attached.
It searches the EAO project, diffs the keys against the tracker, classifies each new
ticket, appends it with `append_row.py` (and carries established causes back onto
earlier rows with `update_row.py`), refreshes the caches, runs the full gate and
pushes. **No API credentials exist anywhere in this repo or in Streamlit** -- the
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
| Executive Summary | the whole story, in eight sections |
| All customer emails | the records, and the vocabulary every other tab uses |
| Monthly trend | volume by month, then the summary's own trend block |
| Root cause | the summary's two root-cause blocks, then the heatmap and the per-owner drill-downs |
| Top customer complaints | the summary's Customers impacted block, then one account at a time from a dropdown |
| DETAIL Event workload | the summary's Event types block |
| Dynamic Source Discovery | the source and keyword deep dive |

**The six Executive Summary sections are functions now** -- `render_root_cause`,
`render_customers`, `render_event_types`, `render_nature`, `render_trend`,
`render_deeper_root_cause` -- and the internal pages call the same ones. That is the
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
`Event Identification` / `Prioritization`, split on `Root Cause` People against Product).
The first two take their wording from `PLAIN_SUBTYPE` rather than repeating it, so a
label cannot be renamed in one place and not the other. The last two are the only labels
on the page that may name an actor, because the owner is part of the rule that selects
their rows rather than a property of the sub-type.

Every other missed email takes a bucket **named after its own sub-type**, generated in
`miss_bucket_series()` from `PLAIN_SUBTYPE`. Eleven buckets on the current data: an
analyst let it through 27, source not in our network 24, keyword miss 12, the model did
not spot it 6, then supplier not mapped 2, published but not visible 2, reporting
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

**Every table on the page carries a Total row** (`excel_bar_table(..., total_row=True)`,
which is the default). It is summed inside the table function rather than by a generic
helper, because the share column is a formatted string: "29.5%" cannot be added up after
the fact, and the total of a column of shares is 100% of whatever base the table was
built from, not the sum of the strings in it.

1. **Eight cards**, two rows of four via `kpis(..., columns=4)`. Never eight across: at
   the width this is read at that is 180px a card, and the number is the first thing to
   shrink. Row one is what came in (emails, complaints, confirmed misses, complaints
   that were not a miss); row two is what it means (`Never captured by us`, `Seen, but
   overlooked`, the last three months' rate, and the largest account's share of the
   whole page). **`Never captured by us`, not "never notified to customers"** -- the
   second is true of all 78 misses, so it stops contrasting with the card beside it.
2. **What customers sent us** -- two donuts, side by side. `overview_split()` is all 115
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
3. **Why the events were missed** -- two tiers, and the page's headline above both:
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
4. **Customers impacted** -- `miss_by_customer()`, the eight worst as a stacked bar and
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
5. **Event types** -- two charts and one table. `all_event_types()` is every email by
   the kind of event it was about; `missed_event_types()` is the confirmed misses only.
   Neither is readable alone: nine misses is a different fact depending on whether ten
   emails named that event type or forty, and the block used to show only the misses.
   `event_type_pairs()` puts both bases on one row underneath with a miss rate that
   **prints its own denominator inside it** ("81% of 16"), because a bare percentage
   over one email is not a finding.
6. **Nature of complaints** -- the eight `REASON_CATEGORIES`, the same vocabulary the
   All customer emails tab defines and lists the wordings behind. **The bar is stacked
   on the miss split**, darker for the emails in that category that were a confirmed
   miss and grey for the ones where the event did reach the customer, and a computed
   caption states the arithmetic: `Event missed` carries 63 misses against 78 on the
   cards, and the other 15 sit in categories where the event *was* reported and
   something else went wrong. That gap reads as an error every time somebody meets it,
   and it is not one -- the category is what the customer wrote about, the flag is
   whether the event reached them in time. Showing the split on the bar, and printing
   `63 + 15 = 78` under the table, is what stops it being asked a third time.
7. **Is it getting better?** -- `trend_chart()` is **one bar per month**, its percentage
   printed on it, the last three months blue and the three before grey, months outside
   both windows dark so they cannot be mistaken for part of the comparison. It was a line
   with two flat shelves drawn over it and a signed delta on the plot, and a reader had
   to be told what the shelves meant before the chart said anything. The comparison is
   stated in words by `missed_verdict()` above the chart instead of drawn into it, and
   `trend_table()` puts the months underneath with a total whose rate is **pooled, not
   averaged**.
8. **The deeper root cause** -- `root_frame()` and `grouped_bar()`: every failure in the
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

**`DRIVERS` is keyed on `(Root Cause, Sub-type)` -- never on the display wording.**
It gives each pair EventWatch's own name for the failure and the same thing in plain
English: the term is what the chart prints, the plain English rides on the hover and
fills a column of the table, so the page reads to a VP without costing an analyst the
word they file records under. `Source Coverage` is `Source Miss`, `Keyword Update` is
`Keyword Miss`, Product-rooted `Review` / `Event Identification` / `Prioritization` /
`Relevancy` are all `Model Miss`, People-rooted `Review` is `People / Analyst Miss`, and
Process-rooted `Visibility` and `WarRoom Creation` are both `WarRoom Issue` -- the
tooltip for which says "missing, delayed, duplicated, or not visible", which is why both
belong to it.

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

## The vocabulary, and the two rules that hold it together

`PLAIN_SUBTYPE` was rewritten wholesale on the owner's wording. `Source Coverage` is
**Source not in our vendor or monitoring network**, `Keyword Update` is **Keyword Miss**,
`Review` is **We saw it and chose not to report it** -- the second pass at that label,
because "Seen at review, and not raised" never said what review *is*, and the sub-type
sits under both People (an analyst) and Product (the model). Describing the **decision**
is the one thing true of both. `Event Identification` is **Classified as
not impactful, wrongly**, `Mapping` is **Supplier was not mapped by the customer**,
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

**No label names an actor where the tracker puts that sub-type under more than one
owner.** `Event Identification` is 5 People and 4 Product, `Review` is 21 People and 2
Product, and `Relevancy`'s single record is Product -- so "an analyst classified this"
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

`REASON_ALIASES` / `normalise_reason()` fold the `Reason` wordings that all mean "an
event we should have reported was not reported" onto one `Missed Event` label for the
Nature-of-complaints table: forty distinct strings for a handful of complaint kinds put
a 4-record insolvency variant beside a 43-record general one as if they were different
failures. Hybrids (`Missed / Delayed Event`, `Delayed / Missing WarRoom`) are left alone
-- they carry a timing signal too. It is a **display** normalisation; the tracker keeps
the customer's own wording, because that wording is the record of what they said. It is deterministic, so it is regression-testable and needs no API key, which
is why the no-network rule in `app.py` still holds.

`missed_verdict()` answers the miss-rate question in a sentence above the trend chart,
because a grid of nine monthly percentages does not answer "are we getting better" and
nobody was reading one out of it: the last three months' pooled miss rate against the
three before, on **counts, not the mean of monthly percentages** -- a month with 4 emails
must not weigh the same as one with 18. A move under 5 points reads as "Not improving"
rather than being dressed up as a trend, and a thin latest month is flagged so nobody
leans on a point that will move. At 116 emails over nine months the current answer is
63% against 72%, down 9.0 points -- which clears the threshold, and the caption under the
chart still names both denominators (46 and 43 emails) so nobody reads nine points off
eighty-nine emails as a result. It no longer opens the page: the eight cards do, and the
comparison sits seventh, where it reads as the end of the story rather than the start.

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
somebody did, where "not linked" reads like a data-model state. And **`Hidden by the
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

`inquiry_table()` gives inquiries their own table, because a column that counts
complaints and inquiries side by side hides what was actually asked and what went back.
Every table that footers a calculation carries a **Total row** (`styled_table(...,
total_row=True)`), built inside the table function rather than by a generic helper --
two of the columns are formatted strings and `"62 (100%)"` cannot be summed after the
fact, only before.

**`Pending` means the investigation is open, not that the paperwork is.** Four records
sat on the under-investigation list with finished RCAs in their own `RCA Details`; only
EAO-48 has no RCA, and it is the one genuinely still open. When an investigation closes,
move `Short Term Fix Status` off `Pending` -- `RCA Shared` where an RCA went out, `Fixed`
where a corrective action was taken -- and leave `Resolution Date` blank unless a real
date exists, since a guessed one is worse than none.

**"We reported it" beats "they said we missed it".** EAO-47 was logged as a source miss
because Western Digital said no Nidec event existed. The event had in fact been captured
and created; the analyst did not check whether Nidec is a mapped partner of theirs and
classified it `Not Impactful`, so it never reached them, and the customer was told the
event *was* reported. It is now an inquiry, `Missed_Flag` No, `Wrong Relevancy`, People /
`Review` -- the failure is the impact classification, not coverage. **A customer asserting
a miss is not evidence of one**; the investigation is.

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
asks about: 18 of the 96 complaints are ones where the event *was* reported and the
failure, if any, was something else -- wrong classification, published twice, not
visible, the supplier left off the WarRoom, late. The KPI
row states it (`Complaints, not a miss  18 of 96`) and a table below breaks it down,
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

The Complaint Tracker page's entry form writes into `st.session_state`, and
`apply_staged()` appends those rows to the frame **before** `sidebar_filters()`. Every
page derives from that one frame, so an entry added there is counted immediately on all
eleven -- Executive Summary's total goes 103 to 104, Top customer complaints's Ford tally 37 to 38.
The form's pickers are built from the tracker's own distinct values, so a staged row can
only carry terms the Definitions sheet already defines, and `derive_row()` fills Month,
Reporting Month, Month_Sort, Number of Customers and Routed To -- a staged row pasted
into the tracker passes `validate.py` unedited. Staging is **per browser session and not
persisted**: Streamlit Cloud's filesystem is ephemeral and `app.py` makes no network
calls, so the entry lives until the tab is closed. The "Download tracker CSV including
staged entries" button is the path to making it permanent. Durable in-app writes would
need a GitHub token or a database, and neither exists here.

`smoke_app.py` covers what `validate.py` cannot: the app itself. It starts Streamlit
against the local CSV, clicks every page (12 of them), and fails on Streamlit exceptions, in-app
error text, or a page rendering fewer charts/tables than it should. Run against the
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
- **`app.py` is ~480 lines** — grep for the symbol, then read with `offset`/`limit`.
  Reading it whole costs ~13K tokens and is rarely needed.
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
  DATA/TS/BI/TENAR. **A record with no key is not necessarily pre-EAO**: the ADM /
  General Mills miss of 16-Sep-2026 has none because the CSM raised it by email to the
  team instead of opening a ticket, so `jira_sync.py` will never see it and the daily
  Routine cannot find it. A row like that is added by hand with `append_row.py`, then
  `sort_tracker.py <month>`, since it appends out of date order.
- `Short Term Fix Status` is `Fixed` / `RCA Shared` / `Clarification Provided`, plus
  `Pending` for tickets still open in Jira. Adding a new value means adding it to the
  Dashboard's Fix Status table too.
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
