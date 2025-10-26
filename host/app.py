# host/app.py
import asyncio
import json
import sys
import traceback
import tkinter as tk
from tkinter import messagebox, ttk
from pathlib import Path

# ---- Compatibilidad Windows ----
if sys.platform.startswith("win"):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    except Exception:
        pass

# ---- MCP ----
from mcp.client.stdio import stdio_client, StdioServerParameters
from mcp.client.session import ClientSession

ROOT_DIR = Path(__file__).resolve().parents[1]
SERVER_COMMAND = sys.executable
SERVER_ARGS = ["-u", str(ROOT_DIR / "server" / "server.py")]  # -u = unbuffered

# --------------------------------------------------------------
# Normalizador robusto del resultado MCP -> dict/list/str
# --------------------------------------------------------------
def normalize_mcp_result(result):
    # Caso 0: a veces ya es un dict con {"type":"text","text":"..."}
    if isinstance(result, dict):
        # Si parece un wrapper de contenido de texto, extraemos el .text y lo parseamos
        if result.get("type") == "text" and "text" in result:
            txt = result.get("text")
            try:
                return json.loads(txt)  # intentamos parsear a list/dict
            except Exception:
                return txt  # si no es JSON válido devolvemos el texto
        # Si no es wrapper, ya es el dato "real"
        return result

    # Caso 1: si es list ya está normalizado
    if isinstance(result, list):
        return result

    # Caso 2: SDK con objetos pydantic (BaseModel) que traen .content
    content = getattr(result, "content", None)
    if content:
        for item in content:
            # --- Pydantic v2: model_dump_json() ---
            mdj = getattr(item, "model_dump_json", None)
            if callable(mdj):
                try:
                    s = mdj()
                    return json.loads(s)
                except Exception:
                    return s

            # --- Pydantic v1: json() ---
            j = getattr(item, "json", None)
            if callable(j):
                try:
                    s = j()
                    return json.loads(s)
                except Exception:
                    return s

            # --- Texto plano ---
            txt = getattr(item, "text", None)
            if txt is not None:
                try:
                    return json.loads(txt)
                except Exception:
                    return txt

            # --- Valor genérico ---
            if hasattr(item, "value"):
                val = getattr(item, "value")
                try:
                    return json.loads(val) if isinstance(val, str) else val
                except Exception:
                    return val

    # Último recurso: convertir a str e intentar json
    try:
        return json.loads(str(result))
    except Exception:
        return str(result)

    
def unwrap_text_wrapper(x):
    # Si viene como {"type":"text","text":"..."} sacamos el texto y lo parseamos
    if isinstance(x, dict) and x.get("type") == "text" and "text" in x:
        txt = x["text"]
        try:
            return json.loads(txt)  # lista/dict real
        except Exception:
            return txt              # si no es JSON válido, devolvemos texto
    return x

