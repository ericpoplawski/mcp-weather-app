# host/app.py
import os
import sys
import re
import json
import asyncio
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

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
    # sacar signos finales
    t = re.sub(r"[¿?!.]+$", "", t)
    # alias exactos
    low = t.lower().strip()
    if low in ALIASES:
        return ALIASES[low]

    # buscar después de "en|para|de"
    m = re.search(r"(?:en|para|de)\s+([A-Za-zÁÉÍÓÚÜÑáéíóúüñ\.\-\'\s]{2,})$", t, re.IGNORECASE)
    if m:
        cand = m.group(1).strip()
        # normalizar alias finales (ej: "... en NYC")
        lowc = cand.lower()
        if lowc in ALIASES:
            return ALIASES[lowc]
        return cand

    # fallback: si el texto es corto, tratarlo como ciudad
    if len(t.split()) <= 3:
        if low in ALIASES:
            return ALIASES[low]
        return t

    # último intento: tomar la última "palabra capitalizada" larga
    tokens = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ][A-Za-zÁÉÍÓÚÜÑáéíóúüñ\.\-\']{1,}", t)
    if tokens:
        cand = tokens[-1]
        lowc = cand.lower()
        if lowc in ALIASES:
            return ALIASES[lowc]
        return cand
    return None


def intent_from_text(user_text: str) -> tuple[str, int]:
    """
    Devuelve ('now'|'tomorrow'|'dayN', day_index)
    - ahora/hoy -> ('now', 0) → get_weather
    - mañana   -> ('tomorrow', 1) → get_forecast_daily (days>=2, idx=1)
    - pasado mañana -> ('day2', 2)
    por defecto: ('day0', 0) → get_forecast_daily (hoy)
    """
    s = (user_text or "").lower()
    if any(k in s for k in ["ahora", "en este momento", "now", "hoy"]):
        return ("now", 0)
    if "pasado mañana" in s or "day after tomorrow" in s:
        return ("day2", 2)
    if "mañana" in s or "tomorrow" in s:
        return ("tomorrow", 1)
    # palabras tipo "pronóstico"
    if "pronost" in s or "forecast" in s:
        return ("day0", 0)
    # default
    return ("day0", 0)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MCP Weather — Simple Router")
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

    # ---------- helpers ----------
    def set_output(self, text: str):
        self.text_output.delete("1.0", "end")
        self.text_output.insert("end", text)

    def append_output(self, text: str):
        self.text_output.insert("end", text)

    # ---------- acciones ----------
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
            # 1) Extraer ciudad del prompt
            city = extract_city(q)
            if not city:
                self.append_output("No pude extraer una ciudad de tu mensaje. Ej.: 'mañana en Montevideo'.\n")
                return

            self.append_output(f"[Ciudad detectada] {city}\n")

            # 2) Decodificar a coords con search_city (count=1; si vacío, count=5)
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

            self.append_output(f"[Match] {city0.get('name')}, {city0.get('admin1') or ''} {city0.get('country') or ''} "
                               f"({lat}, {lon})\n")

            # 3) Elegir tool según intención
            mode, idx = intent_from_text(q)
            if mode == "now":
                out = asyncio.run(self.host.call("get_weather", {
                    "lat": float(lat), "lon": float(lon), "timezone": "auto"
                }))
                # Redacción simple
                cur = (out or {}).get("current") or {}
                tz  = (out or {}).get("timezone")
                line = (f"Ahora en {city0.get('name')} (TZ: {tz}): "
                        f"{cur.get('temperature')}°C, viento {cur.get('windspeed')} km/h, "
                        f"código {cur.get('weathercode')}.\n")
                self.append_output("\n— Respuesta —\n" + line)
                self.append_output("\n[JSON]\n" + json.dumps(out, ensure_ascii=False, indent=2))
                return

            # forecast diario (hoy/mañana/pasado)
            days_needed = max(1, idx + 1)
            days_needed = min(7, days_needed if days_needed >= 2 else 2)  # si idx=0, pedimos 2 igual
            out = asyncio.run(self.host.call("get_forecast_daily", {
                "lat": float(lat), "lon": float(lon), "days": int(days_needed), "timezone": "auto"
            }))
            days = (out or {}).get("days") or []
            picked = days[idx] if 0 <= idx < len(days) else (days[0] if days else None)
            if not picked:
                self.append_output("\nNo pude obtener el día solicitado.\n")
                self.append_output("\n[JSON]\n" + json.dumps(out, ensure_ascii=False, indent=2))
                return

            units = (out or {}).get("units") or {}
            line = (f"Pronóstico para {city0.get('name')} el {picked.get('date')}: "
                    f"máx {picked.get('tmax')}{units.get('tmax','°C')}, "
                    f"mín {picked.get('tmin')}{units.get('tmin','°C')}, "
                    f"precip {picked.get('precipitation_sum')}{units.get('precip','mm')}, "
                    f"código {picked.get('weathercode')}.\n")

            self.append_output("\n— Respuesta —\n" + line)
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
