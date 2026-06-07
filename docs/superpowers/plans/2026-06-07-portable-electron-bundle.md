# Plan de Implementación: Bundle Portable con Electron

> **Para workers agénticos:** SUB-SKILL REQUERIDO: Usar `superpowers:subagent-driven-development` (recomendado) o `superpowers:executing-plans` para implementar este plan task por task. Los pasos usan sintaxis de checkbox (`- [ ]`) para tracking.

**Goal:** Empaquetar la app Conciliación Geotécnica (React + FastAPI) como una app de escritorio nativa para Windows y Linux, sin instalación, sin admin, con feel nativo (ventana con chrome del SO).

**Architecture:** Electron como shell nativo lanza un sidecar de Python (PyInstaller --onefile) que sirve FastAPI + el build de React estáticamente en `http://localhost:57890`. El proceso main de Electron hace pre-flight del puerto, espera el health check, abre la ventana nativa, y mata al sidecar al cerrar. Build vía GitHub Actions matrix (windows-latest + ubuntu-latest).

**Tech Stack:** Python 3.12, FastAPI, uvicorn, PyInstaller 6.x, Electron 32.x, electron-builder 25.x, GitHub Actions, Node 20.

---

## File Structure

Archivos que se crean o modifican en este plan:

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `api/database.py` | modificar | Honrar `CONCILIACION_DATA_DIR` env var (1 línea) |
| `api/main.py` | modificar | Mount de `web/dist/` en `/` (aditivo) |
| `entry_api.py` | crear | Entry point de PyInstaller para el sidecar |
| `conciliacion-api.spec` | crear | Spec de PyInstaller con `--collect-all` para scipy/shapely/trimesh |
| `tests/test_database_env.py` | crear | Test que `DB_PATH` respeta `CONCILIACION_DATA_DIR` |
| `tests/test_api_static_mount.py` | crear | Test que `web/dist/` se monta cuando existe |
| `tests/test_entry_api.py` | crear | Test de `resolve_data_dir()` por S.O. |
| `electron/package.json` | crear | Deps de Electron + electron-builder + scripts |
| `electron/main.js` | crear | Proceso main: ventana, spawn sidecar, cleanup |
| `electron/preload.js` | crear | Bridge seguro al renderer (contextBridge) |
| `electron/lib/port.js` | crear | Pre-flight del puerto (testable, sin Electron deps) |
| `electron/lib/port.test.js` | crear | Test del pre-flight con `node:test` |
| `electron/lib/health.js` | crear | Espera el health check del sidecar (testable) |
| `electron/lib/health.test.js` | crear | Test del health waiter |
| `electron/builder.config.js` | crear | Config de electron-builder (targets Windows + Linux) |
| `electron/assets/icon.png` | crear | Ícono placeholder (512x512) |
| `electron/assets/icon.ico` | crear | Ícono Windows |
| `electron/assets/icon-linux.png` | crear | Ícono Linux |
| `.github/workflows/build-portable.yml` | crear | Matrix build (windows-latest + ubuntu-latest) |
| `docs/PORTABLE.md` | crear | Guía del usuario final |
| `.gitignore` | modificar | Ignorar `dist/`, `build/` (artefactos de PyInstaller/Electron) |

Reglas de descomposición:
- `electron/lib/` agrupa lógica que se puede testear sin levantar Electron
- `entry_api.py` agrupa la lógica de bootstrap del sidecar en un solo archivo
- El spec de PyInstaller y la config de electron-builder se mantienen como
  archivos separados (son configs declarativas, no código)

---

## Task 1: `api/database.py` honra `CONCILIACION_DATA_DIR`

**Files:**
- Modify: `api/database.py:14`
- Create: `tests/test_database_env.py`

- [ ] **Step 1.1: Escribir el test que falla**

Crear `tests/test_database_env.py`:

```python
"""Tests for api/database.py honoring CONCILIACION_DATA_DIR env var."""
import importlib
import os
import tempfile
from pathlib import Path


def test_db_path_uses_default_when_env_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("CONCILIACION_DATA_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    # Reimport to pick up the env state
    if "api.database" in __import__("sys").modules:
        del __import__("sys").modules["api.database"]
    from api import database
    # Default is <repo>/data relative to the package
    assert database.DB_PATH.name == "conciliacion.db"
    assert database.DB_PATH.parent.name == "data"


def test_db_path_uses_env_var_when_set(monkeypatch, tmp_path):
    custom = tmp_path / "custom_data"
    monkeypatch.setenv("CONCILIACION_DATA_DIR", str(custom))
    if "api.database" in __import__("sys").modules:
        del __import__("sys").modules["api.database"]
    from api import database
    assert database.DB_PATH == custom / "conciliacion.db"
```

- [ ] **Step 1.2: Correr el test, ver que falla**

Run: `pytest tests/test_database_env.py -v`
Expected: FAIL — `DB_PATH` todavía está hardcodeado y no respeta la env var.

- [ ] **Step 1.3: Modificar `api/database.py`**

En `api/database.py:14`, reemplazar la línea actual:

```python
DB_PATH = Path(__file__).parent.parent / "data" / "conciliacion.db"
```

por:

```python
_DATA_DIR = Path(
    os.environ.get(
        "CONCILIACION_DATA_DIR",
        Path(__file__).parent.parent / "data",
    )
)
DB_PATH = _DATA_DIR / "conciliacion.db"
```

`os` ya está importado en la línea 5. No se necesita agregar imports.

- [ ] **Step 1.4: Correr el test, ver que pasa**

Run: `pytest tests/test_database_env.py -v`
Expected: PASS (2 tests).

- [ ] **Step 1.5: Commit**

