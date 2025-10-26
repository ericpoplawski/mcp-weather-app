# host/host_client.py
from __future__ import annotations
import json
from typing import Any, Optional

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession


def _normalize_mcp_result(result: Any) -> Any:
    # dict wrapper de texto
    if isinstance(result, dict):
        if result.get("type") == "text" and "text" in result:
            txt = result["text"]
            try:
                return json.loads(txt)
            except Exception:
                return txt
        # si trae 'result' o 'structuredContent'
        if "result" in result:
            return result["result"]
        if "structuredContent" in result and isinstance(result["structuredContent"], dict):
            sc = result["structuredContent"]
            if "result" in sc:
                return sc["result"]
        return result
    # lista ya normalizada
    if isinstance(result, list):
        return result
    # objetos con .content
    content = getattr(result, "content", None)
    if content:
        for item in content:
            txt = getattr(item, "text", None)
            if txt is not None:
                try:
                    return json.loads(txt)
                except Exception:
                    return txt
            if hasattr(item, "value"):
                val = getattr(item, "value")
                try:
                    return json.loads(val) if isinstance(val, str) else val
                except Exception:
                    return val
    # str → intentar json
    try:
        return json.loads(str(result))
    except Exception:
        return str(result)


class MCPOneShotHost:
    """Cliente MCP one-shot: abre/cierra el server por stdio en cada llamada."""
    def __init__(self, command: str, args: list[str], cwd: Optional[str] = None, env: Optional[dict] = None):
        self._params = StdioServerParameters(command=command, args=args, cwd=cwd, env=env or {"PYTHONUNBUFFERED":"1"})

    async def call(self, tool_name: str, arguments: dict) -> Any:
        async with stdio_client(self._params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                raw = await session.call_tool(tool_name, arguments or {})
                return _normalize_mcp_result(raw)

    async def get_resource(self, name: str) -> str:
        async with stdio_client(self._params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                try:
                    resources = await session.list_resources()
                    found = next((r for r in resources if r.name == name), None)
                    if not found:
                        return ""
                    content = await session.read_resource(found.uri)
                    for c in content.contents:
                        txt = getattr(c, "text", None)
                        if txt is not None:
                            return txt
                except Exception:
                    return ""
                return ""
