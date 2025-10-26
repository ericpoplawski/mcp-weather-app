# host/llm_router.py
from __future__ import annotations
import os
import json
from typing import Optional, Tuple

import openai

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY no está definido. Esta app requiere LLM y no tiene fallbacks.")

openai.api_key = OPENAI_API_KEY

def infer_city_and_dayindex(user_text: str) -> Tuple[str, int]:
    """
    Usa LLM (function calling) para extraer ciudad e intención temporal.
    Retorna: (city:str, day_index:int) con 0=hoy/ahora, 1=mañana, 2=pasado mañana.
    Si algo no se puede determinar, lanza RuntimeError (sin fallback).
    """
    tools = [{
        "type": "function",
        "function": {
            "name": "extract_weather_query",
            "description": "Extrae ciudad e intención temporal de una consulta meteorológica en español.",
            "parameters": {
                "type": "object",
                "properties": {
                    "city":   {"type": "string", "description": "Nombre de la ciudad, ej: 'Buenos Aires'."},
                    "intent": {"type": "string", "enum": ["now", "today", "tomorrow", "day_after_tomorrow"]},
                },
                "required": ["city"]
            }
        }
    }]

    system = (
        "Eres un parser. Dado un mensaje en español sobre el clima, "
        "extrae la ciudad y cuándo se quiere el pronóstico.\n"
        "- 'ahora' o 'hoy' -> intent='today'\n"
        "- 'mañana' -> 'tomorrow'\n"
        "- 'pasado mañana' -> 'day_after_tomorrow'\n"
        "Devuelve solo la function call."
    )

    resp = openai.chat.completions.create(
        model=OPENAI_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text}
        ],
        tools=tools,
        tool_choice="auto",
        temperature=0.0,
    )
    call = resp.choices[0].message.tool_calls[0] if resp.choices[0].message.tool_calls else None
    if not call:
        raise RuntimeError("El LLM no devolvió function_call.")

    fn = call.function
    args = fn.arguments or {}
    if isinstance(args, str):
        args = json.loads(args)

    city = (args.get("city") or "").strip()
    if not city:
        raise RuntimeError("El LLM no pudo extraer la ciudad.")

    intent = (args.get("intent") or "today").strip().lower()
    if intent in ("now", "today"):
        di = 0
    elif intent == "tomorrow":
        di = 1
    elif intent == "day_after_tomorrow":
        di = 2
    else:
        raise RuntimeError(f"Intención inválida: {intent}")

    return (city, di)
