import asyncio
import os
from langchain_mcp_adapters.client import MultiServerMCPClient

class MCPTransport:
    def __init__(self):
        self.client = MultiServerMCPClient({
            'database': {'url':os.getenv('MCP_DATABASE_URL','http://mcp-postgres:8001/mcp'),'transport':'streamable_http'},
            'ops': {'url':os.getenv('MCP_OPS_URL','http://mcp-ops:8002/mcp'),'transport':'streamable_http'}})

    async def call(self, server, name, arguments):
        async with asyncio.timeout(15):
            async with self.client.session(server) as session:
                available = await session.list_tools()
                if name not in {tool.name for tool in available.tools}:
                    return {'ok':False,'code':'TOOL_UNAVAILABLE'}
                result = await session.call_tool(name, arguments)
                if result.isError or not isinstance(result.structuredContent,dict):
                    return {'ok':False,'code':'INVALID_TOOL_RESULT'}
                return result.structuredContent
