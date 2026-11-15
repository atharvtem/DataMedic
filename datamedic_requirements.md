# DataMedic: Requirements and Design Brief

**Author:** Atharv Tembhurnikar  
**Target Roles:** AI Engineer, LLM / Agent Engineer, Applied ML Engineer  
**Core Stack:** Python, LangGraph, FastMCP (Model Context Protocol), PostgreSQL, Docker Compose, a configurable LLM provider, LangSmith (optional), Streamlit (optional)

---

## Updated product direction (2026-11-14)

Users upload their own tables, inspect discovered columns, choose suggested checks
or describe a custom check. The agent selects relevant tables, columns, time
windows and charts, and explains measured results in simple language. It proposes
fixes and ends with “What should you do next?”. User datasets must never be
modified, even as a proposed future automation. Downloads contain findings and
suggestions, not repaired datasets. The Olist scenario is a development example;
claims of broad support must state supported formats and operations.

## 1. Executive Summary & Resume Positioning

### 1.1 The Problem
Modern data and engineering teams rely on automated monitoring (Z-score alerts, threshold checks, dbt tests) to detect *when* a business metric breaks—such as a sudden 35% drop in daily net revenue or a spike in failed checkout sessions. However, **detecting the symptom is trivial; diagnosing the root cause is manual, slow, and expensive.** Data engineers spend hours writing ad-hoc SQL queries across relational tables and cross-referencing ETL pipeline logs to figure out whether an anomaly came from duplicate webhook inserts, a broken discount rule, a missing ingestion batch, or an upstream API timeout.

Naive LLM-based "Text-to-SQL" chatbots fail in production for three reasons:
1. **Unbounded Cost & Latency:** They run expensive full-table `JOIN` and `SELECT *` queries blindly without checking cheap table metadata first.
2. **Zero Safety Guarantees:** Giving an LLM raw database access risks destructive mutations (`DROP`, `UPDATE`, `DELETE`), PII exposure, or database lockups.
3. **Confident Hallucination:** When logs and tables contain ambiguous or conflicting signals, standard agents guess a plausible-sounding cause instead of escalating to a human engineer.

### 1.2 The Solution: `DataMedic`
**DataMedic** is a budgeted autonomous diagnosis agent built on **LangGraph** and **Model Context Protocol (MCP)**. Given a data anomaly alert and access to a PostgreSQL database plus operational logs, `DataMedic` investigates the available evidence. The initial implementation targets one database; support for additional, unfamiliar schemas is a later validation goal, not an assumption:
* **Generates Competing Hypotheses:** Formulates 3 mutually exclusive root-cause theories before running heavy queries.
* **Executes Budget-Aware Diagnostics:** Operates under an explicit tool-point budget (e.g., 12 points per incident), prioritizing lower-cost diagnostic tools before heavier analytical queries. Points are a planner heuristic; actual query time, rows returned, and token use are measured separately.
* **Enforces Deterministic SQL Governance:** Routes database calls through an MCP server with SQL policy checks and database-enforced read-only access, returning structured denials and actionable feedback.
* **Practices Calibrated Abstention:** Automatically stops and escalates a structured triage brief to a human engineer if its budget expires with competing hypotheses still unresolved.

### 1.3 Strategic Resume Fit
This project unifies your existing profile into a single cohesive narrative:
* Connects your **UMD Agentic AI TA** leadership (LangGraph, multi-agent orchestration) with your **Hackveda Data Science internship** (100K+ retail transactions, pricing/discount anomalies) and **`DCFare`** (2.5M+ taxi trip records).
* Fills key industry keywords missing from your current project portfolio: **Model Context Protocol (MCP)**, **PostgreSQL**, **Docker Compose**, **deterministic tool guardrails**, and **multi-baseline quantitative benchmarking**.

---

## 2. Core Stack and Optional Services

The core project runs locally through Docker Compose. Hosted LLMs and observability services are optional integrations; their pricing, quotas, and model availability are provider-controlled and must be checked when selected. Local deterministic checks and benchmark runs should remain possible without cloud deployment.

