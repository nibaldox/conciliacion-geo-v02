# Bundle Portable Multiplataforma con Electron

**Fecha:** 2026-06-07
**Estado:** Diseño propuesto, pendiente de revisión del usuario
**Reemplaza:** `2026-06-07-portable-pyz-bundle-design.md` (descartado — el
usuario prefirió el feel de app nativa por sobre el minimalismo de un solo
`.exe`)

## Objetivo

Empaquetar la aplicación actual (frontend React + backend FastAPI) como una
**app de escritorio nativa** que el usuario pueda copiar a una PC de trabajo
con restricciones (sin admin, sin instalador, sin Python) y ejecutar con un
doble click. La ventana debe verse como una app nativa, **no como un
browser abierto a localhost** — esa fue la decisión del usuario al elegir
Electron por sobre PyInstaller.

UX de referencia: la app de escritorio de Slack, Discord, VS Code — ventana
nativa con chrome del sistema operativo, sin barra de URL, sin botón "atrás"
del browser.

Soportado en v1: **Windows + Linux**.

## Fuera de alcance (v1)

- **macOS** — sin firma de código la UX es muy mala (cuarentena de Gatekeeper).
  Revisar si en el futuro se justifica el Apple Developer Program (USD 99/año).
- **Auto-actualización** — el usuario descarga un nuevo artifact y reemplaza el
  binario manualmente.
- **Firma de código en Windows** — certificado EV cuesta USD 300-500/año. El
  clic en SmartScreen ("Más info" → "Ejecutar de todas formas") es aceptable
  para una herramienta interna.
- **Portabilizar la UI legacy de Streamlit** — `CONTRIBUTING.md` lo prohíbe;
  solo se empaqueta la UI React nueva.
- **Integración con el sistema operativo** (bandeja, diálogos nativos de
  archivo, notificaciones nativas, etc.) — no es necesario para el caso de
  uso. Se puede agregar en v2 si hace falta.
- **Soporte de ARM** — solo x86_64 en v1. ARM se puede agregar al matrix
  cuando haya demanda real.

## Arquitectura

```
┌──────────────────────────────────────────────────────────────┐
│  conciliacion.exe  (Electron, ~150-200 MB)                    │
│                                                               │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Proceso main de Electron (Node.js)                  │   │
│  │  - Crea la ventana nativa con chrome del SO          │   │
│  │  - Lanza el sidecar de Python al arrancar            │   │
│  │  - Monitorea el health del backend                   │   │
│  │  - Mata al sidecar cuando se cierra la ventana       │   │
│  │  - Maneja un único instance lock (puerto)            │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                    │
│                          ▼ HTTP loadURL                       │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Proceso renderer de Electron (Chromium)             │   │
│  │  - Carga el build estático de React                  │   │
│  │  - Sin barra de URL, sin botón atrás                 │   │
│  │  - Llama a la API en localhost:57890                 │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                    │
│                          ▼ spawn (child_process)             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  conciliacion-api  (sidecar Python, ~120 MB)         │   │
│  │  - PyInstaller --onefile con FastAPI + deps          │   │
│  │  - uvicorn en 127.0.0.1:57890                        │   │
│  │  - Sirve el build de React estáticamente en /        │   │
│  └──────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

Tres procesos vivos (main, renderer, sidecar Python) pero el usuario solo ve
**una ventana nativa**. Toda la coordinación pasa por el proceso main.

## Forma del bundle (post-build)

Después de construir y comprimir, el usuario descarga uno de:

```
conciliacion-portable-windows.zip
├── conciliacion.exe              # shell de Electron
└── resources/
    ├── conciliacion-api.exe      # sidecar Python
    ├── ...                       # otros assets de Electron
    └── locales/                  # archivos de idioma, ícono, etc.

