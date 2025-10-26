# server/server.py
from __future__ import annotations
import asyncio
import json
import sys
import traceback
from typing import Any, Dict, List
from pathlib import Path

import httpx
from fastmcp import FastMCP

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

app = FastMCP("weather-mcp-server")
LOG_FILE = Path(__file__).resolve().parent / "mcp_server_error.log"

def _safe_float(x: Any) -> float | None:
    try:
        return float(x)
    except Exception:
        return None

# ================== IMPLEMENTACIONES (para CLI y tools) ==================
async def search_city_impl(name: str, count: int = 5) -> List[Dict[str, Any]]:
    if not name or not name.strip():
        return []
    count = max(1, min(int(count), 10))
    params = {"name": name.strip(), "count": count, "language": "en", "format": "json"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(GEOCODING_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    results = []
    for item in data.get("results", []) or []:
        results.append(
            {
                "name": item.get("name"),
                "country": item.get("country"),
                "admin1": item.get("admin1"),
                "lat": _safe_float(item.get("latitude")),
                "lon": _safe_float(item.get("longitude")),
                "timezone": item.get("timezone"),
            }
        )
    return results

async def get_weather_impl(lat: float, lon: float, timezone: str = "auto") -> Dict[str, Any]:
    lat = _safe_float(lat); lon = _safe_float(lon)
    if lat is None or lon is None:
        return {"error": "Invalid coordinates"}
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "timezone": timezone or "auto",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(FORECAST_URL, params=params)
        resp.raise_for_status()
        data = resp.json()
    current = data.get("current_weather") or {}
    hourly = data.get("hourly") or {}
    units = data.get("hourly_units") or {}
    return {
        "coordinates": {"lat": lat, "lon": lon},
        "timezone": data.get("timezone"),
        "current": {
            "time": current.get("time"),
            "temperature": current.get("temperature"),
            "windspeed": current.get("windspeed"),
            "winddirection": current.get("winddirection"),
            "weathercode": current.get("weathercode"),
        },
        "hourly_preview": {
            "time": (hourly.get("time") or [])[:6],
            "temperature_2m": (hourly.get("temperature_2m") or [])[:6],
            "relative_humidity_2m": (hourly.get("relative_humidity_2m") or [])[:6],
            "wind_speed_10m": (hourly.get("wind_speed_10m") or [])[:6],
            "units": {
                "temperature_2m": units.get("temperature_2m", "°C"),
                "relative_humidity_2m": units.get("relative_humidity_2m", "%"),
                "wind_speed_10m": units.get("wind_speed_10m", "km/h"),
            },
        },
    }

# ================== REGISTRO DE TOOLS MCP ==================
@app.tool(name="search_city")
async def search_city_tool(name: str, count: int = 5) -> List[Dict[str, Any]]:
    return await search_city_impl(name, count)

@app.tool(name="get_weather")
async def get_weather_tool(lat: float, lon: float, timezone: str = "auto") -> Dict[str, Any]:
    return await get_weather_impl(lat, lon, timezone)

# ================== ENTRADAS ==================
def run_stdio_blocking() -> None:
    """Arranca el servidor MCP por stdio (fastmcp.run elige el transporte)."""
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    # fastmcp usa .run() (no existe run_stdio en tu versión)
    app.run()

async def _cli_test_search(q: str) -> None:
    res = await search_city_impl(q)
    print(json.dumps(res, indent=2, ensure_ascii=False))

async def _cli_test_weather(lat: float, lon: float) -> None:
    res = await get_weather_impl(lat, lon)
    print(json.dumps(res, indent=2, ensure_ascii=False))

def _print_help() -> None:
    print(
        "Usage:\n"
        "  python server.py               # run as MCP stdio server\n"
        "  python server.py test-search <city>\n"
        "  python server.py test-weather <lat> <lon>\n"
    )

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # stdio mode
        run_stdio_blocking()
    else:
        cmd = sys.argv[1]
        if cmd == "test-search" and len(sys.argv) >= 3:
            asyncio.run(_cli_test_search(" ".join(sys.argv[2:])))
        elif cmd == "test-weather" and len(sys.argv) == 4:
            asyncio.run(_cli_test_weather(float(sys.argv[2]), float(sys.argv[3])))
        else:
            _print_help()