| Layer | Technology | Role in System | Requirement / Notes |
| :--- | :--- | :--- | :--- |
| **Agent Orchestration** | **LangGraph** + `langchain-mcp-adapters` | Stateful cyclic graph managing hypotheses, tool budgets, retries, and abstention routing | Open-source (MIT) |
| **Tool Protocol** | **FastMCP** (`streamable-http` transport) | Exposes decoupled PostgreSQL and Ops-Log tool servers over internal Docker HTTP | Open-source (Apache 2.0) |
| **LLM** | Configurable provider and model | Structured hypothesis generation and investigation planning; deterministic rules enforce budgets and policies | Provider key optional for live LLM runs; pin and document selected model/version for evaluations |
| **Database** | **PostgreSQL 16** + `sqlglot` | Stores relational datasets + synthetic `etl_pipeline_logs` & `service_status_events` tables | Open-source (PostgreSQL License) |
| **Observability & Eval** | **LangSmith (optional)** | Traces agent runs and supports evaluation workflows; local logs and benchmark outputs remain available | Verify current pricing, retention, and quotas before use |
| **Frontend UI** | **Streamlit** | Interactive dashboard to trigger alerts, inspect live hypothesis elimination, and view SQL proofs | Open-source (Apache 2.0) |
| **Container & Cloud** | **Docker Compose** | Reproducible local deployment of the app, MCP servers, and PostgreSQL | Docker is a core deliverable; cloud deployment is optional after local behavior is reliable |

---

## 3. System Architecture & Data Flow

### 3.1 High-Level Container Architecture

```text
+-----------------------------------------------------------------------+
|                          Local Docker Host                            |
|                                                                       |
|  +-----------------------------------------------------------------+  |
|  |  Container 1: datamedic-app (Streamlit UI + LangGraph Engine)   |  |
|  |  - Hypothesis State Machine & 12-Point Cost Budget Controller   |  |
|  |  - Configurable LLM provider and model                          |  |
|  |  - Telemetry Exporter -> LangSmith Cloud                        |  |
|  +----------------+-------------------------------+----------------+  |
|                   | MCP (Streamable HTTP)         | MCP (HTTP)        |
|                   v                               v                   |
|  +---------------------------------+  +----------------------------+  |
|  | Container 2: mcp-postgres       |  | Container 3: mcp-ops       |  |
|  | (FastMCP Server - Port 8001)    |  | (FastMCP Server - Port 8002|  |
|  | - AST SQL Policy Gate (sqlglot) |  | - ETL Job Log Inspector    |  |
|  | - Cost-Tagged SQL Tools (1-5pt) |  | - Webhook & Config History |  |
|  +----------------+----------------+  +-------------+--------------+  |
|                   | Read-Only SQL                   | Read-Only SQL   |
|                   v                                 v                 |
|  +-----------------------------------------------------------------+  |
|  | Container 4: postgres-db (PostgreSQL 16 - Port 5432)            |  |
|  | - Initial dataset: Olist; NYC Taxi and Pagila are later validation phases |  |
|  | - Ops Telemetry Schema: ops_telemetry (etl_logs, config_audits) |  |
|  +-----------------------------------------------------------------+  |
+-----------------------------------------------------------------------+
```

### 3.2 MCP Server Specifications

#### Server A: `mcp-postgres` (Database Diagnostics & SQL Policy Gate)
All database queries pass through the `mcp-postgres` MCP server. The SQL AST policy gate (`sqlglot`, configured for PostgreSQL) is one layer of defense, paired with a database user that has read-only grants and, where supported, read-only transactions. Enforce statement timeouts and result row/byte limits at the execution layer. A `LIMIT` clause alone does not guarantee low compute cost.
* **Read-only policy:** Accept only supported read queries; reject writes, multiple statements, and data-modifying CTEs. Independently verify the database role cannot mutate data.
* **Bounded execution:** Apply statement timeouts and bounded result retrieval. Require explicit limits for potentially large result sets while recognizing that limits do not bound the work PostgreSQL performs.
* **Sensitive data policy:** Use database grants to restrict sensitive columns/tables where possible. Add AST checks as defense in depth; a simple list of column names is not comprehensive PII protection.
* **Counterexample feedback:** On denial, return structured policy details and a safe fix hint. Never include secrets or sensitive row data in errors.

**Cost-Tagged Tools Exposed by `mcp-postgres`:**
1. `inspect_database_schema()` — **Cost: 1 point.** Queries permitted schema metadata. Discovery is a tool capability; cross-schema diagnosis must be demonstrated through evaluation.
2. `check_table_health(table_name, date_col)` — **Cost: 1 point.** Runs bounded row counts, volume comparisons, null summaries, and key checks on a selected table. Validate identifiers against discovered metadata and use safe query construction.
3. `check_column_distribution(table_name, column_name, group_by_col)` — **Cost: 2 points.** Computes bounded summary statistics grouped by a validated column.
4. `execute_targeted_analytical_query(sql_query)` — **Cost: 5 pts.** Executes a multi-table `JOIN` or cohort aggregation validated by the SQL Policy Gate.

