import sys
import asyncio
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

if sys.platform.startswith("win"):
    try:
        import asyncio as _asyncio
        _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_COMMAND = sys.executable
SERVER_ARGS = ["-u", str(ROOT_DIR / "server" / "server.py")]  # -u = unbuffered

from host_client import MCPOneShotHost
from services.summarizer import summarize_weather
from services.logging_setup import setup_logger
from services.llm_router import infer_city_and_dayindex

log = setup_logger("host.app")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MCP Weather App")
        self.geometry("600x200")
        self.minsize(500, 200)

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
        self.entry_query.insert(0, "En montevideo como está el clima?")

        self.btn_send  = ttk.Button(top, text="Enviar",  command=self.on_send);  self.btn_send.grid(row=0, column=2, padx=(0,6))
        self.btn_clear = ttk.Button(top, text="Limpiar", command=self.on_clear); self.btn_clear.grid(row=0, column=3)
        self.entry_query.bind("<Return>", lambda e: self.on_send())

        bottom = ttk.Frame(self, padding=(10,0,10,10)); bottom.grid(row=1, column=0, sticky="nsew")
        bottom.rowconfigure(1, weight=1); bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, text="Pronóstico:").grid(row=0, column=0, sticky="w")
        self.text_output = tk.Text(bottom, wrap="word"); self.text_output.grid(row=1, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(bottom, orient="vertical", command=self.text_output.yview)
        scroll.grid(row=1, column=1, sticky="ns")
        self.text_output.configure(yscrollcommand=scroll.set)

        self.entry_query.focus_set()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # helpers
    def set_output(self, text: str):
        self.text_output.delete("1.0", "end")
        self.text_output.insert("end", text)

    def append_output(self, text: str):
        self.text_output.insert("end", text)

    def on_clear(self):
        self.entry_query.delete(0, "end")
        self.text_output.delete(1.0, "end")


    def on_send(self):
        q = self.entry_query.get().strip()
        if not q:
            messagebox.showwarning("Atención", "Escribí tu pregunta.")
            return

        self.btn_send.config(state="disabled")
        self.set_output("Pensando…\n")
        log.info(f"user_query: {q}")

        try:
            # 0) prompt de estilo del server
            style_prompt = asyncio.run(self.host.get_prompt("es_summary_style"))
            if style_prompt:
                log.info("prompt_used: es_summary_style")

            # 1) LLM: ciudad + day_index
            city, day_index = infer_city_and_dayindex(q)
            log.info(f"llm_extracted city={city} day_index={day_index}")


            # 2) geocode via MCP (pedimos hasta 10 coincidencias)
            res = asyncio.run(self.host.call("search_city", {"name": city, "count": 10}))
            if not isinstance(res, list) or not res or (isinstance(res[0], dict) and "error" in res[0]):
                raise RuntimeError(f"No se encontró la ciudad '{city}' en geocodificación.")

            # Si hay más de una coincidencia, mostrar selección
            pick = None
            if len(res) == 1:
                pick = res[0]
            else:
                # Mostrar ventana de selección
                options = []
                for i, item in enumerate(res):
                    name = item.get("name", "?")
                    admin1 = item.get("admin1", "")
                    country = item.get("country", "")
                    options.append(f"{name} ({admin1}, {country})")

                def select_city():
                    idx = lb.curselection()
                    if not idx:
                        messagebox.showwarning("Atención", "Seleccioná una ciudad de la lista.")
                        return
                    nonlocal pick
                    pick = res[idx[0]]
                    sel_win.destroy()

                sel_win = tk.Toplevel(self)
                sel_win.title("Selecciona la ciudad")
                sel_win.geometry("400x300")
                tk.Label(sel_win, text="Selecciona la ciudad correcta:").pack(pady=8)
                lb = tk.Listbox(sel_win, height=min(10, len(options)), selectmode=tk.SINGLE)
                for opt in options:
                    lb.insert(tk.END, opt)
                lb.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)
                btn = tk.Button(sel_win, text="Elegir", command=select_city)
                btn.pack(pady=8)
                sel_win.transient(self)
                sel_win.grab_set()
                self.wait_window(sel_win)
                if pick is None:
                    self.set_output("No se seleccionó ninguna ciudad.\n")
                    return

            lat, lon = pick.get("lat"), pick.get("lon")
            if lat is None or lon is None:
                raise RuntimeError("La ciudad detectada no trae coordenadas válidas.")
            log.info(f"city_match: name={pick.get('name')} admin1={pick.get('admin1')} country={pick.get('country')} lat={lat} lon={lon}")

            # 3) Elegir la tool según day_index
            if day_index == 0:
                out = asyncio.run(self.host.call("get_weather", {
                    "lat": float(lat), "lon": float(lon), "timezone": "auto"
                }))
                data_for_summary = out
            else:
                days_needed = max(1, day_index + 1)
                days_needed = min(7, days_needed if days_needed >= 2 else 2)
                out = asyncio.run(self.host.call("get_forecast_daily", {
                    "lat": float(lat), "lon": float(lon), "days": int(days_needed), "timezone": "auto"
                }))
                # marcar el día elegido para el summarizer (sin fallback si no está)
                days = (out or {}).get("days") or []
                if not (0 <= day_index < len(days)):
                    raise RuntimeError("El pronóstico no contiene el día solicitado por el LLM.")
                data_for_summary = {**out, "selected_day": days[day_index]}

            # 4) Redacción con LLM
            pretty = summarize_weather(q, pick.get("name") or city, data_for_summary, style_prompt or None)
            self.append_output("\n— Respuesta —\n" + pretty + "\n")

        except Exception as e:
            log.exception(f"Unhandled error in on_send: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            self.btn_send.config(state="normal")

    def on_close(self):
        self.destroy()

if __name__ == "__main__":
    app = App()
    app.mainloop()
