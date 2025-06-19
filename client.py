import asyncio, json, os, re, sys
from contextlib import AsyncExitStack
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

# --------------------------------------------------------------------------- #
# MCP Client
# --------------------------------------------------------------------------- #

class MCPClient:
    """MCP client supporting stdio, SSE, and Streamable HTTP transports."""

    def __init__(self) -> None:
        self.exit_stack = AsyncExitStack()
        self.session: Optional[ClientSession] = None

    # internal connection helpers ------------------------------------------------
    async def _bootstrap(self, reader, writer) -> None:
        self.session = await self.exit_stack.enter_async_context(
            ClientSession(reader, writer)
        )
        await self.session.initialize()
        tools = [t.name for t in (await self.session.list_tools()).tools]
        print("Connected ✅  Tools available →", ", ".join(tools) or "none")

    async def _connect_stdio(self, script_path: str) -> None:
        cmd = "python" if script_path.endswith(".py") else "node"
        params = StdioServerParameters(command=cmd, args=[script_path])
        reader, writer = await self.exit_stack.enter_async_context(stdio_client(params))
        await self._bootstrap(reader, writer)

    async def _connect_sse(self, url: str) -> None:
        reader, writer = await self.exit_stack.enter_async_context(sse_client(url))
        await self._bootstrap(reader, writer)

    async def _connect_streamable(self, url: str) -> None:
        reader, writer, *_ = await self.exit_stack.enter_async_context(
            streamablehttp_client(url)
        )
        await self._bootstrap(reader, writer)

    # public API -----------------------------------------------------------------
    async def connect(self, target: str) -> None:
        parsed = urlparse(target)
        if parsed.scheme in {"http", "https"}:
            if target.rstrip("/").endswith("/sse"):
                return await self._connect_sse(target)
            if target.rstrip("/").endswith("/mcp"):
                return await self._connect_streamable(target)
            raise ValueError("Remote URL must end with /sse or /mcp")
        if target.endswith((".py", ".js")):
            return await self._connect_stdio(os.path.abspath(target))
        raise ValueError("Target must be .py/.js script or URL ending in /sse or /mcp")

    async def call_tool(self, name: str, params: Dict[str, Any]) -> None:
        if not self.session:
            raise RuntimeError("Session not initialised")
        print(f"\nCalling tool “{name}” with params {params} …")
        result = await self.session.call_tool(name, params)  
        # Handle the common result fields gracefully
        if hasattr(result, "content") and result.content:
            print("Result:", result.content[0].text)
        elif hasattr(result, "text"):
            print("Result:", result.text)
        else:
            print("Result object:", result)

    async def cleanup(self) -> None:
        await self.exit_stack.aclose()


# --------------------------------------------------------------------------- #
# Utility helpers
# --------------------------------------------------------------------------- #

def _coerce(value: str) -> Any:
    """Best-effort convert CLI strings → int / float / bool / None / str."""
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    if value.lower() in {"null", "none"}:
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if re.fullmatch(r"-?\d+\.\d*", value):
        return float(value)
    return value


def _parse_cli_params(tokens: list[str]) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    tokens come from sys.argv[2:].
    First token → tool name (if present); the rest → k=v pairs.
    """
    if not tokens:
        return None, {}
    tool = tokens[0]
    params: Dict[str, Any] = {}
    for t in tokens[1:]:
        if "=" not in t:
            raise SystemExit(f"Bad parameter '{t}'.  Use key=value format.")
        k, v = t.split("=", 1)
        params[k] = _coerce(v)
    return tool, params


# --------------------------------------------------------------------------- #
# CLI entry-point
# --------------------------------------------------------------------------- #

async def _main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target = sys.argv[1]
    tool, params = _parse_cli_params(sys.argv[2:])

    client = MCPClient()
    try:
        await client.connect(target)
        if tool:
            await client.call_tool(tool, params)
    finally:
        await client.cleanup()


if __name__ == "__main__":
    asyncio.run(_main())