#### Server B: `mcp-ops` (Pipeline & Service Telemetry)
Simulates real-world operational context stored in the `ops_telemetry` schema:
1. `query_etl_pipeline_logs(window_hours, status_filter)` — **Cost: 2 pts.** Retrieves recent batch ingestion logs, row-count watermarks, and job exit codes.
2. `check_upstream_service_events(window_hours)` — **Cost: 2 pts.** Checks simulated third-party API health events (e.g., payment gateway `503` timeouts, currency rate feed staleness).
3. `inspect_config_deployments(window_hours)` — **Cost: 2 pts.** Lists recent pricing rules, promo code thresholds, or ETL schema mapping changes.

---

## 4. What the App Does & How It Works (Step-by-Step)

### 4.1 LangGraph State Schema

```python
class Hypothesis(TypedDict):
    id: str                  # e.g., "H1"
    category: str            # DUPLICATE_RECORDS | MISSING_INGESTION | SILENT_LOGIC_CORRUPTION | UPSTREAM_SERVICE_OUTAGE
    description: str         # Specific testable claim
    status: str              # ACTIVE | FALSIFIED | CONFIRMED
    confidence: float        # 0.0 to 1.0
    evidence: list[str]      # Exact tool outputs supporting/refuting this hypothesis

class AgentState(TypedDict):
    alert_text: str
    database_name: str
    budget_total: int        # Default: 12 points
    budget_remaining: int
    schema_summary: str
    hypotheses: list[Hypothesis]
    tool_history: list[dict]
    final_verdict: str       # Confirmed category OR "ESCALATE_AMBIGUOUS"
    final_report: str
```

### 4.2 End-to-End Execution Walkthrough

Suppose an automated alert triggers on the Olist database:
> **Alert:** *"Net realized payment revenue dropped 34% on 2018-08-15 compared to the trailing 7-day average, while total order count remained normal."*

1. **Step 1 — Schema Discovery (1 pt | Remaining: 11 pts):**  
   `DataMedic` calls `inspect_database_schema()` and discovers permitted tables and columns. This exposes schema metadata; the investigator must still select valid domain-specific fields based on evidence.
2. **Step 2 — Hypothesis Generation (0 pts — LLM Reasoning):**  
   Notice the clue in the alert: *order count is normal, but realized payment revenue dropped*. The LLM outputs 3 competing hypotheses in strict JSON:
   * **H1 (`MISSING_INGESTION`):** `order_payments` rows failed to ingest for 2018-08-15 despite `orders` being present.
   * **H2 (`SILENT_LOGIC_CORRUPTION`):** A pricing/discount or freight calculation bug zeroed out item prices or installments.
   * **H3 (`UPSTREAM_SERVICE_OUTAGE`):** A payment gateway outage left orders stuck in `unavailable` or `canceled` status.
3. **Step 3 — Cheapest Discriminating Check (1 pt | Remaining: 10 pts):**  
   Olist `order_payments` has no payment timestamp, so the investigator uses the order purchase timestamp from `orders` and joins it to `order_payments` through `order_id`. A bounded tool can compare payment-row coverage by purchase date.  
   *Result:* Coverage is normal for the alert date, weakening H1; the agent records the evidence and does not claim falsification unless the check actually rules the hypothesis out.
4. **Step 4 — Targeted Follow-Up (2 pts | Remaining: 8 pts):**  
   Between H2 and H3, `DataMedic` checks `inspect_config_deployments(48)` (2 pts) and finds a config change deployed at `2018-08-15 02:14 UTC`: `promo_discount_multiplier` updated from `0.10` to `1.00` (100% discount).
5. **Step 5 — SQL Proof Verification (5 pts | Remaining: 3 pts):**  
   Now confident H2 is the culprit, `DataMedic` spends 5 points on `execute_targeted_analytical_query(...)` to verify the exact dollar impact and affected product categories, confirming `payment_value = 0.00` on 148 promo orders.
6. **Step 6 — Structured Output & Reproducibility:**  
   `DataMedic` terminates early (saving 3 budget points), emits `final_verdict = "SILENT_LOGIC_CORRUPTION"`, and renders the exact SQL query, row counts, and timestamped config diff in Streamlit.

### 4.3 When It Abstains (`ESCALATE_AMBIGUOUS`)
If the agent runs out of its 12-point budget (or no remaining tool costs $\le$ `budget_remaining`) while **two or more hypotheses remain `ACTIVE` with similar confidence**, the router triggers `ESCALATE_AMBIGUOUS`. It outputs a concise triage handoff showing which theories were already ruled out and what specific question a human engineer needs to check next.

---

## 5. Staged Multi-Dataset Validation

