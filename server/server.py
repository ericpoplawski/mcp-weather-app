from __future__ import annotations
import asyncio
import json
import sys
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List

from fastmcp import FastMCP

# ---------- logging ----------
LOG_FILE = Path(__file__).resolve().parent / "mcp_server.log"
logger = logging.getLogger("server.mcp")
logger.setLevel(logging.DEBUG)
if not any(isinstance(h, RotatingFileHandler) for h in logger.handlers):
    fh = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(fh)

# ---------- providers ----------
from providers.geocoding_provider import GeocodingProvider
from providers.forecast_provider import ForecastProvider

geocoder = GeocodingProvider()     # timeout configurable por env GEOCODING_TIMEOUT
forecaster = ForecastProvider()    # timeout configurable por env FORECAST_TIMEOUT

app = FastMCP("weather-mcp-server")

def _safe_float(x: Any) -> float | None:
    try: return float(x)
    except Exception: return None

# ================== IMPLEMENTACIONES ==================
async def search_city_impl(name: str, count: int = 1) -> List[Dict[str, Any]]:
    logger.info(f"tool(search_city) name={name!r} count={count}")
    if not name or not name.strip():
        return []
    try:
        raw = await geocoder.search(name.strip(), count=max(1, min(int(count), 10)), language="en")
        logger.debug(f"geocoding_raw={json.dumps(raw, ensure_ascii=False)[:2000]}")
    except Exception as e:
        logger.exception(f"search_city_impl error: {e}")
        return [{"error": f"geocoding_failed: {e}"}]

    results = []
    for item in (raw.get("results") or []):
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
    logger.info(f"tool(get_weather) lat={lat} lon={lon} tz={timezone!r}")
    lat = _safe_float(lat); lon = _safe_float(lon)
    if lat is None or lon is None:
        return {"error": "invalid_coordinates"}
    try:
        raw = await forecaster.current(lat, lon, timezone=timezone or "auto")
        logger.debug(f"forecast_current_raw={json.dumps(raw, ensure_ascii=False)[:2000]}")
    except Exception as e:
        logger.exception(f"get_weather_impl error: {e}")
        return {"error": f"forecast_failed: {e}"}

    current = raw.get("current_weather") or {}
    hourly  = raw.get("hourly") or {}
    units   = raw.get("hourly_units") or {}
    return {
        "coordinates": {"lat": lat, "lon": lon},
        "timezone": raw.get("timezone"),
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
    logger.info(f"tool(get_forecast_daily) lat={lat} lon={lon} days={days} tz={timezone!r}")
    lat = _safe_float(lat); lon = _safe_float(lon)
    if lat is None or lon is None:
        return {"error": "invalid_coordinates"}
    days = max(1, min(int(days), 7))
    try:
        raw = await forecaster.daily(lat, lon, timezone=timezone or "auto")
        logger.debug(f"forecast_daily_raw={json.dumps(raw, ensure_ascii=False)[:2000]}")
    except Exception as e:
        logger.exception(f"get_forecast_daily_impl error: {e}")
        return {"error": f"forecast_failed: {e}"}

    daily = raw.get("daily") or {}
    units = raw.get("daily_units") or {}
    out = {
        "coordinates": {"lat": lat, "lon": lon},
        "timezone": raw.get("timezone"),
        "days": [],
        "units": {"tmax": units.get("temperature_2m_max", "°C"),
                  "tmin": units.get("temperature_2m_min", "°C"),
                  "precip": units.get("precipitation_sum", "mm")}
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

# ================== TOOLS MCP ==================
@app.tool(name="search_city")
async def search_city_tool(name: str, count: int = 1) -> List[Dict[str, Any]]:
    return await search_city_impl(name, count)

@app.tool(name="get_weather")
async def get_weather_tool(lat: float, lon: float, timezone: str = "auto") -> Dict[str, Any]:
    return await get_weather_impl(lat, lon, timezone)

@app.tool(name="get_forecast_daily")
async def get_forecast_daily_tool(lat: float, lon: float, days: int = 2, timezone: str = "auto") -> Dict[str, Any]:
    return await get_forecast_daily_impl(lat, lon, days, timezone)

# ================== PROMPT (se mantiene para demo) ==================
@app.prompt(name="es_summary_style")
async def es_summary_style() -> str:
    return (
        "Redacta en español claro y conciso. "
        "Incluye temperatura máxima y mínima en pronóstico diario; si es tiempo real, temperatura y viento. "
        "Usa unidades del JSON. No inventes datos ni agregues lugares comunes."
    )

# ================== MAIN ==================
def run_stdio_blocking() -> None:
    if sys.platform.startswith("win"):
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        except Exception:
            pass
    logger.info("Starting MCP server (stdio)")
    app.run(transport="stdio")

if __name__ == "__main__":
    run_stdio_blocking()