conciliacion-portable-linux.AppImage
# AppImage auto-contenido, ejecutable con chmod +x
```

Después del primer arranque, la app crea (y reutiliza en arranques
posteriores) el directorio de datos por S.O.:

**Windows** (`%APPDATA%/conciliacion/`):
```
%APPDATA%/conciliacion/
├── conciliacion.db               # SQLite (sesiones, mallas, resultados)
├── conciliacion.db-wal           # journal de WAL
├── conciliacion.db-shm
├── logs/
│   └── conciliacion.log          # uvicorn + logs de la app
└── uploads/                      # STL/DXF subidos por el usuario
```

**Linux** (`$XDG_DATA_HOME/conciliacion/` o
`~/.local/share/conciliacion/`):
```
~/.local/share/conciliacion/
├── conciliacion.db
├── conciliacion.db-wal
├── conciliacion.db-shm
├── logs/
│   └── conciliacion.log
└── uploads/
```

Mantener los datos del usuario fuera del binario permite mover el bundle o
actualizarlo sin perder sesiones, mallas, ni resultados.

## Cambios al código

### 1. `entry_api.py` (nuevo, raíz del repo)

Entry point del **sidecar de Python** (lo que se compila con PyInstaller).
Responsabilidades:

- Detectar el S.O. y resolver el directorio de datos:
  - **Windows**: `%APPDATA%/conciliacion/`
  - **Linux**: `$XDG_DATA_HOME/conciliacion/` (con fallback a
    `~/.local/share/conciliacion/`)
  - **macOS**: `RuntimeError("Plataforma no soportada")` — falla rápido si
    alguien corre el binario equivocado
  - Detección con `sys.platform`
- Setear `CONCILIACION_DATA_DIR` y `DATABASE_URL` **antes** de importar
  `api.database` (ese módulo lee `DB_PATH` al importarse)
- Configurar logging a un archivo bajo `data_dir/logs/`
- Montar `web/dist/` (extraído por PyInstaller bajo `sys._MEIPASS`) como
  `StaticFiles(html=True)` en `/` sobre la app de FastAPI
- Correr `uvicorn.run(app, host="127.0.0.1", port=57890, log_config=None)`
  en el hilo principal

No necesita auto-open del browser ni guard de instancia única — esas
responsabilidades son del proceso main de Electron.

### 2. `conciliacion-api.spec` (nuevo, raíz del repo)

Spec de PyInstaller para el sidecar. Flags clave:

- `datas=[('web/dist', 'web/dist')]` — empaquetar el build de React
- `hiddenimports=[...]` — forzar inclusión de módulos con carga perezosa
- `--collect-all scipy --collect-all shapely --collect-all trimesh
  --collect-all numpy` — estos paquetes tienen imports dinámicos que
  PyInstaller no detecta estáticamente
- `excludes=['tkinter', 'pytest', 'matplotlib.tests', 'IPython', 'notebook']`
  — mantener el bundle chico
- `console=False` — sin ventana de consola parpadeando (los logs van al
  archivo)
- Nombre del output:
  - Windows: `conciliacion-api.exe`
  - Linux: `conciliacion-api` (sin extensión)

### 3. `electron/` (nuevo, raíz del repo)

Proyecto Electron propiamente dicho. Estructura:

```
electron/
├── package.json             # deps de Electron + electron-builder
├── main.js                  # proceso main: ventana + spawn sidecar + cleanup
├── preload.js               # expone APIs seguras al renderer (contextBridge)
├── assets/
│   ├── icon.png             # ícono placeholder (512x512)
│   ├── icon.ico             # ícono Windows
│   └── icon-linux.png       # ícono Linux
└── builder.config.js        # config de electron-builder (o en package.json)
```

**`main.js`** (esquema):

```js
const { app, BrowserWindow } = require('electron');
const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const fs = require('fs');

let pythonProcess = null;
let mainWindow = null;

function getSidecarPath() {
  // electron-builder pone los sidecars bajo resources/ en producción
  const name = process.platform === 'win32'
    ? 'conciliacion-api.exe'
    : 'conciliacion-api';
  return path.join(process.resourcesPath, name);
}

function waitForApi(port, timeoutMs = 10000) {
  // polea http://localhost:PORT/api/v1/health hasta 200 o timeout
  // ...
}

function startApi() {
  const sidecar = getSidecarPath();
  pythonProcess = spawn(sidecar, [], {
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  // logs del sidecar → archivo en %APPDATA%/~/.local/share
  // ...
}

app.whenReady().then(async () => {
  // pre-flight: si el puerto 57890 ya está en uso, mostrar error y salir
  startApi();
  await waitForApi(57890);

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 768,
    title: 'Conciliación Geotécnica',
    icon: path.join(__dirname, 'assets/icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.setMenuBarVisibility(false);  // opcional: sin menú nativo
  await mainWindow.loadURL('http://localhost:57890');
});

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
  }
  app.quit();
});
```

### 4. `api/main.py` (modificación aditiva)

Después de incluir los routers, montar el build de React en `/` si la
carpeta existe:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

_web_dist = Path(__file__).parent.parent / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")
```

`html=True` hace que `StaticFiles` sirva `index.html` para rutas de
directorio, que es lo que el SPA de React necesita para el routing del
lado del cliente. El check sobre `_web_dist.exists()` no rompe el dev
workflow (donde la build de React puede o no existir según si el dev
ejecutó `npm run build`).