Docker Compose and MCP are core project skills and remain in the implementation from the first milestone. Build and validate the full local path on Olist first: app/agent → MCP over the selected transport → PostgreSQL. Keep dataset loading and database configuration replaceable. Once the first benchmark works, add NYC Taxi and then Pagila as explicit generalization checks. A successful run on three datasets supports adaptability across these tested schemas; it does not prove universal schema agnosticism.

### Dataset 1: Brazilian E-Commerce Public Dataset by Olist (Primary Benchmark)
* **Source:** Kaggle (`olistbr/brazilian-ecommerce`, ~44 MB, CC BY-NC-SA 4.0).
* **Scale & Schema:** ~100,000 orders across **9 normalized tables** (`orders`, `order_items`, `order_payments`, `order_reviews`, `products`, `customers`, `sellers`, `geolocation`, `product_category_name_translation`).
* **Why It Fits:** Mirrors multi-table e-commerce data where revenue anomalies emerge across joins between orders, payment installments, freight values, and timestamps. The initial tool set and alerts should be designed against the actual Olist schema.
* **Sample Injected Bugs:**
  * Duplicate payment webhook records inflating `order_payments` for `credit_card` transactions.
  * Canceled orders accidentally included in daily revenue views due to status-mapping drift.
  * Missing `order_items` batch ingestion for a specific seller state (`SP`) while `orders` headers exist.

### Dataset 2: NYC TLC Yellow Taxi Trip Records (Domain Generalization & `DCFare` Continuity)
* **Source:** NYC Taxi & Limousine Commission Public Data (200K-row stratified sample + `taxi_zone_lookup` dimension table).
* **Scale & Schema:** Multi-table transportation telemetry (`yellow_tripdata`, `taxi_zones`, `rate_code_lookup`, `payment_type_lookup`).
* **Why It Fits:** Extends your `DCFare` work into an operational data-engineering context and tests whether the same agent/tool boundary can adapt to a different schema with limited dataset-specific configuration.
* **Sample Injected Bugs:**
  * Missing `$2.50` congestion surcharge or JFK airport flat-rate corruption (`RatecodeID = 2`) after a vendor feed update.
  * Foreign-key drift where `PULocationID` maps to `264/265` (`Unknown` zone) for 40% of trips from Vendor 2.
  * Negative or zero `trip_distance` rows paired with non-zero `total_amount` due to GPS parser timeouts.

### Dataset 3: Pagila Operational DVD Rental Database (Zero-Shot Schema Adaptation)
* **Source:** Official PostgreSQL Sample Database (`pagila`, open-source).
* **Scale & Schema:** **15 highly normalized operational tables** (`rental`, `payment`, `inventory`, `film`, `customer`, `staff`, `store`, `category`, `actor`, etc.) with complex foreign keys and composite views.
* **Why It Fits:** Provides a later unfamiliar-schema test. Report the prompts, configuration, and any dataset-specific setup required; metadata discovery alone is not proof of zero-shot adaptation.

---

## 6. Synthetic Bug Injection & Reproducible Benchmark Suite

### 6.1 Benchmark Dataset Construction (Staged)
Start with a small, manually reviewed Olist benchmark that exercises each diagnosis category and includes ambiguous cases. Validate that each injected issue changes the intended data, that the alert is reproducible, and that the ground truth is supported by observable evidence. Expand the suite toward 80 incidents after the generation process and scoring are stable; then add separate NYC Taxi and Pagila slices during the generalization phase. Keep development cases separate from held-out evaluation cases where practical, and disclose that synthetic cases test controlled scenarios rather than real-world incident prevalence.

| Ground-Truth Label | Count | Description of Synthetic Failure Scenario |
| :--- | :---: | :--- |
| `DUPLICATE_RECORDS` | 18 | Retry loops duplicating subsets of child rows (`order_payments` or `yellow_tripdata`) without violating primary keys |
| `MISSING_INGESTION` | 18 | Partial batch drops filtered by region, vendor ID, or payment type where parent headers exist without child records |
| `SILENT_LOGIC_CORRUPTION` | 18 | Broken discount multipliers, zeroed freight/surcharges, or corrupted foreign-key mappings |
| `UPSTREAM_SERVICE_OUTAGE` | 14 | Correlated `503` gateway timeouts or stale exchange-rate feeds recorded in `ops_telemetry` explaining metric drops |
| `ESCALATE_AMBIGUOUS` | 12 | Conflicting or incomplete signals (e.g., minor metric dip accompanied by two simultaneous partial errors) where abstaining is optimal |