```bash
git add api/database.py tests/test_database_env.py
git commit -m "feat(api): honor CONCILIACION_DATA_DIR env var for portable data dir"
```

---

## Task 2: `api/main.py` monta `web/dist/` en `/`

**Files:**
- Modify: `api/main.py` (después de los routers, antes del bloque de routers)
- Create: `tests/test_api_static_mount.py`

- [ ] **Step 2.1: Escribir el test que falla**

Crear `tests/test_api_static_mount.py`:

```python
"""Tests for api/main.py static mount of web/dist/ at /."""
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_static_mount_present_when_web_dist_exists(monkeypatch, tmp_path):
    # Crear un web/dist con un index.html y un asset
    web_dist = tmp_path / "web" / "dist"
    web_dist.mkdir(parents=True)
    (web_dist / "index.html").write_text("<html><body>hi</body></html>")

    # Cambiar CWD a tmp_path para que api/main.py encuentre web/dist ahí
    monkeypatch.chdir(tmp_path)
    # Necesitamos recargar el módulo
    import importlib
    import api.main
    importlib.reload(api.main)
    from api.main import app
    client = TestClient(app)
    r = client.get("/")
    assert r.status_code == 200
    assert "hi" in r.text


def test_static_mount_absent_when_web_dist_missing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # No hay web/dist acá
    import importlib
    import api.main
    importlib.reload(api.main)
    from api.main import app
    client = TestClient(app)
    r = client.get("/")
    # Sin web/dist, no hay ruta en /; la API no tiene GET /, así que 404
    assert r.status_code in (404, 405)
```

- [ ] **Step 2.2: Correr el test, ver que falla**

Run: `pytest tests/test_api_static_mount.py -v`
Expected: FAIL — el primer test falla porque `web/dist` no se monta todavía.

- [ ] **Step 2.3: Modificar `api/main.py`**

Al final de `api/main.py`, después de los routers (después de la línea `app.include_router(ai.router, prefix="/api/v1")`), agregar:

```python
# ---------------------------------------------------------------------------
# Static mount: serve the React build at / when web/dist/ exists.
# This is the "portable" mode (Electron + sidecar) where the same process
# serves both the API and the SPA. Dev workflow (Vite on :5173) is
# unaffected because the React dev server runs separately.
# ---------------------------------------------------------------------------

from pathlib import Path
from fastapi.staticfiles import StaticFiles

_web_dist = Path(__file__).parent.parent / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")
```

Nota: los `from ... import ...` van al final del archivo para que no se
importen al cargar el módulo antes de que `app` exista. (Los routers
incluidos arriba ya usan `app`, así que el orden es: definir `app`,
incluir routers, montar static.)

- [ ] **Step 2.4: Correr el test, ver que pasa**

Run: `pytest tests/test_api_static_mount.py -v`
Expected: PASS (2 tests).

- [ ] **Step 2.5: Verificar que los demás tests siguen pasando**

Run: `pytest tests/ -v --tb=short`
Expected: todos los tests existentes siguen pasando (puede haber
warnings sobre reload del módulo, son aceptables).

- [ ] **Step 2.6: Commit**

```bash
git add api/main.py tests/test_api_static_mount.py
git commit -m "feat(api): mount web/dist/ at / for portable SPA serving"
```

---

## Task 3: `entry_api.py` con resolución de directorio de datos

**Files:**
- Create: `entry_api.py`
- Create: `tests/test_entry_api.py`

- [ ] **Step 3.1: Escribir el test que falla**

Crear `tests/test_entry_api.py`:

```python
"""Tests for entry_api.resolve_data_dir() — pure platform/IO logic only."""
import sys
from pathlib import Path

import pytest


def test_resolve_data_dir_linux_with_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    # Import fresh
    if "entry_api" in sys.modules:
        del sys.modules["entry_api"]
    import entry_api
    result = entry_api.resolve_data_dir()
    assert result == tmp_path / "conciliacion"


def test_resolve_data_dir_linux_without_xdg(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    # Patch Path.home to return tmp_path
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    if "entry_api" in sys.modules:
        del sys.modules["entry_api"]
    import entry_api
    result = entry_api.resolve_data_dir()
    assert result == tmp_path / ".local" / "share" / "conciliacion"


def test_resolve_data_dir_windows(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    if "entry_api" in sys.modules:
        del sys.modules["entry_api"]
    import entry_api
    result = entry_api.resolve_data_dir()
    assert result == tmp_path / "conciliacion"


def test_resolve_data_dir_unsupported_platform(monkeypatch):
    monkeypatch.setattr("sys.platform", "darwin")
    if "entry_api" in sys.modules:
        del sys.modules["entry_api"]
    import entry_api
    with pytest.raises(RuntimeError, match="Plataforma no soportada"):
        entry_api.resolve_data_dir()
```

- [ ] **Step 3.2: Correr el test, ver que falla**

Run: `pytest tests/test_entry_api.py -v`
Expected: FAIL — `entry_api` no existe todavía (ModuleNotFoundError).

- [ ] **Step 3.3: Crear `entry_api.py` con `resolve_data_dir()` y bootstrap mínimo**

Crear `entry_api.py` en la raíz del repo:

