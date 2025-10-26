# server/providers/forecast_provider.py
from __future__ import annotations
from typing import Any, Dict
import os
import json
import logging
import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# ---------- logging a consola ----------
_LOG_LEVEL = os.getenv("PROVIDER_LOG_LEVEL", "INFO").upper()
_LOG_TRUNC = int(os.getenv("PROVIDER_LOG_TRUNC", "1200"))

logger = logging.getLogger("provider.forecast")
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(_LOG_LEVEL)
    ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(ch)
logger.setLevel(_LOG_LEVEL)
logger.propagate = False

class ForecastProvider:
    """Cliente simple para Open-Meteo Forecast API (current y daily)."""

    def __init__(self, timeout: float | None = None):
        env_timeout = os.getenv("FORECAST_TIMEOUT")
        if timeout is None and env_timeout:
            try:
                timeout = float(env_timeout)
            except Exception:
                timeout = 10.0
        self._timeout = timeout if timeout is not None else 10.0

    async def current(self, lat: float, lon: float, *, timezone: str = "auto") -> Dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": "true",
            "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m",
            "timezone": timezone or "auto",
        }
        logger.info(f"[forecast/current] GET {FORECAST_URL} params={params}")

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(FORECAST_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        try:
            preview = json.dumps(data, ensure_ascii=False)
        except Exception:
            preview = repr(data)
        if len(preview) > _LOG_TRUNC:
            preview = preview[:_LOG_TRUNC] + "... [truncated]"
        logger.info(f"[forecast/current] response={preview}")

        return data

    async def daily(self, lat: float, lon: float, *, timezone: str = "auto") -> Dict[str, Any]:
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "weathercode,temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": timezone or "auto",
        }
        logger.info(f"[forecast/daily] GET {FORECAST_URL} params={params}")

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(FORECAST_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        try:
            preview = json.dumps(data, ensure_ascii=False)
        except Exception:
            preview = repr(data)
        if len(preview) > _LOG_TRUNC:
            preview = preview[:_LOG_TRUNC] + "... [truncated]"
        logger.debug(f"[forecast/daily] response={preview}")

        return data