*Note on Non-Triviality:* Include multi-step scenarios where a single-table count appears healthy and diagnosis requires cross-table aggregates or correlation with `ops_telemetry`. Measure scenario difficulty rather than asserting a target percentage before the cases exist.

### 6.2 Credible Baselines & Ablations
Evaluate the benchmark locally first; LangSmith is an optional tracing/evaluation integration. Compare equivalent model settings and prompts across these configurations, recording versions and run settings:
1. **Baseline 1 — No-Tool LLM:** Receives only the alert text and database schema; must guess the root-cause label without running queries.
2. **Baseline 2 — Unbudgeted Standard ReAct Agent:** Has full access to all `mcp-postgres` and `mcp-ops` tools, but lacks hypothesis-elimination prompting and cost awareness (tends to run expensive 5-point `JOIN` queries immediately).
3. **Target System — `DataMedic` (Budgeted Hypothesis-Elimination Agent):** Enforces the 12-point tool budget, cheap-first hypothesis falsification, SQL AST Policy Gate, and calibrated abstention.

### 6.3 Quantitative Resume Metrics
The evaluation harness (`eval/run_benchmark.py`) outputs a summary table directly transferable to your CV and GitHub README:
* **Root-Cause Diagnosis Accuracy (%):** Exact match against `ground_truth.json` across the 68 resolvable cases.
* **Abstention F1 / Escalation Precision (%):** Accuracy on the 12 ambiguous cases without over-escalating clear bugs.
* **Investigation Efficiency:** Tool points (internal budget), observed query latency/rows, and LLM tokens per incident versus the baseline. Do not call tool points SQL compute cost.
* **End-to-End Median Latency (s):** Wall-clock investigation time per incident.
* **Run-to-Run Consistency (%):** Agreement rate across 3 repeated runs on a 20-case subset at $T = 0$.
* **SQL Safety Compliance:** Report policy test cases and outcomes, including writes, multi-statement input, data-modifying CTEs, oversized results, timeouts, and restricted data. Treat the result as coverage of tested cases, not a universal guarantee.

---

## 7. Production Repository Structure

```text
datamedic/
├── docker-compose.yml              # Orchestrates postgres-db, mcp-postgres, mcp-ops, and datamedic-app
├── .env.example                    # Selected LLM key (optional), tracing key (optional), database settings
├── requirements.txt
├── data_loaders/
│   ├── load_olist.py               # Downloads/loads Olist 9 CSVs into olist_db
│   ├── load_nyc_taxi.py            # Added in generalization phase
│   ├── load_pagila.py              # Added in generalization phase
│   └── seed_ops_telemetry.py       # Populates baseline ETL & service status logs
├── mcp_servers/
│   ├── postgres_server.py          # FastMCP server (Port 8001) + sqlglot AST Policy Gate
│   └── ops_server.py               # FastMCP server (Port 8002) for ETL/config/service logs
├── agent/
│   ├── graph.py                    # LangGraph state machine & conditional budget/abstain routing
│   ├── llm_router.py               # Configurable provider/model and retry handling
│   ├── prompts.py                  # Evidence-grounded hypothesis & falsification prompts
│   └── schemas.py                  # Pydantic models for strict JSON structured outputs
├── eval/
│   ├── generate_benchmarks.py      # Generates versioned reproducible cases and ground_truth.json
│   ├── baselines.py                # No-Tool and Unbudgeted ReAct implementations
│   └── run_benchmark.py            # Batch runner logging metrics & traces to LangSmith
├── ui/
│   └── app.py                      # Streamlit dashboard (DB selector, live hypothesis trace, SQL proof)
└── tests/
    └── test_sql_guardrail.py       # Pytest suite verifying 100% block rate on unsafe SQL
```

---

## 8. Implementation Sequence

The ordered phases, work items, and exit criteria are maintained separately in [datamedic_implementation_plan.md](datamedic_implementation_plan.md). This document remains the requirements and design brief; use the implementation plan to track build order and progress.

---

## 9. Ready-to-Use Resume Bullet Points

Use this as a template only after the work is complete; replace bracketed values with measured results and do not claim unmeasured safety or performance outcomes:

> **DataMedic — Budgeted SQL Anomaly Investigation Agent** | *LangGraph, MCP (FastMCP), PostgreSQL, Docker Compose, [LLM provider]*
> * Built a containerized diagnostic agent using FastMCP tools and a PostgreSQL read-only role to investigate [N] reproducible Olist incidents; reported [measured diagnosis and abstention results].
> * Implemented budget-aware hypothesis testing and escalation; compared against [baseline] and measured [tool points, query latency, and token use]. Extended evaluation to [additional datasets] with [documented setup/configuration].
