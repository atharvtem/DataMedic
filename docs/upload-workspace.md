# Check your own files

Choose **Your files** in the sidebar. Upload CSV or flat JSON tables, inspect discovered columns, select suggested checks or write your own, and create a plan. Groq or Gemini selects tables, columns, date fields, time grouping and chart types from the discovered metadata. There are no Olist names or fixed incident dates in this workspace.

Submitting a request immediately calculates its charts and read-only checks. Review the exact plan, including date boundaries, and use **Update charts and checks** after changing settings. Multi-column numeric checks run separately for each selected column. A failed check or chart does not block other steps; failures are shown as not measured, never zero findings. Findings appear in a table with dataset/table, columns, measured counts and suggested next steps. Charts never require data corrections first. The engine performs only validated built-in operations. It does not execute model-written Python or SQL. It never edits uploaded bytes or loaded tables. Planning sends file/column names, inferred types, counts and the request to the selected provider. Follow-up planning also sends aggregate check statistics (including numeric summaries), chart specifications, completion status and exclusion notes. It does not send raw rows, example row numbers or chart data values. Uploaded files live in the Streamlit session and are not saved to disk by this workflow.

Supported operations: missing/blank values, repeated rows or selected keys, unreadable numbers/dates, numeric summary, IQR unusual-value flags, and a single-key reference check between two files. Supported charts: numeric histograms, category aggregations, daily/weekly/monthly date aggregations, numeric scatter plots, and box plots. All five support optional colour grouping and pre-chart filters. Grouped bars appear side by side, time series are separate lines, and histogram groups share bins without stacking. Box plots use all usable rows, with quartiles/median and min/max whiskers. Scatter plots above 5,000 usable rows display a disclosed reproducible sample; checks still use all rows. Charts expose actual calculated values and excluded-row/group counts. The AI chooses the plan; local code calculates the results. Date conversion uses pandas' mixed-format parser and UTC; ambiguous date conventions need user review.

A custom request is accepted, but not every question is currently executable. The planner must list unsupported parts. Invalid table/column choices fail explicitly. This is a bounded analysis interface, not universal reasoning over every data type. Excel, PDFs, complex multi-table joins, causal diagnosis, arbitrary SQL and user-supplied code are not supported here yet.

Limits: five files, 20 MB total, 100,000 rows and 100 columns per table. All accepted rows are checked; type suggestions use up to 1,000 nonempty values per column. Numeric parsing does not guess currency or locale conventions. Category charts show the top 30 groups; time charts cap at 1,000 buckets. Results show up to 20 data-row numbers, not the full affected-row export. IQR flags and repeated keys are review candidates, not proof of errors.

**What should you do next?** explains possible fixes without applying them. The JSON download contains findings, counts, row references, chart summaries and suggestions. It is never a rewritten dataset.

The existing Olist MCP/LangGraph workflow remains under **Olist example**. The upload workflow uses a bounded iterative planner with local read-only execution; it does not use the separate Olist MCP tools.


Chart reliability: numeric category labels sort numerically; text labels sort
alphabetically. Crowded category and box plots switch to horizontal layouts.
Colour domains are taken from the uploaded table before filtering so a group
keeps its colour across charts using that field. Bar/count scales include zero;
percentage scales run from 0% to 100%. Scatter and box plots fit the observed
numeric range. Time axes and tooltip dates use UTC; absent measurements break
lines instead of implying an observed continuous trend.

Count charts can display raw counts, a percentage of all usable rows, a
percentage within each colour group, or (category/time only) a percentage within
each x category/time bucket. Select the denominator explicitly. All percentages
are calculated after filters/date bounds and before the category display cap.
Downloads retain counts and denominators. These options are row shares, not a
general calculated-business-metric engine. The source records are never changed.

Verified with `tests.check_chart_combinations` and `tests.check_upload_analysis`,
including shuffled inputs, renamed fields, filter stability, missing time
measurements, and percentage calculations. Sample PNGs were rendered and
visually reviewed during development. Very high-cardinality colour fields can
still be difficult to distinguish; choose a smaller grouping or filter.


Follow-up investigation is enabled by default and can be disabled in the request
form. It uses at most four provider calls (60 seconds each), eight atomic checks
and three charts. Multi-column numeric checks consume one step per column.
Repeated operations are skipped, including failures; the planner must change
arguments to repair an invalid step. A later planning failure retains earlier
results. The investigation history and stop reason appear above analysis
settings and in the downloaded report. Recalculating edited settings clears the
old investigation history because it describes the earlier run.

A stop means the planner chose no further work, could not make progress, failed,
or reached a limit; it does not prove that the question is fully answered.
Chart values are not fed back to the planner, so trend interpretation remains
limited. Offline controller scenarios run with
`python -m tests.check_file_investigation`; four synthetic live smoke cases pass across Groq and Gemini. Broader provider
follow-up quality remains unverified. See `docs/live-validation.md` and run
`python -m datamedic.evaluation.uploads` to repeat the live checks.

Malformed model responses now receive schema-only feedback and can be repaired
within the same four-call budget. Invalid payload contents are not echoed into
feedback. Planning error codes are included in investigation history and the
report; rate limits and timeouts preserve previously computed outputs. A run
with no data checks explicitly states that it offers no data-quality conclusion.

The live development evaluator now covers six scenarios per provider: numeric
histograms with malformed data, chart-only requests, clean/dirty conditional
follow-ups, reference coverage across two tables, and an undefined conversion
rate. Select individual cases with repeated `--case` arguments. Offline tests
in `tests.check_upload_evaluation` verify that the evaluator rejects empty
answers and follow-ups executed before prerequisite evidence.

Scope consistency: planner instructions now distinguish narrow requests (such
as missing/unreadable values) from broad data-quality exploration. Narrow
requests should stop after their requested evidence is available, even when
budget remains. This is a model instruction, not a deterministic guarantee that
arbitrary natural-language scope will always be interpreted correctly.

The development evaluator enforces exact scope for the malformed-reading case
(two checks and one histogram), and supports `--repeats 1`, `2`, or `3`.
Repeated runs retain their individual outcomes; a later success does not erase
an earlier failure. Example:

```sh
docker compose exec -T datamedic-app python -m datamedic.evaluation.uploads --case malformed-readings --case conditional-dirty --case ambiguous-rate --repeats 2
```
