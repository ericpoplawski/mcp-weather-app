# host/app.py
import os
import sys
import re
import json
import asyncio
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

# Windows: loop policy segura para Tkinter + asyncio
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_COMMAND = sys.executable
SERVER_ARGS = ["-u", str(ROOT_DIR / "server" / "server.py")]  # -u = unbuffered

from host_client import MCPOneShotHost
from summarizer import summarize_weather

ALIASES = {
    "nyc": "New York City",
    "new york": "New York City",
    "cdmx": "Ciudad de México",
    "baires": "Buenos Aires",
}

def extract_city(user_text: str) -> str | None:
    """Heurística simple para quedarse con la ciudad del prompt."""
    if not user_text:
        return None
    t = user_text.strip()
    t = re.sub(r"[¿?!.]+$", "", t)
    low = t.lower().strip()
    if low in ALIASES:
        return ALIASES[low]
    m = re.search(r"(?:en|para|de)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ\.\-\'\s]{2,})$", t, re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        lowc = cand.lower()
        if lowc in ALIASES:
            return ALIASES[lowc]
        return cand
    if len(t.split()) <= 3:
        if low in ALIASES:
            return ALIASES[low]
        return t
    tokens = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ\.\-\']{1,}", t)
    if tokens:
        cand = tokens[-1]
        lowc = cand.lower()
        if lowc in ALIASES:
            return ALIASES[lowc]
        return cand
    return None

def intent_from_text(user_text: str) -> tuple[str, int]:
    s = (user_text or "").lower()
    if any(k in s for k in ["ahora", "en este momento", "now", "hoy"]):
        return ("now", 0)
    if "pasado mañana" in s or "day after tomorrow" in s:
        return ("day2", 2)
    if "mañana" in s or "tomorrow" in s:
        return ("tomorrow", 1)
    if "pronost" in s or "forecast" in s:
        return ("day0", 0)
    return ("day0", 0)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MCP Weather — Resumen en español")
        self.geometry("880x600")
        self.minsize(760, 520)

        self.host = MCPOneShotHost(
            command=SERVER_COMMAND,
            args=SERVER_ARGS,
            cwd=str(ROOT_DIR),
            env={"PYTHONUNBUFFERED": "1"},
        )

        # ---------- UI ----------
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=10); top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="Pregunta:").grid(row=0, column=0, padx=(0,8), sticky="w")
        self.entry_query = ttk.Entry(top); self.entry_query.grid(row=0, column=1, sticky="ew", padx=(0,8))
        self.entry_query.insert(0, "¿Cómo va a estar mañana en NYC?")

        self.btn_send  = ttk.Button(top, text="Enviar",  command=self.on_send);  self.btn_send.grid(row=0, column=2, padx=(0,6))
        self.btn_clear = ttk.Button(top, text="Limpiar", command=self.on_clear); self.btn_clear.grid(row=0, column=3)
        self.entry_query.bind("<Return>", lambda e: self.on_send())

        bottom = ttk.Frame(self, padding=(10,0,10,10)); bottom.grid(row=1, column=0, sticky="nsew")
        bottom.rowconfigure(1, weight=1); bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, text="Salida:").grid(row=0, column=0, sticky="w")
        self.text_output = tk.Text(bottom, wrap="word"); self.text_output.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(bottom, orient="vertical", command=self.text_output.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.text_output.configure(yscrollcommand=scroll.set)

        self.entry_query.focus_set()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def set_output(self, text: str):
        self.text_output.delete("1.0", "end")
        self.text_output.insert("end", text)

    def append_output(self, text: str):
        self.text_output.insert("end", text)

    def on_clear(self):
        self.entry_query.delete(0, "end")
        self.text_output.delete("1.0", "end")

    def on_send(self):
        q = self.entry_query.get().strip()
        if not q:
            messagebox.showwarning("Atención", "Escribí tu pregunta.")
            return

        self.btn_send.config(state="disabled")
        self.set_output("Pensando…\n")

        try:
            # 1) detectar ciudad + intención
            city = extract_city(q)
            if not city:
                self.append_output("No pude extraer una ciudad. Ej.: 'mañana en Montevideo'.\n")
                return
            mode, idx = intent_from_text(q)
            self.append_output(f"[Ciudad detectada] {city} — intención: {mode}\n")

            # 2) geocode → primera coincidencia (o 5 si no aparece al primer intento)
            res = asyncio.run(self.host.call("search_city", {"name": city, "count": 1}))
            if not isinstance(res, list) or not res or (isinstance(res[0], dict) and "error" in res[0]):
                res = asyncio.run(self.host.call("search_city", {"name": city, "count": 5}))

            if not isinstance(res, list) or not res:
                self.append_output("No encontré esa ciudad en la base de datos.\n")
                return

            city0 = res[0]
            lat, lon = city0.get("lat"), city0.get("lon")
            if lat is None or lon is None:
                self.append_output("La ciudad detectada no trae coordenadas válidas.\n")
                return

            # 3) tool adecuada
            style_prompt = ""
            try:
                # si existe el prompt opcional de estilo, lo usamos
                style_prompt = asyncio.run(self.host.get_resource("capabilities"))  # dummy read para iniciar
                # mejor: leer prompt si lo agregaste
                from mcp.client.stdio import stdio_client, StdioServerParameters
                from mcp.client.session import ClientSession
                # no lo usamos aquí para mantener simple; el summarizer tiene texto por defecto
                style_prompt = ""
            except Exception:
                style_prompt = ""

            if mode == "now":
                out = asyncio.run(self.host.call("get_weather", {
                    "lat": float(lat), "lon": float(lon), "timezone": "auto"
                }))
            else:
                days_needed = max(1, idx + 1)
                days_needed = min(7, days_needed if days_needed >= 2 else 2)
                out = asyncio.run(self.host.call("get_forecast_daily", {
                    "lat": float(lat), "lon": float(lon), "days": int(days_needed), "timezone": "auto"
                }))
                # marcamos el día elegido
                if isinstance(out, dict):
                    days = out.get("days") or []
                    if 0 <= idx < len(days):
                        out = {**out, "selected_day": days[idx]}

            # 4) resumen en español (LLM o fallback)
            pretty = summarize_weather(q, city0.get("name") or city, out, style_prompt or None)
            self.append_output("\n— Respuesta —\n" + pretty + "\n")
            self.append_output("\n[JSON]\n" + json.dumps(out, ensure_ascii=False, indent=2))

        except Exception as e:
            messagebox.showerror("Error", f"No se pudo resolver la consulta:\n{e}")
        finally:
            self.btn_send.config(state="normal")

    def on_close(self):
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()
