# Investigation loop

The app image now includes a LangGraph investigation engine using langchain-mcp-adapters sessions to discover and call both internal MCP servers. It has no database credentials or baseline/ground-truth access.

```sh
docker compose exec -T datamedic-app python -m datamedic.investigate > data/investigation.json
docker compose exec -T datamedic-app python -m datamedic.investigate --budget 3
```

The default date is 2018-08-15. Set `--date YYYY-MM-DD`, `--alert '...'`, and `--budget N` as needed. Dates drive tool windows; alert text is recorded as context. The current deterministic Olist planner does not interpret arbitrary natural-language incident types. No LLM key is required. The app now serves a Streamlit review interface at localhost:8501 as well as this CLI.

## Graph and controls

Flow: initialize hypotheses → plan → validate/charge/call → assess evidence → plan again or report. Typed Pydantic models validate alerts, hypotheses, requests, and reports. LangGraph keeps hypotheses, budget, tool history, results, and terminal report. Tool results are checked for their structured success envelope; missing or malformed evidence fields cannot produce the supported diagnosis.

The graph owns costs and server routing. Attempts, denials, and failures consume points. Unknown tools and unaffordable requests are never called. A tool can be attempted at most twice. Each transport call has a 15-second deadline including MCP discovery/session setup. The fixed planner makes one attempt per tool; it has no automatic retry. Graph retry limits also constrain injected planners. Planner implementations provide hypotheses and the next validated tool request; they cannot set costs or terminal verdicts.

The default sequence is schema discovery (1), eight-day purchase coverage (1), ETL records (2), service records (2), and configuration records (2). It stops at 8 points when evidence supports missing ingestion. The heavier SQL tool is available through the same deterministic budget gate but is not needed by this development planner.

## Evidence and limits

Four competing hypotheses start unresolved: missing ingestion, logic corruption, upstream outage, and duplicates. Coverage provides initial support for missing rows. A supported ingestion verdict additionally requires seven reference days, reduced coverage, matching purchase windows, a failed payment batch whose actual row count equals the observed count, sufficient expected-row shortfall to account for missing orders, successful order ingestion with matching counts, and explicit healthy/unchanged service and configuration records. Conflicting evidence or absent required evidence escalates. Alternatives are weakened, not conclusively falsified.

This is an explicit, scenario-specific decision rule. It supports the mechanism in the controlled case; aggregate counts do not identify missing source keys or establish lost monetary value. The report asks for source-to-import reconciliation and replay verification. No access to the hidden removed-key list is required or allowed. Only MISSING_INGESTION and ESCALATE_AMBIGUOUS are emitted in this first scenario.

The JSON trace includes evidence IDs, tool parameters/results, per-call latency, cost, remaining budget, hypotheses, terminal reason, and manual follow-up. Deterministic planning uses zero model tokens. Groq and Gemini planning adapters are implemented; live validation requires API keys. See [provider setup](providers.md). No LangSmith credentials are required.

## Verification

```sh
docker compose exec -T datamedic-app python - < tests/check_investigation.py
```

Verified against real MCP services: supported incident diagnosis at 8/12 points. Replay checks cover four insufficient budgets, missing ETL, conflicting service evidence, mismatched purchase windows, charged failures, repeated-tool termination, and unavailable-tool termination. These are development checks, not held-out benchmark results.
