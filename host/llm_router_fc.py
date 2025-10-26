# host/host_client.py
from __future__ import annotations
import json
from typing import Any, Optional

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession


def _normalize_mcp_result(result: Any) -> Any:
    """
    Intenta sacar el dato “real” de distintas formas que devuelve el SDK:
    - dict {"type":"text","text":"..."} -> parsea JSON si aplica
    - objetos con .content, .structuredContent, .structured_content, .result
    - listas ya normalizadas
    - último recurso: str -> intentar json.loads
    """
    # 1) Casos dict directos
    if isinstance(result, dict):
        if result.get("type") == "text" and "text" in result:
            txt = result["text"]
            try:
                return json.loads(txt)
            except Exception:
                return txt
        # Si trae un 'result' anidado (wrapper)
        if "result" in result and isinstance(result["result"], (dict, list, str)):
            try:
                if isinstance(result["result"], str):
                    return json.loads(result["result"])
                return result["result"]
            except Exception:
                return result["result"]
        # Si trae 'structuredContent'
        if "structuredContent" in result and isinstance(result["structuredContent"], dict):
            sc = result["structuredContent"]
            if "result" in sc:
                return sc["result"]
        if "structured_content" in result and isinstance(result["structured_content"], dict):
            sc = result["structured_content"]
            if "result" in sc:
                return sc["result"]
        return result

    # 2) List ya normalizada
    if isinstance(result, list):
        return result

    # 3) Objetos estilo pydantic con varios atributos posibles
    # 3a) .structuredContent / .structured_content
    sc = getattr(result, "structuredContent", None) or getattr(result, "structured_content", None)
    if isinstance(sc, dict) and "result" in sc:
        return sc["result"]

    # 3b) .result directo
    res = getattr(result, "result", None)
    if res is not None:
        return res

    # 3c) .content (array de bloques text/json)
    content = getattr(result, "content", None)
    if content and isinstance(content, (list, tuple)):
        for item in content:
            # pydantic v2: model_dump_json()
            mdj = getattr(item, "model_dump_json", None)
            if callable(mdj):
                try:
                    s = mdj()
                    return json.loads(s)
                except Exception:
                    return s
            # pydantic v1: json()
            j = getattr(item, "json", None)
            if callable(j):
                try:
                    s = j()
                    return json.loads(s)
                except Exception:
                    return s
            # texto plano
            txt = getattr(item, "text", None)
            if txt is not None:
                try:
                    return json.loads(txt)
                except Exception:
                    return txt
            # valor genérico
            if hasattr(item, "value"):
                val = getattr(item, "value")
                try:
                    return json.loads(val) if isinstance(val, str) else val
                except Exception:
                    return val

    # 4) Último recurso: str(result) → intentar json
    try:
        return json.loads(str(result))
    except Exception:
        return str(result)


class MCPOneShotHost:
    """Cliente MCP one-shot con poda de argumentos desconocidos."""
    def __init__(self, command: str, args: list[str], cwd: Optional[str] = None, env: Optional[dict] = None):
        self._params = StdioServerParameters(command=command, args=args, cwd=cwd, env=env or {"PYTHONUNBUFFERED":"1"})

    async def call_compat(self, tool_name: str, arguments: dict) -> Any:
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

    async def get_prompt(self, name: str) -> str:
        async with stdio_client(self._params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                try:
                    prompts = await session.list_prompts()
                    found = next((p for p in prompts if p.name == name), None)
                    if not found:
                        return ""
                    prompt = await session.read_prompt(found.name)
                    parts = []
                    for m in prompt.messages:
                        txt = getattr(m, "content", "")
                        if isinstance(txt, str):
                            parts.append(txt)
                        else:
                            t = getattr(txt, "text", None)
                            if t:
                                parts.append(t)
                    return "\n".join(parts) if parts else ""
                except Exception:
                    return ""