```python
"""Entry point for the PyInstaller-bundled Python sidecar.

Launches uvicorn with the FastAPI app from api.main. The Electron main
process spawns this binary and talks to it over http://127.0.0.1:57890.

Environment variables set BEFORE importing api.database:
- CONCILIACION_DATA_DIR: directory for SQLite + logs + uploads
- DATABASE_URL: sqlite:///<data_dir>/conciliacion.db
"""

import logging
import os
import sys
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def resolve_data_dir() -> Path:
    """Resolve the per-OS data directory for the portable build.

    Windows: %APPDATA%/conciliacion/
    Linux:   $XDG_DATA_HOME/conciliacion/  (or ~/.local/share/conciliacion/)

    Raises:
        RuntimeError: if running on an unsupported platform.
    """
    if sys.platform == "win32":
        base = Path(
            os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
        )
    elif sys.platform.startswith("linux"):
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    else:
        raise RuntimeError(f"Plataforma no soportada: {sys.platform}")
    return base / "conciliacion"


def configure_data_dir() -> Path:
    """Resolve the data dir, create it, and export the relevant env vars.

    Returns:
        The data directory path.
    """
    data_dir = resolve_data_dir()
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "logs").mkdir(exist_ok=True)
    (data_dir / "uploads").mkdir(exist_ok=True)
    os.environ["CONCILIACION_DATA_DIR"] = str(data_dir)
    os.environ["DATABASE_URL"] = f"sqlite:///{data_dir}/conciliacion.db"
    return data_dir


def configure_logging(log_file: Path) -> None:
    """Send logs to a file under the data dir."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_file),
        level=logging.INFO,
        format=LOG_FORMAT,
    )


def main() -> None:
    data_dir = configure_data_dir()
    configure_logging(data_dir / "logs" / "conciliacion.log")

    import uvicorn  # imported here so logging is configured first
    from api.main import app

    uvicorn.run(app, host="127.0.0.1", port=57890, log_config=None)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3.4: Correr el test, ver que pasa**

Run: `pytest tests/test_entry_api.py -v`
Expected: PASS (4 tests).

- [ ] **Step 3.5: Commit**

```bash
git add entry_api.py tests/test_entry_api.py
git commit -m "feat(sidecar): entry_api.py with per-OS data dir resolution"
```

---

## Task 4: `conciliacion-api.spec` (PyInstaller spec)

**Files:**
- Create: `conciliacion-api.spec`

Esta task no tiene test unitario — el "test" es el build en sí, que
sucede en Task 5.

- [x] **Step 4.1: Crear el spec de PyInstaller**

Crear `conciliacion-api.spec` en la raíz del repo:

```python
# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the Python sidecar binary.

Build:
    pyinstaller --clean --noconfirm conciliacion-api.spec

Produces:
    Windows: dist/conciliacion-api.exe
    Linux:   dist/conciliacion-api
