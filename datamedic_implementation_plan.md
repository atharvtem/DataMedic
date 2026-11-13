# DataMedic: Step-by-Step Implementation Plan

This is the working build sequence for DataMedic. It turns the project requirements in [datamedic_requirements.md](datamedic_requirements.md) into ordered, reviewable steps. The plan has no fixed dates. Complete each phase's exit criteria before moving to the next; adjust the plan when implementation evidence changes a requirement.

## Product goals to preserve

- **Docker Compose is part of the deliverable from the start.** The database, MCP server, and application run as services in a reproducible local stack.
- **MCP is part of the product architecture, not a resume-only keyword.** The LangGraph app discovers and calls the database and operations tools through MCP.
- **The investigation loop remains the differentiator:** competing hypotheses, evidence-based checks, a bounded tool-point budget, SQL governance, and explicit escalation when evidence is insufficient.
- **Start with Olist.** Add NYC Taxi and Pagila only after the Olist flow and evaluation are repeatable. Additional datasets test generalization; they do not imply universal schema independence.
- **Use measured results only.** Tool points are an internal planning heuristic. Measure query latency, results, tokens, diagnosis quality, and abstentions separately.

## Phase 0 — Confirm scope and define the first incident

**Status:** Complete specification in [first incident](docs/first-incident.md).
Selected missing payment ingestion; alert percentages are computed, not assumed.
The reproducible injection and ground-truth manifest will be built in phase 2.

1. Read the requirements and lock the first release to one Olist anomaly scenario.
2. Choose an alert that can be explained with available Olist columns and seeded operational evidence. Use `orders.order_purchase_timestamp` for purchase-date analysis; `order_payments` does not contain a payment timestamp.
3. Write down the alert, expected root cause, evidence that would support it, evidence that would falsify it, and cases where the agent should abstain.
4. Define the first categories to support: duplicate records, missing ingestion, logic corruption, upstream/service issue, and ambiguous evidence. Keep the set small enough to implement and score correctly.
5. Decide and record the initial tool-point costs and incident budget. Treat these as planner settings, not physical database cost estimates.

**Exit criteria:** One concrete, schema-correct Olist incident is specified with observable ground truth and a clear abstention condition.

## Phase 1 — Establish the Docker Compose foundation

**Status:** Running stack verified: all three services healthy and app MCP probe
passes. Initialization now ships inside the PostgreSQL image with controlled
permissions; the existing volume was repaired without deletion. A separate
fresh-volume startup check remains before claiming clean-checkout validation.

1. Create the repository layout and a `docker-compose.yml` with PostgreSQL, a minimal FastMCP server, and the application container.
2. Put services on a private Compose network. Persist PostgreSQL data with a named volume; expose only the ports needed for local development.
3. Add health checks and startup dependencies so the app does not attempt MCP/database work before those services are ready.
4. Add configuration through environment variables and an `.env.example`. Keep real keys out of source control and container images.
5. Add a short README section with prerequisites and the commands to build, start, inspect logs, and stop the local stack.

**Exit criteria:** A clean checkout can start the services through documented Docker Compose commands, and the app container can reach PostgreSQL over the internal network.

## Phase 2 — Load and understand Olist

**Status:** Complete for the selected two-table incident scope. Official CSVs
loaded in Compose: 99,441 orders and 103,886 payments. Repeated incident loads
produce identical manifests. The 102 removed payments total 18,351.42;
telemetry and the measured alert agree. Reader access to baseline and ground
truth schemas is denied. See [Olist setup](docs/olist-data.md).

1. Implement a deterministic Olist loader for the selected source files. Document acquisition, licensing, expected files, and checksums or version where practical.
2. Load the data into a dedicated Olist schema/database using explicit column types and stable table names.
3. Add indexes for the joins and time columns used by the first scenarios; avoid speculative indexing across every column.
4. Seed a separate `ops_telemetry` schema with baseline ETL, service, and configuration events. Clearly label synthetic records and make their timestamps line up with scenario windows.
5. Record row counts and key relationships, then document the actual columns used by the first incident.

**Exit criteria:** Re-running the documented loader creates a known baseline, and the first scenario's alert and ground truth can be checked directly against the loaded tables and telemetry.

## Phase 3 — Build the MCP database server and safety boundary

**Status:** Complete for the first incident. Schema discovery, a fixed payment
coverage diagnostic, conservative SQLGlot SELECT policy, bounded execution,
and structured errors are implemented. Docker integration checks passed for
MCP invocation, policy denials, result caps, timeout, and independent database
permissions. See [SQL boundary and coverage](docs/sql-boundary.md). Generic
identifier-driven table/distribution diagnostics are deferred; fixed coverage
is the bounded scenario tool selected by step 4.

1. Implement the FastMCP PostgreSQL server and choose/document its transport. Keep it on the internal Compose network.
2. Create a dedicated PostgreSQL role with only the required read permissions. Verify at the database level that it cannot write, regardless of what SQL the model requests.
3. Implement `inspect_database_schema()` for permitted schemas and columns.
4. Implement one or two bounded diagnostic tools needed for the first Olist scenario. Validate table and column identifiers against discovered metadata; parameterize values and avoid interpolating untrusted identifiers into SQL.
5. Add the `sqlglot` PostgreSQL-dialect policy gate for supported query shapes. Reject writes, multiple statements, and data-modifying CTEs; return structured denials and safe fix hints.
6. Enforce statement timeouts and result row/byte caps in the execution path. A SQL `LIMIT` is not a substitute for a timeout or a compute bound.
7. Add policy cases for allowed reads, writes, malformed input, multiple statements, data-modifying CTEs, oversized results, and restricted data. Record what is covered and any limitations.