# --------------------------------------------------------------
# Llamada MCP
# --------------------------------------------------------------
async def mcp_call(tool_name: str, arguments: dict):
    params = StdioServerParameters(
        command=SERVER_COMMAND,
        args=SERVER_ARGS,
        cwd=str(ROOT_DIR),
        env={"PYTHONUNBUFFERED": "1"},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # (Opcional) validar tool
            try:
                tools = await session.list_tools()
                names = {t.name for t in tools}
                if tool_name not in names:
                    raise RuntimeError(f"La tool '{tool_name}' no está registrada. Tools: {sorted(names)}")
            except Exception:
                pass

            raw = await session.call_tool(tool_name, arguments)
            return normalize_mcp_result(raw)

# --------------------------------------------------------------
# GUI
# --------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MCP Weather Host")
        self.geometry("720x520")
        self.resizable(False, False)

        # Buscar
        f1 = ttk.Frame(self, padding=10); f1.pack(fill="x")
        ttk.Label(f1, text="Ciudad:").pack(side="left")
        self.entry_city = ttk.Entry(f1, width=30); self.entry_city.pack(side="left", padx=6)
        self.btn_search = ttk.Button(f1, text="Buscar", command=self.on_search); self.btn_search.pack(side="left")

        # Resultados
        f2 = ttk.Frame(self, padding=(10,0,10,10)); f2.pack(fill="both", expand=True)
        cols = ("name","country","admin1","lat","lon","tz")
        self.tree = ttk.Treeview(f2, columns=cols, show="headings", height=10)
        for c,label,w in [("name","Ciudad",140),("country","País",120),("admin1","Estado/Depto",160),
                          ("lat","Lat",80),("lon","Lon",80),("tz","Timezone",120)]:
            self.tree.heading(c, text=label); self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True)
        self.cities = []

        # Acción
        f3 = ttk.Frame(self, padding=10); f3.pack(fill="x")
        self.btn_weather = ttk.Button(f3, text="Ver clima de la ciudad seleccionada", command=self.on_get_weather)
        self.btn_weather.pack(side="left")

        # Salida
        f4 = ttk.Frame(self, padding=10); f4.pack(fill="both", expand=True)
        ttk.Label(f4, text="Salida:").pack(anchor="w")
        self.text_output = tk.Text(f4, height=10); self.text_output.pack(fill="both", expand=True)

    def set_output(self, obj):
        self.text_output.delete("1.0", "end")
        if isinstance(obj, (dict, list)):
            self.text_output.insert("end", json.dumps(obj, indent=2, ensure_ascii=False))
        else:
            self.text_output.insert("end", str(obj))

    # ---- Handlers ----
    def on_search(self):
        city = self.entry_city.get().strip()
        if not city:
            messagebox.showwarning("Atención", "Ingresá un nombre de ciudad."); return
        self.btn_search.config(state="disabled"); self.set_output("Buscando ciudades...")
        try:
            asyncio.run(self._search_async(city))
        finally:
            self.btn_search.config(state="normal")

    async def _search_async(self, city: str):
        try:
            res = await mcp_call("search_city", {"name": city, "count": 5})
            res = unwrap_text_wrapper(res)
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except Exception:
                    pass

            # res DEBE ser una lista de ciudades; si vino como str JSON, intentar parseo
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except Exception:
                    pass

            # poblar tabla
            for i in self.tree.get_children(): self.tree.delete(i)
            self.cities = []
            if isinstance(res, list):
                for item in res:
                    self.cities.append(item)
                    self.tree.insert("", "end", values=(
                        item.get("name"),
                        item.get("country"),
                        item.get("admin1"),
                        item.get("lat"),
                        item.get("lon"),
                        item.get("timezone"),
                    ))
            self.set_output(res)
        except Exception as e:
            tb = traceback.format_exc()
            messagebox.showerror("Error", f"Falló la búsqueda:\n{e}\n\nDetalle:\n{tb}")

    def on_get_weather(self):
        sel = self.tree.focus()
        if not sel:
            messagebox.showinfo("Info", "Seleccioná una ciudad de la lista."); return
        idx = self.tree.index(sel)
        if idx >= len(self.cities):
            messagebox.showerror("Error", "No se pudo resolver la ciudad seleccionada."); return
        city = self.cities[idx]; lat, lon = city.get("lat"), city.get("lon")
        if lat is None or lon is None:
            messagebox.showerror("Error", "La ciudad no trae coordenadas."); return
        self.btn_weather.config(state="disabled"); self.set_output(f"Obteniendo clima para {city.get('name')} ({lat}, {lon})...")
        try:
            asyncio.run(self._weather_async(lat, lon))
        finally:
            self.btn_weather.config(state="normal")

    async def _weather_async(self, lat: float, lon: float):
        try:
            res = await mcp_call("get_weather", {"lat": float(lat), "lon": float(lon), "timezone": "auto"})
            res = unwrap_text_wrapper(res)
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except Exception:
                    pass

            # Si vino como string JSON, parseamos
            if isinstance(res, str):
                try:
                    res = json.loads(res)
                except Exception:
                    pass
            self.set_output(res)
        except Exception as e:
            tb = traceback.format_exc()
            messagebox.showerror("Error", f"Falló la consulta de clima:\n{e}\n\nDetalle:\n{tb}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