### 5. `api/database.py` (modificación de 1 línea)

Hoy hardcodea:

```python
DB_PATH = Path(__file__).parent.parent / "data" / "conciliacion.db"
```

Cambiar a honrar `CONCILIACION_DATA_DIR` (que ya existe como env var en
`core/config.py:DeployDefaults:94`):

```python
import os
_DATA_DIR = Path(os.environ.get(
    "CONCILIACION_DATA_DIR",
    Path(__file__).parent.parent / "data"
))
DB_PATH = _DATA_DIR / "conciliacion.db"
```

El default preserva el comportamiento actual para dev / Render / Streamlit.
El entry del sidecar setea la env var antes de importar, así que la build
portable usa `%APPDATA%` o `~/.local/share/`.

### 6. `.github/workflows/build-portable.yml` (nuevo)

Trigger manual (`workflow_dispatch`) en v1. Matrix sobre
`windows-latest` y `ubuntu-latest`. Pasos por entrada del matrix:

1. Checkout
2. `actions/setup-python@v5` (Python 3.12, cache de pip)
3. `actions/setup-node@v4` (Node 20, cache de npm)
4. `pip install -r requirements-api.txt pyinstaller`
5. `npm ci` (en `web/`)
6. `npm run build` (en `web/`, con `VITE_API_URL=/api/v1` para que la
   build use paths relativos y funcione tanto en dev como en el bundle)
7. `pyinstaller --clean --noconfirm conciliacion-api.spec`
8. `npm ci` (en `electron/`) e `npm run build` (que ejecuta
   `electron-builder`)
9. Empaquetar el output de electron-builder:
   - **Windows**: `Compress-Archive` del directorio `.exe-win32-x64/` →
     `conciliacion-portable-windows.zip`
   - **Linux**: el `electron-builder` ya produce un `.AppImage`
     directamente como target; se renombra y se sube como artifact
10. `actions/upload-artifact@v4` con nombre por S.O.

Tiempos de build (cold cache): ~10-15 min por entrada del matrix. Con
cache: ~4-6 min. El matrix corre en paralelo.

### 7. `docs/PORTABLE.md` (nuevo)

Guía para el usuario final. Contenido:

- Qué trae cada `.zip` / `.AppImage`
- **Windows**: doble click en `conciliacion.exe`; SmartScreen → "Más info"
  → "Ejecutar de todas formas"
- **Linux**: `chmod +x conciliacion.AppImage && ./conciliacion.AppImage`.
  Documentar el caso de FUSE faltante (algunos Linux requieren
  `apt install libfuse2`)
- Dónde queda la data (rutas por S.O. arriba)
- Cómo ver los logs (el archivo en la carpeta de datos)
- Cómo actualizar (descargar el nuevo artifact y reemplazar el binario;
  la data se preserva)
- Limitaciones conocidas: sin auto-update, puerto 57890 debe estar libre,
  una sola instancia permitida

## Decisiones técnicas

