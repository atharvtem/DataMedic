"""Probe the full MCP to database path, also used by Compose health checks."""
import asyncio
import sys
from fastmcp import Client


async def probe(url: str) -> dict:
    async with Client(url, timeout=5) as client:
        names = [tool.name for tool in await client.list_tools()]
        if "database_status" not in names:
            raise RuntimeError("Database status tool is unavailable")
        result = await client.call_tool("database_status", {})
        if result.is_error:
            raise RuntimeError("Database connectivity check failed")
        return {"tools": names, "database_status": result.data}


async def probe_all(urls: list[str]) -> list[dict]:
    return await asyncio.gather(*(probe(url) for url in urls))


if __name__ == "__main__":
    asyncio.run(probe_all(sys.argv[1:]))