**Exit criteria:** An MCP client inside Compose can discover schema and invoke the diagnostic tools; unsafe operations are blocked by both policy checks and database permissions; query execution is bounded.

## Phase 4 — Add the MCP operations server

**Status:** Complete. Separate internal FastMCP operations service and reader
role provisioned. Three bounded tools return timestamped synthetic records.
The app discovers both servers. Docker integration and independent privilege
checks passed; see [operations contract](docs/operations-mcp.md).

1. Implement a separate FastMCP operations server for the `ops_telemetry` schema.
2. Expose narrowly scoped tools for ETL job logs, upstream service events, and configuration changes. Filter by bounded time windows and cap result counts.
3. Use a read-only database role for this server as well. Return structured records with timestamps and source identifiers so the agent can cite evidence.
4. Configure the app to discover/call both MCP servers through Compose networking.

**Exit criteria:** The app can invoke database and operations tools through MCP and receive structured, bounded, timestamped results from both.

## Phase 5 — Implement the LangGraph investigation loop

1. Define typed state for the alert, permitted schema summary, hypotheses, evidence, tool history, remaining budget, verdict, and report.
2. Define structured outputs for hypotheses, tool requests, evidence updates, and the final report. Validate model output before changing state or calling a tool.
3. Generate a small set of distinct, testable hypotheses before expensive investigation. Do not require hypotheses to be mutually exclusive if the scenario allows multiple causes.
4. Let deterministic graph logic enforce tool availability, point costs, retry limits, and budget accounting. The model may recommend the next check but cannot override these controls.
5. Update each hypothesis from tool evidence with a short rationale and source reference. Distinguish `SUPPORTED`, `WEAKENED`, `FALSIFIED`, and `UNRESOLVED`; do not mark a cause confirmed on a weak correlation alone.
6. Add terminal routes for supported diagnosis, budget exhausted, no useful tool available, and ambiguous/conflicting evidence. Each uncertain route produces `ESCALATE_AMBIGUOUS` with what was checked and what a human should verify.
7. Keep provider/model configuration separate from graph logic. Support deterministic fixtures or a fake model for local development without an API key.

**Exit criteria:** A complete investigation can run in the local stack, respects budget and tool policies, records evidence, and abstains when the evidence does not justify a diagnosis.

## Phase 6 — Create the Olist benchmark and baselines

1. Create a small reviewed set of Olist cases covering the supported labels, including at least one genuinely ambiguous case.
2. For each case, store a reproducible alert, baseline data reference, injection procedure, expected label, evidence needed, and acceptable abstention behavior.
3. Keep prompt-development cases separate from held-out evaluation cases where feasible. Version the generator, case manifest, and ground truth.
4. Implement three comparable configurations: no-tool LLM, unbudgeted tool-using baseline, and DataMedic. Keep model/version, prompts, and run settings consistent where the comparison permits.
5. Report diagnosis accuracy and per-class errors, abstention precision/recall or F1, tool points, actual query latency, returned rows, token use, and run-to-run variation.
6. Include failure examples and limitations. State clearly that synthetic cases evaluate controlled scenarios and do not establish real-world incident performance.
7. Make LangSmith optional: the benchmark must save usable local results even when tracing credentials are absent.

**Exit criteria:** The benchmark can be regenerated and run reproducibly; ground truth is independently inspectable; baseline and DataMedic results can be compared without claiming unmeasured gains.

## Phase 7 — Build the reviewable demo

1. Add a Streamlit interface to enter/select an alert and start an investigation.
2. Display the hypothesis list, state changes, evidence, MCP tool calls, budget points, elapsed time, and final verdict.
3. Show the SQL or tool parameters used and the bounded results supporting the report. Hide restricted values and secrets.
4. Make escalation visible and useful: show unresolved hypotheses, evidence gaps, and a concrete next manual check.
5. Use a fixed, reproducible demo incident so the main flow is easy to inspect.

**Exit criteria:** A reviewer can follow the incident from alert through evidence to diagnosis or abstention without relying on hidden logs.

## Phase 8 — Test generalization on the other databases

1. Add NYC Taxi as a separate dataset loader and define domain-correct alerts and ground truth.
2. Run the same core agent and MCP interfaces. Record any configuration, prompt, or tool changes needed for this schema.
3. Add Pagila as a second unfamiliar-schema check and repeat the same process.
4. Keep results split by dataset. Report performance and adaptation effort per dataset; do not pool results in a way that hides failures.
5. Treat any dataset-specific mapping as explicit configuration and document it. The generalization claim is about measured performance on these datasets under the documented setup.

**Exit criteria:** The same core orchestration and MCP contract have been evaluated on all intended datasets, with per-dataset results and required setup documented.

## Phase 9 — Package and present the project

1. Polish setup instructions, architecture diagram, threat/safety boundaries, benchmark method, results, and known limitations.
2. Add a short demo recording only after the local demo is reproducible.
3. Consider cloud deployment after local Docker Compose setup is stable. Document cloud costs, secrets handling, network exposure, and teardown steps if deployed.
4. Write resume bullets from completed work and measured outcomes only. Separate observed results from targets or hypotheses.

**Exit criteria:** A reviewer can clone, run, understand, and inspect the project and its evidence without needing undocumented setup or trusting unsupported claims.

## Working agreement for future implementation turns

- Work on the earliest incomplete phase unless a concrete dependency requires another order.
- Keep the requirements document authoritative for scope and constraints; put task sequence and progress in this file.
- Update this plan when implementation evidence changes the sequence or acceptance criteria.
- Mark a phase complete only when its exit criteria are met; record blockers and decisions next to the relevant phase.