| Tema | Decisión | Razón |
|---|---|---|
| Framework | Electron | Pedido explícito del usuario (feel nativo) |
| Empaquetador Electron | electron-builder | Mejor soporte de sidecars, más maduro que electron-forge |
| Sidecar de Python | PyInstaller --onefile | Un solo binario, electron-builder lo maneja de forma estándar |
| Carga del React build | Desde el sidecar Python en `http://localhost:57890` | Mismo origen que la API, sin CORS; Electron solo aporta la ventana nativa |
| Puerto del API | `57890` (fijo) | Evita configuración runtime; documento como limitación |
| Ventana default | 1280x800, min 1024x768 | Cómodo para el wizard; no permite layouts rotos |
| Menú nativo | Oculto en v1 | El usuario no lo pidió; se puede agregar en v2 |
| Icono | Placeholder (asset propio) | Necesario para electron-builder; se puede mejorar después |
| Build CI | GitHub Actions matrix | Ya hay runners para ambos S.O. |
| Formato Windows | `.zip` con `.exe` portable | Evita NSIS installer (que necesita admin para instalar) |
| Formato Linux | `.AppImage` | Estándar de facto para portable en Linux; auto-monta con FUSE |
| Code signing | No en v1 | Documentar el clic de SmartScreen |

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Impacto | Mitigación |
|---|---|---|---|
| PyInstaller no bundle bien scipy | Alta (conocido) | Build roto | `--collect-all scipy --collect-all numpy` + hidden imports |
| PyInstaller no bundle bien shapely | Alta (conocido) | Build roto | `--collect-all shapely` + hidden import de `shapely.geometry` |
| Antivirus marca el `.exe` | Media | Fricción del usuario | Documentar el clic de SmartScreen; bundle sin firma |
| Tamaño del bundle ~300 MB | Cierta | Peso del artifact | Aceptable; documentar |
| Cold start 3-5s del sidecar | Media | UX menor | Aceptable; el splash de Electron lo disimula |
| Puerto 57890 ya en uso | Baja | La app no arranca | Pre-flight en `main.js`: intentar `bind()` al puerto, si falla mostrar error y salir |
| Múltiples instancias | Baja | Corrupción de datos | Mismo pre-flight: el segundo `main.js` detecta el puerto ocupado y sale |
| Assets de Cesium (~22 MB) inflan el bundle | Cierta | Tamaño +200 MB | Aceptable; Cesium es necesario para la vista 3D. En v2 se podría cargar lazy |
| Tamaño del build de React (~25-30 MB) | Cierta | Tamaño | Aceptable; inevitable para el SPA |
| SmartScreen marca el `.exe` | Alta (esperable) | Fricción inicial | Documentar el flujo "Más info" → "Ejecutar de todas formas" |
| **Linux**: FUSE no instalado | Media | AppImage no se ejecuta | Documentar `apt install libfuse2` (Ubuntu 22.04+) o `dpkg --add-architecture i386 && apt install libfuse2` (Ubuntu 24.04) |
| **Linux**: AppImage no es ejecutable después de descargar | Alta | El doble click no funciona | Documentar `chmod +x conciliacion.AppImage` |
| **Linux**: distros con glibc < 2.35 | Baja | El sidecar Python no arranca | Documentar el requisito de glibc 2.35+ (Ubuntu 22.04+, Debian 12+, Fedora 36+) |
| **Electron**: procesos zombies si Electron crashea sin disparar `window-all-closed` | Baja | El sidecar queda corriendo | El `main.js` debe registrar handler de `before-quit` que mate al child explícitamente |

## Criterios de aceptación

- [ ] Se suben dos artifacts desde GitHub Actions:
      `conciliacion-portable-windows.zip` y `conciliacion-portable-linux.AppImage`
- [ ] **Windows**: el `.zip` extraído en una VM limpia con Windows 10/11 y sin
      Python instalado arranca con doble click
- [ ] **Linux**: el `.AppImage` en una VM limpia con Ubuntu 22.04+ y sin
      Python instalado arranca con `chmod +x && ./conciliacion.AppImage`
- [ ] La ventana se ve como una app nativa: chrome del S.O., título
      "Conciliación Geotécnica", sin barra de URL
- [ ] Subir un STL, definir una sección, procesar y exportar Excel funciona
      end-to-end en ambos S.O.
- [ ] Reiniciar la app preserva los datos del SQLite (sesiones, mallas)
- [ ] Cerrar la ventana mata al sidecar Python (no quedan procesos zombies)
- [ ] El visor 3D de Cesium carga correctamente
- [ ] Abrir dos veces la app: la segunda detecta el puerto ocupado y sale
      con un mensaje claro en el log
- [ ] El antivirus no marca el `.exe` (o un falso positivo conocido está
      documentado en `PORTABLE.md`)

## Archivos tocados (resumen)

| Archivo | Acción | Por qué |
|---|---|---|
| `entry_api.py` | nuevo | Entry point de PyInstaller para el sidecar |
| `conciliacion-api.spec` | nuevo | Spec de PyInstaller para el sidecar |
| `electron/main.js` | nuevo | Proceso main de Electron |
| `electron/preload.js` | nuevo | Bridge seguro al renderer |
| `electron/package.json` | nuevo | Deps de Electron + scripts de build |
| `electron/assets/*` | nuevo | Iconos placeholder |
| `api/database.py` | modificar (1 línea) | Honra `CONCILIACION_DATA_DIR` |
| `api/main.py` | modificar (aditivo) | Mount de `web/dist/` en `/` si existe |
| `.github/workflows/build-portable.yml` | nuevo | Matrix build por S.O. |
| `docs/PORTABLE.md` | nuevo | Guía del usuario final |
| `web/src/api/client.ts` | sin cambios | Ya soporta `VITE_API_URL` relativo |
| `core/`, `web/`, etc. | sin cambios | No se tocan |

## Preguntas abiertas

Ninguna. Todas las decisiones tienen default razonable; el usuario aprobó
la dirección de Electron por sobre PyInstaller. Pendiente: revisión del
spec por el usuario antes de pasar al plan de implementación.
