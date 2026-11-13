# DataMedic

An evidence-driven database incident investigator using PostgreSQL and MCP.
The current milestone provides the container foundation; the investigation
graph, dataset loader, and UI are subsequent planned phases.

## Start the local foundation

Prerequisites: Docker Engine/Desktop with Docker Compose v2.

```sh
cp .env.example .env
docker compose up --build -d
docker compose ps
docker compose logs -f datamedic-app mcp-postgres
docker compose exec datamedic-app python -m datamedic.probe http://mcp-postgres:8001/mcp
docker compose down
```

The app logs discovered tools and database connectivity every 30 seconds.
All four services use a private internal network with no published host ports.
PostgreSQL persists in a named volume. `down` preserves that data. Database
initialization runs only on a new volume; changing `.env` passwords does not
rotate credentials in an existing database.

The MCP service uses a dedicated reader account with read-only transactions
and a five-second statement timeout. It exposes schema discovery, bounded payment coverage, and governed analytical
SQL. See [SQL boundary and checks](docs/sql-boundary.md).
The app accesses the database through MCP and has no database credentials.
No LLM key is needed for this milestone.

Python dependencies are pinned in `uv.lock`; images install with `uv sync
--frozen --no-dev`. For local development use Python 3.12+ and `uv sync`.
HTTP transport follows the [FastMCP documentation](https://gofastmcp.com/deployment/running-server).

## Build status

- Phase 0 specified: [first incident](docs/first-incident.md).
- Phase 1 stack running and MCP probe verified; fresh-volume check remains.
- Phase 2 complete: deterministic Olist loading and synthetic incident telemetry.
- Phase 3 complete: bounded diagnostic tools and SQL governance verified in Docker.
- Phase 4 complete: separate operations MCP server and reader role verified.
- Phase 5 next: the LangGraph investigation loop.

See [operations MCP tools and setup](docs/operations-mcp.md).

See [Olist setup and measured incident](docs/olist-data.md) to reproduce the data.

See the [implementation plan](datamedic_implementation_plan.md) and
[requirements](datamedic_requirements.md) for the full sequence.
