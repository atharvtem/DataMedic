# Groq and Gemini planning

Provider integrations are explicit selections: `--planner groq` or `--planner gemini` in the CLI, or the planner selector in the UI. There is no automatic provider fallback. Deterministic mode remains available without credentials.

Add these entries to the existing ignored `.env`, retaining the database settings:

```dotenv
GROQ_API_KEY=
GROQ_MODEL=openai/gpt-oss-120b
GEMINI_API_KEY=
GEMINI_MODEL=gemini-3.5-flash
```

Then recreate the app with `docker compose up -d datamedic-app`.

The app alone receives provider credentials and an outbound network connection. The database and MCP services stay on the private internal network. Docker publishes only the app at `127.0.0.1:8501`.

Groq's [model documentation](https://console.groq.com/docs/model/openai/gpt-oss-120b) lists `openai/gpt-oss-120b`. Google's [Gemini 3.5 Flash documentation](https://aistudio.google.com/docs/models/gemini-3.5-flash) says the ID is deprecated and requests are routed to Gemini 3.6 Flash. The requested model and API-reported served model are saved per call; configure a newer explicit ID if reproducibility requires it.

The model proposes four hypotheses and the next tool request. Schema discovery is enforced first. For named coverage/operations tools, the application binds exact date windows from the selected purchase date and requests unfiltered ETL evidence; the model cannot change these scenario windows. JSON outputs are validated before graph actions. The graph owns budget, retry bounds, allowed tools, evidence assessment and verdicts. This remains an Olist missing-ingestion decision rule even with model-driven planning; multi-category diagnosis is pending. Provider calls use a 45-second HTTP timeout, a 60-second total planning-step deadline, and one bounded HTTP 429 retry. API failure or invalid output causes escalation. Prompts include permitted tool evidence and alert text; secrets are not included.

Offline mocked HTTP checks cover both provider contracts, JSON parsing, token accounting, and served-model capture. Keys are configured. Groq completed the live incident after window handling fixes and bounded rate-limit retry. Gemini generation succeeded but its full run encountered HTTP 503; see [live validation](live-validation.md). Comparative benchmarks remain pending.

```sh
docker compose exec -T datamedic-app python -m datamedic.investigate --planner groq
docker compose exec -T datamedic-app python -m datamedic.investigate --planner gemini
```

## Review interface and development regression suite

Open http://localhost:8501 for alert entry, budget selection, hypothesis statuses, tool parameters, results, latency, verdict, and JSON export. Live tool progress, budget, and hypothesis updates stream during the investigation.

The regression runner captures live MCP evidence and replays seven controlled variants three times. It does not mutate the database and is explicitly labeled development evidence replay, not a held-out benchmark or provider comparison:

```sh
docker compose exec -T datamedic-app python -m datamedic.evaluation.run
docker compose cp datamedic-app:/tmp/datamedic-regression.json data/regression.json
```
