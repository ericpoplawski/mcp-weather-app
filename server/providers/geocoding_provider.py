from __future__ import annotations
from typing import Any, Dict
import os
import json
import logging
import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

# ---------- logging a consola ----------
_LOG_LEVEL = os.getenv("PROVIDER_LOG_LEVEL", "INFO").upper()
_LOG_TRUNC = int(os.getenv("PROVIDER_LOG_TRUNC", "1200"))

logger = logging.getLogger("provider.geocoding")
# Evitar duplicados si el server reimporta
if not logger.handlers:
    ch = logging.StreamHandler()
    ch.setLevel(_LOG_LEVEL)
    ch.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    logger.addHandler(ch)
logger.setLevel(_LOG_LEVEL)
logger.propagate = False  # para que no lo capture otro handler y se duplique

class GeocodingProvider:
    """Cliente simple para Open-Meteo Geocoding API (solo búsqueda)."""

    def __init__(self, timeout: float | None = None):
        env_timeout = os.getenv("GEOCODING_TIMEOUT")
        if timeout is None and env_timeout:
            try:
                timeout = float(env_timeout)
            except Exception:
                timeout = 10.0
        self._timeout = timeout if timeout is not None else 10.0

    async def search(self, name: str, count: int = 5, *, language: str = "en") -> Dict[str, Any]:
        params = {
            "name": name,
            "count": max(1, min(int(count), 10)),
            "language": language,
            "format": "json",
        }
        logger.info(f"[geocoding] GET {GEOCODING_URL} params={params}")

        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(GEOCODING_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        # preview JSON (truncado)
        try:
            preview = json.dumps(data, ensure_ascii=False)
        except Exception:
            preview = repr(data)
        if len(preview) > _LOG_TRUNC:
            preview = preview[:_LOG_TRUNC] + "... [truncated]"
        logger.debug(f"[geocoding] response={preview}")

        return data
