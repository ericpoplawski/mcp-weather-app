# host/summarizer.py
from __future__ import annotations
import os
import json
from typing import Any

import openai

_openai_key = os.getenv("OPENAI_API_KEY", "")
if _openai_key:
    openai.api_key = _openai_key

# Mapeo básico WMO para mejorar el fallback
WMO = {
    0: "Cielo despejado",
    1: "Mayormente despejado",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Niebla",
    48: "Niebla con escarcha",
    51: "Llovizna débil",
    53: "Llovizna",
    55: "Llovizna intensa",
    61: "Lluvia débil",
    63: "Lluvia",
    65: "Lluvia intensa",
    71: "Nieve débil",
    73: "Nieve",
    75: "Nieve intensa",
    80: "Chubascos débiles",
    81: "Chubascos",
    82: "Chubascos fuertes",
    95: "Tormenta",
    96: "Tormenta con granizo",
    99: "Tormenta con granizo fuerte",
}

def _fallback_spanish_text(user_query: str, city_name: str, data: Any) -> str:
    """Si no hay LLM, armamos un texto claro con los datos que tenemos."""
    if not isinstance(data, dict):
        return f"No pude formatear la respuesta. Datos: {data}"
    tz = data.get("timezone") or ""
    cur = data.get("current") or {}
    if cur:
        code = cur.get("weathercode")
        desc = WMO.get(code, f"Código {code}")
        return (
            f"Ahora en {city_name} (TZ {tz}): {cur.get('temperature')}°C, "
            f"viento {cur.get('windspeed')} km/h. Condición: {desc}."
        )
    days = data.get("days") or []
    sel = data.get("selected_day") or (days[0] if days else None)
    units = data.get("units") or {}
    if sel:
        code = sel.get("weathercode")
        desc = WMO.get(code, f"Código {code}")
        return (
            f"Pronóstico para {city_name} el {sel.get('date')}: "
            f"máx {sel.get('tmax')}{units.get('tmax','°C')}, "
            f"mín {sel.get('tmin')}{units.get('tmin','°C')}, "
            f"precip {sel.get('precipitation_sum')}{units.get('precip','mm')}. "
            f"Condición: {desc}."
        )
    return f"No encontré valores para redactar. JSON: {json.dumps(data, ensure_ascii=False)[:400]}"

def summarize_weather(user_query: str, city_name: str, data: Any, style_prompt: str | None = None) -> str:
    """Devuelve un párrafo en español. Usa OpenAI si hay API key; si no, fallback."""
    if not _openai_key:
        return _fallback_spanish_text(user_query, city_name, data)

    system = style_prompt or (
        "Redacta en español claro y conciso un breve reporte del clima. "
        "Incluye temperatura máxima y mínima si hay pronóstico diario, o temperatura actual y viento si es tiempo real. "
        "No inventes datos; usa solo los del JSON."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": f"Pregunta del usuario: {user_query}\n\nCiudad: {city_name}\n\nJSON:\n{json.dumps(data, ensure_ascii=False)}"}
    ]
    resp = openai.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        messages=messages,
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()