"""

block_cipher = None

datas = [
    ('web/dist', 'web/dist'),
]

hiddenimports = [
    'scipy._lib.misc',
    'scipy.special._cdflib',
    'scipy.integrate._quadpack',
    'scipy.integrate._odepack',
    'scipy.optimize._minpack',
    'shapely.geometry',
    'trimesh',
    'pandas',
    'openpyxl',
    'ezdxf',
]

excludes = [
    'tkinter',
    'pytest',
    'matplotlib.tests',
    'IPython',
    'notebook',
    'PIL',
    'PyQt5',
    'PySide2',
]

a = Analysis(
    ['entry_api.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='conciliacion-api',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
```

- [x] **Step 4.2: Commit** (SHA: 71a81cc)

```bash
git add conciliacion-api.spec
git commit -m "feat(sidecar): PyInstaller spec for the Python sidecar binary"
```

---

## Task 5: Smoke test del sidecar en Linux (dev local)

Esta task valida que el spec de PyInstaller produce un binario funcional.
Solo se puede correr en el dev local (Linux). El build de Windows se
valida vía CI en Task 11.

**Files:** ninguno (validación manual)

- [x] **Step 5.1: Asegurarse de que el build de React existe**

Run: `cd web && npm run build && cd ..`
Expected: el directorio `web/dist/` se crea con `index.html` adentro.

Si `web/dist/` ya existe de una build anterior, podés saltar este paso.

- [x] **Step 5.2: Instalar PyInstaller**

Run: `pip install pyinstaller`
Expected: instalación exitosa.

- [x] **Step 5.3: Correr PyInstaller**

Run: `pyinstaller --clean --noconfirm conciliacion-api.spec`
Expected: el comando termina con `Building EXE from EXE-00.toc completed
successfully.` y se crea `dist/conciliacion-api`.

Si falla con errores tipo `ModuleNotFoundError: No module named 'X'`,
agregar `'X'` a `hiddenimports` en el spec y reintentar.

- [x] **Step 5.4: Arrancar el sidecar y validar**

Run (en una terminal): `./dist/conciliacion-api`

En otra terminal, validar:

```bash
curl -s http://localhost:57890/api/v1/health
# Expected: {"status":"ok","version":"2.0.0"}

curl -s http://localhost:57890/ | head -5
# Expected: contenido HTML del index.html de React
```

Si ambos retornan lo esperado, el sidecar funciona. Matar el proceso con
Ctrl+C en la primera terminal.

- [x] **Step 5.5: Verificar dónde quedó la DB**

Run: `ls ~/.local/share/conciliacion/`
Expected: `conciliacion.db`, `conciliacion.db-wal`, `conciliacion.db-shm`,
`logs/`, `uploads/`.

- [x] **Step 5.6: Limpiar el artefacto de build local**

Run: `rm -rf dist/ build/`
Expected: los directorios `dist/` y `build/` (de PyInstaller) se eliminan.
No commitear estos directorios (se agregan al `.gitignore` en Task 10).

- [x] **Step 5.7: No commit — esta task no genera código nuevo**

Si hubo ajustes al spec en 5.3, volver a Task 4, ajustar, re-correr, y
commitear con `--amend` o un commit nuevo.

---

## Task 6: Set up del proyecto Electron

**Files:**
- Create: `electron/package.json`
- Modify: `.gitignore` (ignorar `electron/node_modules/`, `electron/dist/`)

- [ ] **Step 6.1: Crear `electron/package.json`**

Crear `electron/package.json`:

```json
{
  "name": "conciliacion-electron",
  "version": "0.1.0",
  "private": true,
  "description": "Electron shell for Conciliación Geotécnica portable bundle",
  "main": "main.js",
  "scripts": {
    "dev": "electron .",
    "build": "electron-builder --config builder.config.js",
    "build:linux": "electron-builder --linux --config builder.config.js",
    "build:windows": "electron-builder --win --config builder.config.js",
    "test": "node --test lib/"
  },
  "devDependencies": {
    "electron": "^32.0.0",
    "electron-builder": "^25.0.0"
  }
}
```

- [ ] **Step 6.2: Instalar deps**

Run: `cd electron && npm install && cd ..`
Expected: `electron/node_modules/` se crea con electron + electron-builder
instalados. Descarga ~150 MB.

- [ ] **Step 6.3: Modificar `.gitignore`**

Agregar al final de `.gitignore`:

```
# Electron build artifacts
electron/node_modules/
electron/dist/
```

- [ ] **Step 6.4: Commit**

```bash
git add electron/package.json .gitignore
git commit -m "feat(electron): scaffold electron/ project with electron-builder"
```

---

## Task 7: Íconos placeholder para Electron

**Files:**
- Create: `electron/assets/icon.png`
- Create: `electron/assets/icon.ico`
- Create: `electron/assets/icon-linux.png`

Los íconos placeholder son PNGs planos. Para v1, podés generarlos
fácilmente con cualquier editor de imágenes o con un comando de
ImageMagick.

- [ ] **Step 7.1: Generar ícono placeholder (PNG 512x512)**

Si tenés ImageMagick instalado:

Run: `convert -size 512x512 xc:'#1e40af' -fill white -gravity center -pointsize 80 -annotate 0 'CG' electron/assets/icon.png`

Si no, generá un PNG 512x512 de cualquier color sólido con un texto o
símbolo distintivo y guardalo en `electron/assets/icon.png`.

- [ ] **Step 7.2: Convertir a .ico (Windows)**

Run: `convert electron/assets/icon.png -define icon:auto-resize=256,128,96,64,48,32,16 electron/assets/icon.ico`

Si ImageMagick no soporta la conversión, podés usar `png2ico` o
`electron-icon-builder` (que se invoca desde electron-builder).
Alternativa rápida: usar un PNG 256x256 con la mayoría de herramientas
de íconos online, o saltarte este paso y dejar que electron-builder
genere uno default (con warning).

- [ ] **Step 7.3: Copiar a `icon-linux.png`**

Run: `cp electron/assets/icon.png electron/assets/icon-linux.png`
Expected: el mismo PNG está disponible como `icon-linux.png`.

- [ ] **Step 7.4: Commit**

```bash
git add electron/assets/
git commit -m "feat(electron): placeholder icons (PNG/ICO/Linux)"
```

---

## Task 8: `electron/lib/port.js` (pre-flight del puerto, testeable)

**Files:**
- Create: `electron/lib/port.js`
- Create: `electron/lib/port.test.js`

Esta lógica se extrae del main process para poder testearla sin
levantar Electron.

- [x] **Step 8.1: Escribir el test que falla**

Crear `electron/lib/port.test.js`:

```javascript
const test = require('node:test');
const assert = require('node:assert');
const net = require('node:net');
const { isPortInUse, findFreePort } = require('./port');

test('isPortInUse returns false for a free port', async () => {
  const free = await findFreePort();
  const inUse = await isPortInUse(free);
  assert.strictEqual(inUse, false);
});

test('isPortInUse returns true for a busy port', async () => {
  const port = await findFreePort();
  const server = net.createServer();
  await new Promise((resolve) => server.listen(port, '127.0.0.1', resolve));
  try {
    const inUse = await isPortInUse(port);
    assert.strictEqual(inUse, true);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('findFreePort returns a port in the valid range', async () => {
  const port = await findFreePort();
  assert.ok(port >= 1024 && port <= 65535, `Port ${port} out of range`);
});
```

- [x] **Step 8.2: Correr el test, ver que falla**

Run: `cd electron && npm test && cd ..`
Expected: FAIL — `electron/lib/port.js` no existe todavía.

- [x] **Step 8.3: Crear `electron/lib/port.js`**

Crear `electron/lib/port.js`:

```javascript
const net = require('node:net');

/**
 * Check if a TCP port is currently in use on 127.0.0.1.
 * @param {number} port
 * @returns {Promise<boolean>}
 */
function isPortInUse(port) {
  return new Promise((resolve) => {
    const tester = net.createServer();
    tester.once('error', () => resolve(true));
    tester.once('listening', () => {
      tester.close(() => resolve(false));
    });
    tester.listen(port, '127.0.0.1');
  });
}

/**
 * Find a free TCP port by asking the OS to assign one.
 * @returns {Promise<number>}
 */
function findFreePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', reject);
    server.listen(0, '127.0.0.1', () => {
      const { port } = server.address();
      server.close(() => resolve(port));
    });
  });
}

module.exports = { isPortInUse, findFreePort };
```

- [x] **Step 8.4: Correr el test, ver que pasa**

Run: `cd electron && npm test && cd ..`
Expected: PASS (3 tests).

- [x] **Step 8.5: Commit**

```bash
git add electron/lib/port.js electron/lib/port.test.js
git commit -m "feat(electron): port pre-flight utilities with tests"
```

---

## Task 9: `electron/lib/health.js` (health check waiter)

**Files:**
- Create: `electron/lib/health.js`
- Create: `electron/lib/health.test.js`

Lógica de esperar a que el sidecar responda al endpoint de health.

- [ ] **Step 9.1: Escribir el test que falla**

Crear `electron/lib/health.test.js`:

```javascript
const test = require('node:test');
const assert = require('node:assert');
const http = require('node:http');
const { waitForHealth } = require('./health');

function startFakeApi(port, statusCode = 200) {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      if (req.url === '/api/v1/health') {
        res.writeHead(statusCode, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'ok' }));
      } else {
        res.writeHead(404);
        res.end();
      }
    });
    server.listen(port, '127.0.0.1', () => resolve(server));
  });
}

test('waitForHealth resolves when API returns 200', async () => {
  const server = await startFakeApi(0, 200);
  const port = server.address().port;
  try {
    await waitForHealth(port, 2000, 50);
    assert.ok(true, 'waitForHealth resolved');
  } finally {
    await new Promise((r) => server.close(r));
  }
});

test('waitForHealth rejects when API never returns 200', async () => {
  const server = await startFakeApi(0, 500);
  const port = server.address().port;
  try {
    await assert.rejects(
      () => waitForHealth(port, 500, 50),
      /timed out/i
    );
  } finally {
    await new Promise((r) => server.close(r));
  }
});
```

- [ ] **Step 9.2: Correr el test, ver que falla**

Run: `cd electron && npm test && cd ..`
Expected: FAIL — `electron/lib/health.js` no existe.

- [ ] **Step 9.3: Crear `electron/lib/health.js`**

Crear `electron/lib/health.js`:

```javascript
const http = require('node:http');

/**
 * Poll the FastAPI health endpoint until it returns 200 or timeout.
 * @param {number} port - localhost port where the sidecar is listening
 * @param {number} timeoutMs - total timeout in ms
 * @param {number} intervalMs - poll interval in ms
 * @returns {Promise<void>} resolves when health returns 200
 * @throws {Error} if the timeout is reached
 */
function waitForHealth(port, timeoutMs = 10000, intervalMs = 200) {
  const deadline = Date.now() + timeoutMs;

  function attempt() {
    return new Promise((resolve, reject) => {
      const req = http.request(
        { host: '127.0.0.1', port, path: '/api/v1/health', method: 'GET', timeout: 1000 },
        (res) => {
          if (res.statusCode === 200) {
            res.resume();
            resolve();
          } else {
            res.resume();
            reject(new Error(`Health check returned ${res.statusCode}`));
          }
        }
      );
      req.on('error', reject);
      req.on('timeout', () => {
        req.destroy();
        reject(new Error('Health check request timed out'));
      });
      req.end();
    });
  }

  return new Promise((resolve, reject) => {
    function tick() {
      const remaining = deadline - Date.now();
      if (remaining <= 0) {
        return reject(new Error(`waitForHealth timed out after ${timeoutMs}ms`));
      }
      attempt().then(resolve, () => {
        setTimeout(tick, Math.min(intervalMs, remaining));
      });
    }
    tick();
  });
}

module.exports = { waitForHealth };
```

- [ ] **Step 9.4: Correr el test, ver que pasa**

Run: `cd electron && npm test && cd ..`
Expected: PASS (2 tests).

- [ ] **Step 9.5: Commit**

```bash
git add electron/lib/health.js electron/lib/health.test.js
git commit -m "feat(electron): health check waiter with tests"
```

---

## Task 10: `electron/preload.js` y `electron/main.js`

**Files:**
- Create: `electron/preload.js`
- Create: `electron/main.js`

- [x] **Step 10.1: Crear `electron/preload.js`**

Crear `electron/preload.js`:

```javascript
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('conciliacion', {
  platform: process.platform,
  versions: {
    electron: process.versions.electron,
    chrome: process.versions.chrome,
    node: process.versions.node,
  },
});
```

- [x] **Step 10.2: Crear `electron/main.js`**

Crear `electron/main.js`:

```javascript
const { app, BrowserWindow, dialog } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { isPortInUse } = require('./lib/port');
const { waitForHealth } = require('./lib/health');

const API_PORT = 57890;
let pythonProcess = null;
let mainWindow = null;

function getSidecarPath() {
  const name = process.platform === 'win32' ? 'conciliacion-api.exe' : 'conciliacion-api';
  return path.join(process.resourcesPath, name);
}

function getLogFile() {
  if (process.platform === 'win32') {
    return path.join(process.env.APPDATA || os.homedir(), 'conciliacion', 'logs', 'conciliacion.log');
  }
  const xdg = process.env.XDG_DATA_HOME || path.join(os.homedir(), '.local', 'share');
  return path.join(xdg, 'conciliacion', 'logs', 'conciliacion.log');
}

function setupSidecarLogging() {
  const logFile = getLogFile();
  fs.mkdirSync(path.dirname(logFile), { recursive: true });
  return logFile;
}

function startSidecar(logFile) {
  const sidecar = getSidecarPath();
  if (!fs.existsSync(sidecar)) {
    throw new Error(`Sidecar binary not found at ${sidecar}`);
  }
  const proc = spawn(sidecar, [], {
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  const out = fs.createWriteStream(logFile, { flags: 'a' });
  proc.stdout.pipe(out);
  proc.stderr.pipe(out);
  proc.on('exit', (code) => {
    if (code !== 0 && code !== null && mainWindow && !mainWindow.isDestroyed()) {
      console.error(`Sidecar exited with code ${code}`);
    }
  });
  return proc;
}

function fatalError(message) {
  dialog.showErrorBox('Conciliación Geotécnica — Error', message);
  app.quit();
}

app.whenReady().then(async () => {
  // Pre-flight: si el puerto está en uso, otra instancia está corriendo
  if (await isPortInUse(API_PORT)) {
    fatalError(`El puerto ${API_PORT} ya está en uso. ¿Hay otra instancia de Conciliación corriendo? Ciérrala e intenta de nuevo.`);
    return;
  }

  let logFile;
  try {
    logFile = setupSidecarLogging();
    pythonProcess = startSidecar(logFile);
  } catch (err) {
    fatalError(`No se pudo iniciar el backend: ${err.message}`);
    return;
  }

  try {
    await waitForHealth(API_PORT, 15000, 200);
  } catch (err) {
    fatalError(`El backend no respondió a tiempo. Revisá el log en ${logFile}`);
    return;
  }

  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 1024,
    minHeight: 768,
    title: 'Conciliación Geotécnica',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  mainWindow.setMenuBarVisibility(false);
  await mainWindow.loadURL(`http://127.0.0.1:${API_PORT}`);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
});

app.on('window-all-closed', () => {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
  app.quit();
});

app.on('before-quit', () => {
  if (pythonProcess) {
    pythonProcess.kill();
    pythonProcess = null;
  }
});
```

- [x] **Step 10.3: Verificar que el main.js no tiene errores de sintaxis**

Run: `cd electron && node --check main.js && node --check preload.js && node --check lib/port.js && node --check lib/health.js && cd ..`
Expected: sin output (todos los archivos pasan el syntax check).

- [x] **Step 10.4: Commit**

```bash
git add electron/preload.js electron/main.js
git commit -m "feat(electron): main process with sidecar spawn, health wait, and window"
```

---

## Task 11: `electron/builder.config.js`

**Files:**
- Create: `electron/builder.config.js`

- [x] **Step 11.1: Crear la config de electron-builder**

Crear `electron/builder.config.js`:

```javascript
const path = require('node:path');

/**
 * electron-builder config for the portable bundle.
 *
 * The Python sidecar (built with PyInstaller, see ../../conciliacion-api.spec)
 * is expected at:
 *   ../dist/conciliacion-api(.exe)
 *
 * Build:
 *   npm run build:windows  -> ../dist-portable/conciliacion-portable-windows/
 *   npm run build:linux    -> ../dist-portable/conciliacion-portable-linux.AppImage
 */
module.exports = {
  appId: 'app.conciliacion.geotecnica',
  productName: 'Conciliación Geotécnica',
  copyright: 'Copyright © 2026',

  directories: {
    output: path.join(__dirname, '..', 'dist-portable'),
    buildResources: path.join(__dirname, 'assets'),
  },

  files: [
    'main.js',
    'preload.js',
    'lib/**/*',
    'assets/**/*',
    'package.json',
  ],

  extraResources: [
    {
      from: path.join(__dirname, '..', 'dist', 'conciliacion-api.exe'),
      to: 'conciliacion-api.exe',
      filter: ['**/*'],
    },
    {
      from: path.join(__dirname, '..', 'dist', 'conciliacion-api'),
      to: 'conciliacion-api',
      filter: ['**/*'],
    },
  ],

  win: {
    target: [{ target: 'dir', arch: ['x64'] }],
    artifactName: 'conciliacion-portable-windows',
  },

  linux: {
    target: [{ target: 'AppImage', arch: ['x64'] }],
    artifactName: 'conciliacion-portable-linux.AppImage',
    category: 'Science',
  },

  // Sin auto-update en v1
  publish: null,
};
```

Nota: el `extraResources` lista ambos nombres de binario (`.exe` y sin
extensión) porque electron-builder en Windows/Linux construye desde el
mismo checkout. El que exista físicamente al momento de buildear se
copia; el otro falla silenciosamente. En el futuro podemos refinar esto
con un `extraResources` por target.

- [x] **Step 11.2: Verificar que la config es válida**

Run: `cd electron && node -e "const c = require('./builder.config.js'); console.log(JSON.stringify(c.win), JSON.stringify(c.linux.target))" && cd ..`
Expected: output con la config de Windows y el target `AppImage`.

- [x] **Step 11.3: Commit**

```bash
git add electron/builder.config.js
git commit -m "feat(electron): electron-builder config with sidecar resources"
```

---

## Task 12: `.github/workflows/build-portable.yml`

**Files:**
- Create: `.github/workflows/build-portable.yml`

- [x] **Step 12.1: Crear el workflow**

Crear `.github/workflows/build-portable.yml`:

```yaml
name: Build portable bundle

on:
  workflow_dispatch:

jobs:
  build:
    name: Build ${{ matrix.os }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [windows-latest, ubuntu-latest]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: "pip"

      - name: Set up Node 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: |
            web/package-lock.json
            electron/package-lock.json

      - name: Install Python deps
        run: |
          pip install -r requirements-api.txt
          pip install pyinstaller

      - name: Build React
        working-directory: web
        run: |
          npm ci
          npm run build
        env:
          VITE_API_URL: /api/v1

      - name: Build Python sidecar
        run: |
          pyinstaller --clean --noconfirm conciliacion-api.spec

      - name: Install Electron deps
        working-directory: electron
        run: npm ci

      - name: Build Electron app (Linux)
        if: matrix.os == 'ubuntu-latest'
        working-directory: electron
        run: npm run build:linux

      - name: Build Electron app (Windows)
        if: matrix.os == 'windows-latest'
        working-directory: electron
        run: npm run build:windows

      - name: Package Windows artifact
        if: matrix.os == 'windows-latest'
        shell: pwsh
        run: |
          Compress-Archive `
            -Path dist-portable/win-unpacked/* `
            -DestinationPath conciliacion-portable-windows.zip

      - name: Upload Windows artifact
        if: matrix.os == 'windows-latest'
        uses: actions/upload-artifact@v4
        with:
          name: conciliacion-portable-windows
          path: conciliacion-portable-windows.zip

      - name: Upload Linux artifact
        if: matrix.os == 'ubuntu-latest'
        uses: actions/upload-artifact@v4
        with:
          name: conciliacion-portable-linux
          path: dist-portable/Conciliación Geotécnica-*.AppImage

      - name: Rename Linux artifact for clarity
        if: matrix.os == 'ubuntu-latest'
        run: |
          mv dist-portable/*.AppImage conciliacion-portable-linux.AppImage
```

Nota: el último step de rename puede fallar si electron-builder nombra el
AppImage con caracteres especiales. En ese caso ajustar la glob en el
upload. El patrón `Conciliación Geotécnica-*.AppImage` es el default de
electron-builder con `productName: 'Conciliación Geotécnica'`.

- [x] **Step 12.2: Commit**

```bash
git add .github/workflows/build-portable.yml
git commit -m "ci(electron): GitHub Actions matrix for portable Windows + Linux builds"
```

---

## Task 13: `docs/PORTABLE.md`

**Files:**
- Create: `docs/PORTABLE.md`

- [ ] **Step 13.1: Crear la guía para el usuario final**

Crear `docs/PORTABLE.md`:

````markdown
# Guía de uso: Conciliación Geotécnica Portable

Esta es la versión de escritorio portable de la app. Se distribuye como
un único binario (Windows) o AppImage (Linux) y no requiere instalación.

## Windows

1. Descargá `conciliacion-portable-windows.zip` desde la página de
   releases o desde el artifact de GitHub Actions.
2. Extraé el `.zip` en cualquier carpeta (escritorio, USB, lo que sea).
3. Doble click en `conciliacion.exe`.
4. Si Windows SmartScreen te pregunta, hacé click en **"Más info"** y
   después en **"Ejecutar de todas formas"**. Esto aparece solo la
   primera vez.

## Linux

1. Descargá `conciliacion-portable-linux.AppImage`.
2. Abrí una terminal en la carpeta donde está el archivo.
3. Hacé el binario ejecutable:
   ```bash
   chmod +x conciliacion-portable-linux.AppImage
   ```
4. Ejecutalo:
   ```bash
   ./conciliacion-portable-linux.AppImage
   ```

### Troubleshooting Linux

- **"AppImage no se puede montar"** — Te falta FUSE. En Ubuntu 24.04+
  instalalo con `sudo apt install libfuse2`. En versiones más nuevas de
  Ubuntu, FUSE ya no viene por default.
- **El doble click no hace nada** — Asegurate de haber corrido
  `chmod +x` y de que tu file manager soporte ejecutar AppImages.
  Algunos file managers requieren click derecho → "Ejecutar".
- **"Falta libpython o similar"** — Tu distro tiene glibc < 2.35.
  Necesitás Ubuntu 22.04+, Debian 12+, Fedora 36+, o RHEL 9+.

## Dónde queda tu data

La base de datos, los logs y los archivos subidos se guardan en:

- **Windows**: `%APPDATA%\conciliacion\`
  (típicamente `C:\Users\<tu-usuario>\AppData\Roaming\conciliacion\`)
- **Linux**: `~/.local/share/conciliacion/`

**Importante**: la data NO está dentro del bundle. Si movés o borrás
la carpeta del binario, tu data queda intacta en esa ubicación.

## Cómo ver los logs

Los logs de la app y del backend se guardan en:

- **Windows**: `%APPDATA%\conciliacion\logs\conciliacion.log`
- **Linux**: `~/.local/share/conciliacion/logs/conciliacion.log`

Si la app no arranca o se comporta raro, este archivo es el primer
lugar para mirar.

## Cómo actualizar

1. Descargá el nuevo `.zip` / `.AppImage` de la última versión.
2. Cerrá la app si está abierta.
3. Reemplazá el binario viejo por el nuevo (la data en
   `%APPDATA%` / `~/.local/share/` no se toca).
4. Iniciá la app de nuevo.

## Limitaciones conocidas

- **No hay auto-actualización**: la actualización es manual como se
  describe arriba.
- **Una sola instancia por máquina**: si abrís la app dos veces, la
  segunda detecta que el puerto ya está en uso y se cierra.
- **Puerto 57890 debe estar libre**: si otra aplicación usa ese
  puerto, la app no va a arrancar.
- **Sin firma de código en Windows**: SmartScreen va a mostrar la
  advertencia la primera vez.
- **Sin AppImage firmado en Linux**: algunos sistemas pueden mostrar
  advertencias de seguridad.
````

- [ ] **Step 13.2: Commit**

```bash
git add docs/PORTABLE.md
git commit -m "docs(portable): user-facing guide for Windows + Linux portable bundle"
```

---

## Task 14: Validación end-to-end via GitHub Actions

Esta task no genera código — valida que todo el plan funciona junto.

- [ ] **Step 14.1: Push a una rama de prueba**

Run:
```bash
git checkout -b test/portable-bundle
git push -u origin test/portable-bundle
```

- [ ] **Step 14.2: Disparar el workflow manualmente**

1. Ir a GitHub → repo → Actions → "Build portable bundle"
2. Click "Run workflow" → seleccionar la rama `test/portable-bundle`
3. Esperar a que ambas matrices terminen (~10-15 min la primera vez)

Expected: ambos jobs terminan con ✅. Si fallan, leer los logs y
ajustar.

- [ ] **Step 14.3: Descargar los artifacts**

1. Ir al run del workflow completado
2. En la sección "Artifacts" al final de la página, descargar:
   - `conciliacion-portable-windows`
   - `conciliacion-portable-linux`

- [ ] **Step 14.4: Validar el bundle de Windows**

1. Copiar el `.zip` a una VM con Windows 10 u 11 (sin Python instalado)
2. Extraer
3. Doble click en `conciliacion.exe`
4. Confirmar:
   - Aparece una ventana nativa (no un browser)
   - El título es "Conciliación Geotécnica"
   - La UI de React se ve (incluyendo el visor 3D de Cesium)
   - Podés subir un STL, definir una sección, procesar, exportar Excel
5. Cerrar la ventana
6. Verificar que no quedan procesos `conciliacion-api.exe` corriendo
   (Task Manager)

- [ ] **Step 14.5: Validar el bundle de Linux**

1. En una VM con Ubuntu 22.04+ (sin Python instalado):
   ```bash
   chmod +x conciliacion-portable-linux.AppImage
   ./conciliacion-portable-linux.AppImage
   ```
2. Confirmar los mismos puntos que en Windows (ventana nativa, UI
   funciona, etc.)
3. Cerrar la ventana
4. Verificar que no quedan procesos Python huérfanos:
   ```bash
   ps aux | grep conciliacion-api
   # Expected: no output
   ```

- [ ] **Step 14.6: Validar la persistencia de data**

1. Subir un STL y procesar una sección
2. Cerrar la app
3. Reabrir la app
4. Confirmar que el STL y los resultados siguen ahí (sesión
   recuperada del SQLite)

- [ ] **Step 14.7: Validar el guard de instancia única**

1. Abrir la app
2. Intentar abrir otra instancia
3. Confirmar que la segunda instancia muestra un mensaje de error
   claro y se cierra (no se queda colgada)

- [ ] **Step 14.8: Si todo funciona, mergear a main**

```bash
git checkout main
git merge test/portable-bundle
git push origin main
git branch -d test/portable-bundle
```

- [ ] **Step 14.9: Si algo falló, NO mergear**

Iterar: arreglar lo que haya roto (probablemente ajustes al spec de
PyInstaller, al `main.js`, o al workflow), commitear, push, y volver
a Step 14.2.

---

## Self-Review (auto-revisión contra el spec)

Esta revisión la hago yo antes de declarar el plan completo:

**1. Spec coverage:** Cada sección del spec tiene al menos una task.

| Sección del spec | Task |
|---|---|
| Modificar `api/database.py` | Task 1 |
| Modificar `api/main.py` | Task 2 |
| Crear `entry_api.py` | Task 3 |
| Crear `conciliacion-api.spec` | Task 4 |
| Validar el build del sidecar | Task 5 |
| Set up del proyecto Electron | Task 6 |
| Íconos | Task 7 |
| Pre-flight del puerto (testable) | Task 8 |
| Health waiter (testable) | Task 9 |
| `main.js` y `preload.js` | Task 10 |
| `builder.config.js` | Task 11 |
| Workflow de GitHub Actions | Task 12 |
| `docs/PORTABLE.md` | Task 13 |
| Validación end-to-end | Task 14 |

✅ Todas las secciones del spec están cubiertas.

**2. Placeholder scan:** Busqué "TBD", "TODO", "implement later" en el
plan. No encontré. Todos los steps tienen código o comandos concretos.

**3. Type consistency:**
- `resolve_data_dir()` retorna `Path` en Tasks 3 y test. ✅
- `isPortInUse(port)` retorna `Promise<boolean>` en Tasks 8 y 10. ✅
- `waitForHealth(port, timeoutMs, intervalMs)` retorna `Promise<void>`
  en Tasks 9 y 10. ✅
- Sidecar path es `conciliacion-api.exe` o `conciliacion-api` en
  Tasks 10 y 11. ✅
- API_PORT = 57890 en Tasks 9, 10, 11. ✅
- Data dir resolution consistente entre `entry_api.py` (Task 3) y
  `getLogFile()` en `main.js` (Task 10). ✅

**4. Riesgos del spec:**

| Riesgo | Cubierto en |
|---|---|
| PyInstaller + scipy | `--collect-all` en spec, smoke test en Task 5 |
| Antivirus marca el `.exe` | Documentado en PORTABLE.md (Task 13) |
| Cold start 3-5s del sidecar | Aceptado |
| Puerto 57890 ya en uso | Pre-flight en Task 8, usado en Task 10 |
| Múltiples instancias | Pre-flight del puerto (mismo que arriba) |
| Cesium/React bloat | Aceptado |
| FUSE missing en Linux | Documentado en PORTABLE.md (Task 13) |
| glibc < 2.35 | Documentado en PORTABLE.md (Task 13) |
| Procesos zombies | `before-quit` handler en Task 10 |

✅ Todos los riesgos están mitigados o documentados.

---

## Resumen de tasks

| # | Qué | Tipo |
|---|---|---|
| 1 | `api/database.py` honra env var | Backend + test |
| 2 | `api/main.py` monta `web/dist/` | Backend + test |
| 3 | `entry_api.py` con `resolve_data_dir()` | Sidecar + tests |
| 4 | `conciliacion-api.spec` | Spec de PyInstaller |
| 5 | Smoke test del sidecar (Linux local) | Validación |
| 6 | Set up de `electron/` con deps | Scaffolding |
| 7 | Íconos placeholder | Assets |
| 8 | `electron/lib/port.js` (pre-flight) | Lógica + tests |
| 9 | `electron/lib/health.js` (waiter) | Lógica + tests |
| 10 | `electron/main.js` + `preload.js` | Proceso principal |
| 11 | `electron/builder.config.js` | Config |
| 12 | `.github/workflows/build-portable.yml` | CI |
| 13 | `docs/PORTABLE.md` | Docs para el usuario |
| 14 | Validación end-to-end en CI | Smoke test |

Total: 14 tasks. ~150-200 minutos de trabajo hands-on más el tiempo de
build de CI.
