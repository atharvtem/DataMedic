# Live validation status

The deterministic path is verified end to end against PostgreSQL and both MCP servers. Its seeded missing-ingestion diagnosis uses 8/12 points. The development regression suite passed 21 evidence-replay runs; this is not a held-out benchmark.

Live provider checks with the configured credentials found:

- Groq `openai/gpt-oss-120b`: completed live diagnosis MISSING_INGESTION using five MCP calls, 8/12 points and 7,787 reported tokens. Earlier runs exposed timezone/window mistakes and HTTP 429; canonical window binding and one bounded rate-limit retry were added. This is one successful development run, not a benchmark result.
- Gemini requested `gemini-3.5-flash`, served `gemini-3.6-flash`: valid hypotheses and schema discovery; subsequent planning failed with HTTP 503. Model listing and generation both confirmed credential access. Full live investigation remains unverified.

Safe failures produce escalation, with provider error codes visible separately from evidence. There is no automatic provider switch. Per-step planning is bounded to 60 seconds; output tokens are capped. The user can inspect live tool progress and the remaining budget in Streamlit.

## UI acceptance checks

1. Open http://localhost:8501, keep purchase date 2018-08-15, budget 12, planner deterministic, and click Investigate.
2. Expect MISSING INGESTION, 8 points spent, 4 remaining, and five evidence entries.
3. Expand coverage evidence: 288 orders, 188 with payments, 100 missing payment coverage. ETL evidence has 102 missing payment rows (multiple payment sequences explain the different count).
4. Set budget to 3 and run again: expect ESCALATE AMBIGUOUS, with a next manual check and no budget overspend.
5. Groq/Gemini modes make real API calls. Provider quota/availability errors should appear explicitly, without claiming a supported diagnosis.

Remaining product work includes reliable live provider runs, reviewed multi-category scenarios, no-tool/unbudgeted baseline comparisons, and later dataset generalization. The UI is usable but the full project is not complete.


## Upload investigation validation — November 14, 2026

The repeatable synthetic development suite passed **4/4 live cases**:

| Provider | Case | Steps / calls | Seconds | Reported tokens |
| --- | --- | --- | --- | --- |
| Groq | Missing/unreadable readings and histogram | 4 / 2 | 2.25 | 4,510 |
| Groq | Category chart only | 1 / 2 | 4.60 | 3,814 |
| Gemini | Missing/unreadable readings and histogram | 3 / 2 | 8.15 | 5,289 |
| Gemini | Category chart only | 1 / 2 | 5.17 | 4,203 |

Both providers found one missing and one unreadable reading among six rows;
the histogram included four numeric readings. The chart-only case produced
North=3, South=2, East=1 without running data checks. All runs preserved input
tables, avoided execution failures, and stopped normally within the configured
budget. Groq served `openai/gpt-oss-120b`; Gemini requested `gemini-3.5-flash`
and served `gemini-3.6-flash`. No provider errors were reported in these runs.

Reproduce (makes billable provider calls using synthetic data):

```sh
docker compose exec -T datamedic-app python -m datamedic.evaluation.uploads
```

The JSON report is [upload-live-evaluation.json](upload-live-evaluation.json).
These are development smoke tests, not held-out generalization results. They
do not establish reliable reasoning across arbitrary questions, chart trends,
or ambiguous business rules. The earlier offline tests cover invalid-step
repair, deduplication, budget exhaustion, timeouts, and result preservation.
Monetary cost is not estimated; token counts are provider-reported.

## Expanded upload investigation evaluation — November 14, 2026

The suite now has six scenarios per provider (12 total). Besides the original
histogram and chart-only cases, it tests clean/dirty conditional follow-ups,
reference coverage across shipment/catalog files, and an undefined conversion
rate. The dirty conditional case must execute its unreadable-number check in a
later round than the prerequisite summary; the clean case must stop after the
summary. Reference coverage expects two nonblank missing references and one
separately reported blank key. Ambiguous-rate acceptance requires a specific
missing definition and no unrelated computations.

The initial expanded run passed **7/12**. Its five failures were:

- Groq malformed-readings: valid chart/checks survived a later planning failure;
  no HTTP error was reported, and the original controller did not retain the
  exception classification.
- Groq conditional-clean and reference-coverage: HTTP 429.
- Groq ambiguous-rate: stopped without an explicit missing-definition entry.
- Gemini ambiguous-rate: reported the missing definition but also ran two
  unrequested numeric summaries. No conversion rate was fabricated.

Changes made after this run:

- Schema-invalid plans receive schema diagnostics and can be repaired within
  the existing four-call limit. Failed outputs are not executed; earlier
  successful results survive. Offline tests force repeated invalid responses
  to verify the limit and exclude invalid payload values from feedback.
- Planning error codes are retained in the UI and downloadable report.
- Instructions explicitly require evidence before conditional follow-ups and
  clarification without unrelated summaries for an undefined metric.
- Empty runs no longer imply a clean-data result in the UI.

A targeted rerun of the five failed cases passed **5/5**: Groq 4/4 and Gemini
1/1, with no reported provider errors. This is a targeted rerun, **not a fresh
12/12 run or a held-out benchmark**. Provider variability and quota constraints
remain; Groq also still adds broader checks on some loosely worded requests.
No real-provider schema failure occurred during the targeted rerun, so schema
repair is verified by controlled offline tests rather than live evidence.

Reports:

- [Initial 7/12 results](upload-live-evaluation-v2-initial.json)
- [Groq targeted 4/4 rerun](upload-live-evaluation-v2-groq-recheck.json)
- [Gemini targeted 1/1 rerun](upload-live-evaluation-v2-gemini-recheck.json)

Reproduce a focused case with:

```sh
docker compose exec -T datamedic-app python -m datamedic.evaluation.uploads --provider groq --case ambiguous-rate
```

Offline investigation, evaluator, upload UI, chart and provider-contract tests
pass. The full Stage 2 release gate remains open for broader unseen questions,
consistent request scope, and repeatability under provider failures.

## Scope and repeatability — November 14, 2026

The v3 evaluator now rejects unrelated checks in the missing/unreadable-reading
scenario, even if the requested measurements are correct. Planner instructions
explicitly distinguish narrow questions from broad data-quality exploration.
`--repeats` supports one to three passes while retaining every outcome.

A focused repeatability run covered three cases twice for each provider:
malformed readings, evidence-dependent conditional checks, and an undefined
conversion rate. **6/12 passed** (Groq 5/6, Gemini 1/6). All six nonpassing runs
reported HTTP 429. One retained a completed summary before the follow-up was
rate-limited; the other five were rate-limited before any operation executed.
All completed investigations met the stricter scope checks. Groq's two
malformed-reading runs each used exactly two checks and one chart, with no
additional outlier or summary checks. Inputs remained unchanged throughout.

[Full repeatability report](upload-live-scope-repeatability.json)

This does not establish reliable provider availability or general scope
interpretation. It is a fixed synthetic development set, not held-out evidence.
No failed attempts were removed or rerun to improve the reported score.

The UI now identifies rate limiting explicitly and advises waiting for limits
to reset/checking quota, while keeping existing results. This wording change
was deployed after the live run and verified with offline failure injection;
the saved report retains the earlier generic stop wording.

Offline investigation, evaluation and upload UI regressions pass, including
scope rejection, bounded repeats, and retention of charts after HTTP 429.
Further live repetition should wait for quota availability rather than repeat
this rate-limited batch. Product work can proceed to multiple filters while
availability and broader Stage 2 acceptance remain open.
