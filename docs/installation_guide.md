# Guía de instalación y ejecución – MCP Weather App

## 🎯 Objetivo
Esta aplicación permite consultar información meteorológica en tiempo real mediante una arquitectura **MCP (Model Context Protocol)**.  
Incluye dos componentes principales:
- **Servidor (MCP Server):** obtiene datos de clima desde la API pública de Open-Meteo.
- **Cliente (MCP Host/Client):** interfaz gráfica desarrollada con Tkinter que muestra los resultados.

---

## 🧩 Requisitos previos
1. **Python 3.11 o superior** instalado en el sistema.
2. **Conexión a Internet** (para acceder a la API pública de Open-Meteo).
3. **Sistema operativo:** Windows (probado en Windows 10 y 11).

---

## ⚙️ Configuración inicial

1) **Clonar o descargar el proyecto**
```bash
git clone https://github.com/usuario/mcp-weather-app.git
cd mcp-weather-app
```

2) **Crear entorno virtual (solo la primera vez)**
```bash
python -m venv .venv
```

3) **Activar el entorno virtual**
```bash
.venv\Scripts\activate
```

4) **Instalar dependencias**
```bash
pip install -r requirements.txt
```
El archivo `requirements.txt` incluye:
```text
fastmcp
httpx
mcp
```

---

## 🏗️ Estructura del proyecto
```text
mcp-weather-app/
│
├── host/                    → Cliente (interfaz gráfica)
│   └── app.py
│
├── server/                  → Servidor MCP (provee datos de clima)
│   └── server.py
│
├── docs/
│   └── installation_guide.md
│
├── requirements.txt
└── .gitignore
```

---

## ▶️ Ejecución

1) **Asegurarse de estar en la raíz del proyecto** y con el entorno activado:
```bash
(.venv) C:\...\mcp-weather-app>
```

2) **Iniciar la aplicación (cliente/host):**
```bash
python host/app.py
```

3) **Uso básico de la interfaz:**
- En el campo *Ciudad*, escribir por ejemplo: `Montevideo`.
- Presionar **Buscar**.
- Seleccionar la ciudad en la tabla.
- Presionar **Ver clima de la ciudad seleccionada**.

4) **La aplicación mostrará:**
- Temperatura actual.
- Velocidad y dirección del viento.
- Código del estado meteorológico.
- Vista previa de las próximas horas.

---

## 🧠 Funcionamiento interno (resumen)
- El **cliente (Host)** lanza el **servidor (Server)** como subproceso usando MCP vía **stdio**.
- El servidor expone dos herramientas (tools) MCP:
  - `search_city`: busca ciudades por nombre (usa Open-Meteo Geocoding API).
  - `get_weather`: obtiene el clima actual y un preview horario para coordenadas.
- Los datos provienen de la API pública de **Open-Meteo**.

---

## ✅ Verificación rápida

1) **Probar el servidor desde consola (opcional):**
```bash
python server/server.py test-search Montevideo
python server/server.py test-weather -34.90328 -56.18816
```
- El primer comando debe devolver una lista de coincidencias de ciudades.
- El segundo comando debe mostrar un JSON con la información actual del clima.

2) **Abrir la GUI y repetir la búsqueda desde la aplicación:**
```bash
python host/app.py
```
- Escribir **Montevideo** en el campo de búsqueda.
- Presionar **Buscar** y verificar que aparezcan las ciudades en la tabla.
- Seleccionar **Montevideo (Uruguay)**.
- Presionar **Ver clima de la ciudad seleccionada**.
- Debajo se mostrará la información meteorológica en formato JSON.

Si se muestran correctamente los resultados tanto en consola como en la interfaz, la aplicación está configurada y funcionando correctamente.


## 📦 Créditos
- Python 3.11
- Dependencias: `mcp`, `fastmcp`, `httpx`, `tkinter`
- Datos meteorológicos: Open-Meteo API (https://open-meteo.com)