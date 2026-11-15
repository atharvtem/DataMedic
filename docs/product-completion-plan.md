# Completing the general DataMedic workspace

The target is a read-only assistant that understands uploaded tables, investigates
questions, draws suitable charts, and suggests evidence-based fixes. A chart
request must not depend on fixing data first. Source datasets are never changed.
The earlier 35/100 rating was a subjective assessment, not a measured score.

| Stage | Deliverable | Completion test |
| --- | --- | --- |
| 1. Reliable analysis and charts | Type-aware ordering, consistent group colours, readable labels, explicit filters/units, clear counts versus rates, and visible exclusions. | Calculations and chart encodings match independently computed expected results; shuffled rows and renamed fields preserve meaning. Numeric category ordering is now covered. |
| 2. Evidence-driven investigation — implemented, expanded validation in progress | A bounded loop: discover schema, propose relevant checks, execute, inspect results, select follow-ups, then stop with an answer or state what is missing. Repair invalid steps without repeating them indefinitely. | On unseen fixtures, follow-up choices respond to measured findings, respect the step budget, preserve successful charts, and never change source data. |
| 3. More expressive questions | Multiple filters, calculated metrics, rates with explicit denominators, date comparisons and validated joins. Diagnose ambiguous relationships instead of silently duplicating rows. | Independently verified totals, rates, join cardinality and time windows across unrelated datasets. |
| 4. Useful findings and fixes | A prioritized findings table: dataset/table, columns, issue, affected count/rate, evidence, significance, suggested fix and how to verify it. Separate observations from possible explanations. | Each number traces to an executed result. No invented business rule or unsupported causal claim. Proposed fixes explain when they apply and are never executed. |
| 5. Clear follow-up experience | Retain the question, filters, chart settings and evidence so users can ask follow-ups such as changing a time window or comparing another segment. Support broader file formats in explicit increments. | Follow-ups preserve relevant context, show changed scope, avoid stale results, and explain unsupported inputs. |
| 6. Release validation | A repeatable evaluation set across unfamiliar datasets, both configured providers, realistic failures, chart requests and business questions. | Publish pass/fail results for calculation correctness, request fulfillment, useful explanations, privacy/read-only guarantees, latency and cost. No claim of universal dataset support. |

Stages are work items, not artificial score increments. Mark a stage complete
only after its acceptance tests pass. The overall product is complete for an
agreed supported scope when all gates pass; it cannot honestly promise every
possible dataset or question.

Current limitations: file investigations use a bounded follow-up loop verified with offline planners; the expanded twelve-case live development run passed seven cases before fixes; rate limits and ambiguous-request handling exposed remaining reliability gaps. Fixes are
mostly generic, joins/derived metrics/multiple filters are not implemented, and
CSV/flat JSON are the supported input formats. The separate Olist investigation
does not establish general uploaded-file investigation capability.


Stage 1 delivery: type-aware ordering, adaptive horizontal category/box plots,
stable colour domains, explicit count/percentage selectors and denominators,
zero-based bars, fixed 0–100% percentage axes, UTC time labels and missing-data
gaps are implemented. Calculation/schema/UI regression tests pass and sample
charts were visually reviewed. Percentage support is limited to row shares;
general business rates remain Stage 3. This does not complete the broader
investigation product or guarantee readability for unlimited colour groups.


Stage 2 delivery: the upload workspace now executes up to 11 atomic operations
(8 checks and 3 charts) over at most four planning rounds, with a 60-second
limit per provider call. Follow-up planning receives measured aggregate check
statistics and chart completion/failure information. Identical operations are
not repeated even if their reasons change; invalid operations can be repaired
with new arguments. Successful outputs survive later provider failures.
The UI and downloaded report expose the execution history and stop condition.
Users can disable follow-ups for the original single-plan workflow.

Offline acceptance scenarios verify evidence-dependent decisions on clean and
malformed sensor fixtures, invalid-column repair, repeated-operation prevention,
scalar-column budget accounting, timeout/failure preservation, and unchanged
source tables. Existing upload, chart and provider-contract regressions pass.
This verifies the controller, not real-provider reasoning quality. Charts send
status and exclusion notes rather than their underlying values to follow-up
planning, so reasoning about chart trends remains limited. Results are measured
findings with explicit stop conditions, not a synthesized business diagnosis.
Four synthetic live cases now pass across Groq and Gemini (see docs/live-validation.md). Do not mark the full stage acceptance complete until broader unseen-question evaluation covers these limitations.


Expanded Stage 2 validation (November 14): six scenarios per provider now cover
conditional clean/dirty follow-ups, two-table reference coverage and ambiguous
metrics in addition to chart requests. The initial live run passed 7/12; its
report is retained separately rather than overwritten by reruns. Bounded repair
of schema-invalid plans, visible planning error codes, and honest no-measurement
UI text are now implemented. Clarification instructions explicitly require the
missing metric definition instead of unrelated summaries. Offline tests cover
these changes and verify the evaluation checks themselves. See
`docs/live-validation.md` for initial results and targeted post-fix results.

Post-fix targeted validation passed all five initially failed cases (Groq 4/4, Gemini 1/1). This is not a fresh full-suite pass. Preserve the initial 7/12 report and continue to track provider variability and unnecessary checks before closing Stage 2.

Scope consistency update: narrow-request instructions were tightened and the
evaluator now rejects unrelated checks in the missing/unreadable fixture.
The focused two-repeat run passed 6/12; all six failures reported provider
HTTP 429. Completed investigations met scope checks, but this does not close
the provider-availability gate. Rate-limit messages now explain the condition
and preserve earlier evidence. The next implementation increment is Stage 3's
multiple filters, with deterministic calculations and offline validation;
further live acceptance should wait for quota availability.
