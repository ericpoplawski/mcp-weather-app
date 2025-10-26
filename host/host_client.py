# host/host_client.py
from __future__ import annotations
import json
import time
from typing import Any, Optional

from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

from logging_setup import setup_logger
log = setup_logger("host.client")

def _normalize_mcp_result(result: Any) -> Any:
    if isinstance(result, dict):
        if result.get("type") == "text" and "text" in result:
            txt = result["text"]
            try: return json.loads(txt)
            except Exception: return txt
        if "result" in result:
            return result["result"]
        if "structuredContent" in result and isinstance(result["structuredContent"], dict):
            sc = result["structuredContent"]
            if "result" in sc: return sc["result"]
        return result
    if isinstance(result, list):
        return result
    content = getattr(result, "content", None)
    if content:
        for item in content:
            txt = getattr(item, "text", None)
            if txt is not None:
                try: return json.loads(txt)
                except Exception: return txt
            if hasattr(item, "value"):
                val = getattr(item, "value")
                try: return json.loads(val) if isinstance(val, str) else val
                except Exception: return val
    try: return json.loads(str(result))
    except Exception: return str(result)

class MCPOneShotHost:
    """Cliente MCP one-shot con logging detallado."""
    def __init__(self, command: str, args: list[str], cwd: Optional[str] = None, env: Optional[dict] = None):
        self._params = StdioServerParameters(command=command, args=args, cwd=cwd, env=env or {"PYTHONUNBUFFERED":"1"})

    async def call(self, tool_name: str, arguments: dict) -> Any:
        t0 = time.perf_counter()
        async with stdio_client(self._params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                log.info(f"call_tool → {tool_name} args={arguments}")
                try:
                    raw = await session.call_tool(tool_name, arguments or {})
                    data = _normalize_mcp_result(raw)
                    dt = (time.perf_counter() - t0) * 1000
                    try:
                        log.debug(f"tool_result[{tool_name}] ms={dt:.1f} json={json.dumps(data, ensure_ascii=False)[:4000]}")
                    except Exception:
                        log.debug(f"tool_result[{tool_name}] ms={dt:.1f} repr={repr(data)[:4000]}")
                    return data
                except Exception as e:
                    dt = (time.perf_counter() - t0) * 1000
                    log.exception(f"call_tool ERROR [{tool_name}] ms={dt:.1f}: {e}")
                    raise

    async def get_resource(self, name: str) -> str:
        t0 = time.perf_counter()
        async with stdio_client(self._params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                try:
                    resources = await session.list_resources()
                    found = next((r for r in resources if r.name == name), None)
                    if not found:
                        log.info(f"resource_not_found: {name}")
                        return ""
                    content = await session.read_resource(found.uri)
                    buf = []
                    for c in content.contents:
                        txt = getattr(c, "text", None)
                        if txt is not None: buf.append(txt)
                    text = "\n".join(buf)
                    dt = (time.perf_counter() - t0) * 1000
                    log.info(f"read_resource → {name} uri={found.uri} ms={dt:.1f}")
                    log.debug(f"resource_content[{name}]: {text[:4000]}")
                    return text
                except Exception as e:
                    dt = (time.perf_counter() - t0) * 1000
                    log.exception(f"read_resource ERROR [{name}] ms={dt:.1f}: {e}")
                    return ""

    async def get_prompt(self, name: str) -> str:
        """
        Lee un prompt MCP por nombre, soportando shapes distintos de list_prompts().
        SIN fallback a estilos locales (si falla, devuelve "") — el caller decide si aborta.
        """
        t0 = time.perf_counter()
        async with stdio_client(self._params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                # Intento directo
                try:
                    prompt = await session.read_prompt(name)
                    msgs = getattr(prompt, "messages", prompt)
                    parts = []
                    for m in (msgs or []):
                        txt = getattr(m, "content", None)
                        if isinstance(txt, str):
                            parts.append(txt); continue
                        if txt is None:
                            t = getattr(m, "text", None)
                            if isinstance(t, str):
                                parts.append(t); continue
                        if isinstance(m, dict):
                            c = m.get("content") or m.get("text")
                            if isinstance(c, str):
                                parts.append(c); continue
                        if isinstance(m, (list, tuple)) and m:
                            for x in m:
                                if isinstance(x, str) and x:
                                    parts.append(x); break
                    text = "\n".join(parts)
                    dt = (time.perf_counter() - t0) * 1000
                    log.info(f"read_prompt → {name} ms={dt:.1f} (direct)")
                    log.debug(f"prompt_content[{name}]: {text[:4000]}")
                    return text
                except Exception:
                    # Fallback a list_prompts (pero no a defaults)
                    try:
                        prompts = await session.list_prompts()
                    except Exception as e_list:
                        dt = (time.perf_counter() - t0) * 1000
                        log.exception(f"list_prompts failed ms={dt:.1f}: {e_list}")
                        return ""

                    if isinstance(prompts, tuple) and len(prompts) == 1 and isinstance(prompts[0], (list, tuple, dict)):
                        prompts = prompts[0]
                    if isinstance(prompts, dict) and "prompts" in prompts and isinstance(prompts["prompts"], (list, tuple)):
                        prompts = prompts["prompts"]

                    candidates = []
                    for p in (prompts or []):
                        pname = getattr(p, "name", None)
                        if not pname and isinstance(p, dict):
                            pname = p.get("name")
                        if not pname and isinstance(p, (list, tuple)) and p and isinstance(p[0], str):
                            pname = p[0]
                        if pname:
                            candidates.append(pname)

                    if name not in candidates:
                        dt = (time.perf_counter() - t0) * 1000
                        log.info(f"prompt_not_found: {name}. disponibles={candidates} ms={dt:.1f}")
                        return ""

                    # reintento
                    try:
                        prompt = await session.read_prompt(name)
                        msgs = getattr(prompt, "messages", prompt)
                        parts = []
                        for m in (msgs or []):
                            txt = getattr(m, "content", None)
                            if isinstance(txt, str):
                                parts.append(txt); continue
                            if txt is None:
                                t = getattr(m, "text", None)
                                if isinstance(t, str):
                                    parts.append(t); continue
                            if isinstance(m, dict):
                                c = m.get("content") or m.get("text")
                                if isinstance(c, str):
                                    parts.append(c); continue
                            if isinstance(m, (list, tuple)) and m:
                                for x in m:
                                    if isinstance(x, str) and x:
                                        parts.append(x); break
                        text = "\n".join(parts)
                        dt = (time.perf_counter() - t0) * 1000
                        log.info(f"read_prompt → {name} ms={dt:.1f} (fallback)")
                        log.debug(f"prompt_content[{name}]: {text[:4000]}")
                        return text
                    except Exception as e_fallback:
                        dt = (time.perf_counter() - t0) * 1000
                        log.exception(f"read_prompt ERROR [{name}] ms={dt:.1f}: {e_fallback}")
                        return ""
