# server/server.py
from __future__ import annotations
import asyncio
import json
import sys
from typing import Any, Dict, List

import httpx
from fastmcp import FastMCP

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL  = "https://api.open-meteo.com/v1/forecast"

app = FastMCP("weather-mcp-server")


def _safe_float(x: Any) -> float | None:
    try:
        return float(x)
    except Exception:
        return None


# ================ IMPLEMENTACIONES ================
async def search_city_impl(name: str, count: int = 1) -> List[Dict[str, Any]]:
    """Decodifica nombre de ciudad → [ {name,country,admin1,lat,lon,timezone,population?} ]"""
    if not name or not name.strip():
        return []
    count = max(1, min(int(count), 10))
    params = {"name": name.strip(), "count": count, "language": "en", "format": "json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(GEOCODING_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return [{"error": f"geocoding_failed: {e}"}]

    results = []
    for item in data.get("results", []) or []:
        results.append({
            "name": item.get("name"),
            "country": item.get("country"),
            "admin1": item.get("admin1"),
            "lat": _safe_float(item.get("latitude")),
            "lon": _safe_float(item.get("longitude")),
            "timezone": item.get("timezone"),
            "population": item.get("population"),
        })
    return results


async def get_weather_impl(lat: float, lon: float, timezone: str = "auto") -> Dict[str, Any]:
    """Clima actual + preview de horas."""
    lat = _safe_float(lat); lon = _safe_float(lon)
    if lat is None or lon is None:
        return {"error": "invalid_coordinates"}
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": "true",
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
        "timezone": timezone or "auto",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(FORECAST_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {"error": f"forecast_failed: {e}"}

    current = data.get("current_weather") or {}
    hourly  = data.get("hourly") or {}
    units   = data.get("hourly_units") or {}

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


async def get_forecast_daily_impl(lat: float, lon: float, days: int = 2, timezone: str = "auto") -> Dict[str, Any]:
    """Pronóstico diario (tmax/tmin, precipitación, weathercode)."""
    lat = _safe_float(lat); lon = _safe_float(lon)
    if lat is None or lon is None:
        return {"error": "invalid_coordinates"}
    days = max(1, min(int(days), 7))

    params = {
        "latitude": lat,
        "longitude": lon,
        "timezone": timezone or "auto",
        "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(FORECAST_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {"error": f"forecast_failed: {e}"}

    daily = data.get("daily") or {}
    units = data.get("daily_units") or {}
    out = {
        "coordinates": {"lat": lat, "lon": lon},
        "timezone": data.get("timezone"),
        "days": [],
        "units": {
            "tmax": units.get("temperature_2m_max", "°C"),
            "tmin": units.get("temperature_2m_min", "°C"),
            "precip": units.get("precipitation_sum", "mm"),
        }
    }
    times = (daily.get("time") or [])[:days]
    tmaxs = (daily.get("temperature_2m_max") or [])[:days]
    tmins = (daily.get("temperature_2m_min") or [])[:days]
    precs = (daily.get("precipitation_sum") or [])[:days]
    codes = (daily.get("weathercode") or [])[:days]
    for i, dt in enumerate(times):
        out["days"].append({
            "date": dt,
            "tmax": tmaxs[i] if i < len(tmaxs) else None,
            "tmin": tmins[i] if i < len(tmins) else None,
            "precipitation_sum": precs[i] if i < len(precs) else None,
            "weathercode": codes[i] if i < len(codes) else None,
        })
    return out


# ================ TOOLS MCP ================
@app.tool(name="search_city")
async def search_city_tool(name: str, count: int = 1) -> List[Dict[str, Any]]:
    return await search_city_impl(name, count)

@app.tool(name="get_weather")
async def get_weather_tool(lat: float, lon: float, timezone: str = "auto") -> Dict[str, Any]:
    return await get_weather_impl(lat, lon, timezone)

@app.tool(name="get_forecast_daily")
async def get_forecast_daily_tool(lat: float, lon: float, days: int = 2, timezone: str = "auto") -> Dict[str, Any]:
    return await get_forecast_daily_impl(lat, lon, days, timezone)


# ================ RESOURCE (opcional) ================
@app.resource("memory://capabilities", name="capabilities", mime_type="application/json")
async def capabilities_resource() -> str:
    spec = {
        "tools": {
            "search_city": {"args": {"name": "str", "count": "int<=10"}},
            "get_weather": {"args": {"lat": "float", "lon": "float", "timezone": "str|'auto'"}},
            "get_forecast_daily": {"args": {"lat": "float", "lon": "float", "days": "1..7", "timezone": "str|'auto'"}},
        }
    }
    return json.dumps(spec, ensure_ascii=False, indent=2)


# ================ PROMPT (opcional para estilo) ================
@app.prompt(name="es_summary_style")
async def es_summary_style() -> str:
    return (
        "Redacta en español claro y conciso. Explica temperatura máxima y mínima, probables precipitaciones y viento si aplica. "
        "No inventes datos; usa solo los del JSON."
    )


# ================ MAIN ================
def run_stdio_blocking() -> None:
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    app.run(transport="stdio")

if __name__ == "__main__":
    run_stdio_blocking()
