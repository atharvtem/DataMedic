"""Foundation service: discover MCP tools and report connectivity periodically."""
import asyncio
import json
import logging
import os
from datamedic.probe import probe_all


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    urls = [os.environ.get("MCP_DATABASE_URL", "http://localhost:8001/mcp"),
            os.environ.get("MCP_OPS_URL", "http://localhost:8002/mcp")]
    while True:
        try:
            status = await probe_all(urls)
            logging.info("Foundation ready: %s", json.dumps(status))
        except Exception:
            logging.error("MCP/database unavailable; retrying in 30 seconds")
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
