# Guía de build — Conciliación Geotécnica (Electron portable)

Este documento describe cómo generar la versión portable de escritorio (Electron + Python sidecar) del proyecto.

## Requisitos previos

- Python 3.10+ (recomendado 3.12)
- Node.js 20+
- npm
- Entorno virtual con las dependencias del backend instaladas (`.venv/`)
- `pyinstaller`:

```bash
uv pip install pyinstaller
```

- Dependencias del sistema para `rtree`:
  - Ubuntu/Debian: `sudo apt-get install libspatialindex-dev`
  - macOS: `brew install spatialindex`

## Estructura del bundle

- `core/` y `api/` se empaquetan en el binario Python usando `conciliacion-api.spec`.
- `web/dist/` es el frontend React compilado.
- `electron/` es el shell de Electron que lanza el sidecar Python y carga la UI.

## Pasos de build

### 1. Compilar el frontend

```bash
cd web
npm install
npm run build
```

Esto genera `web/dist/` con `index.html` y los assets estáticos.

### 2. Compilar el sidecar Python

```bash
cd /home/xodla/archivos/12_WindSurf/46-conciliacion-geo-v02
pyinstaller --clean --noconfirm conciliacion-api.spec
```

Resultado:

- Linux: `dist/conciliacion-api`
- Windows: `dist/conciliacion-api.exe`

El spec incluye `core/`, `api/`, `web/dist/` y las dependencias científicas necesarias en `hiddenimports`.

### 3. Instalar dependencias de Electron

```bash
cd electron
npm install
```

### 4. Generar el bundle portable

Linux (AppImage):

```bash
cd electron
npm run build:linux
```

Resultado: `dist-portable/conciliacion-portable-linux.AppImage`

Windows:

```bash
cd electron
npm run build:windows
```

Resultado: `dist-portable/conciliacion-portable-windows/`

## Workflow de desarrollo

Para trabajar en la UI sin recompilar el sidecar en cada cambio:

```bash
# Terminal 1: levantar API + Vite
./dev.sh

# Terminal 2: lanzar Electron apuntando al servidor de desarrollo
CONCILIACION_ELECTRON_DEV=1 npm run dev --prefix electron
```

Alternativa con un solo comando:

```bash
./dev-electron.sh
```

Este script:

1. Exporta `CONCILIACION_ELECTRON_DEV=1`.
2. Levanta la API en el puerto configurado (`CONCILIACION_API_PORT`, default `8000`).
3. Levanta el dev server de Vite.
4. Lanza Electron cargando la URL de Vite.

En modo dev, `electron/main.js` omite el lanzamiento del sidecar Python y carga directamente `http://localhost:5173` (o el valor de `CONCILIACION_DEV_URL`).

## Tests del shell de Electron

```bash
cd electron
npm test
```

Incluye tests para `lib/port.js`, `lib/health.js`, `lib/dev-mode.js` y `lib/spawn-sidecar.js`.

### Tests de integración de Electron

```bash
cd electron
npm run test:integration
```

Este comando ejecuta los tests de `electron/lib/*.test.js` de forma explícita.

### Tests E2E del bundle (Python)

Estos tests verifican que el sidecar compilado arranque, responda a `/api/v1/health` y sirva el frontend empaquetado. Requieren el binario del sidecar y, si el puerto `57890` está ocupado, se saltan automáticamente.

```bash
# Requiere el sidecar compilado
pyinstaller --clean --noconfirm conciliacion-api.spec

# Ejecutar E2E
pytest tests/test_electron_e2e.py -v
```

Si no se compiló el sidecar, los tests se saltan con `pytest.skip` y no fallan. Para forzar el salto:

```bash
pytest tests/test_electron_e2e.py -v --skip-electron
```

## Solución de problemas

### El puerto 57890 ya está en uso

Cierra cualquier instancia anterior del bundle portable o del sidecar. En Linux:

```bash
pkill -f conciliacion-api
```

### No se encuentra el sidecar

Asegúrate de haber corrido `pyinstaller --clean --noconfirm conciliacion-api.spec` antes de `npm run build:*`. `electron/builder.config.js` espera el binario en `../dist/conciliacion-api(.exe)`.

### `web/dist/` no existe

Corré el build del frontend primero:

```bash
cd web && npm run build
```

### El build de `web` falla con error de TypeScript en `BlastUploader.test.tsx`

Si `tsc -b` reporta un error de tipo en `src/components/results/BlastUploader.test.tsx` relacionado con `carga_mean` (`Type 'number | null' is not assignable to type 'number'`), es un problema preexistente en el test. El build no se puede completar hasta corregir ese test. La carpeta `web/dist/` puede existir de builds anteriores, pero no se regenerará hasta solucionarlo.

### Error con `@rollup/rollup-linux-x64-gnu`

Si `npm run dev` falla con `Cannot find module '@rollup/rollup-linux-x64-gnu'`, instalá el binario nativo correspondiente:

```bash
cd web
npm install @rollup/rollup-linux-x64-gnu
```

### Electron muestra pantalla negra después de actualizar

El bundle usa un directorio de usuario (`userData`) bajo `~/.local/share/conciliacion/chromium` para evitar que Service Workers o caché de versiones anteriores rompan la app. Si persisten problemas, borrá ese directorio.

## Notas

- `web/public/Cesium/` está trackeado en git (~22 MB) y no se incluye como dependencia npm. No agregar `cesium` a `package.json`.
- Para builds de Electron portable se desactiva el Service Worker con `VITE_PWA=false` antes de compilar el frontend, de lo contrario la recarga de página puede servir un `index.html` cacheado con hashes de assets antiguos.
- El build de PyInstaller puede tardar varios minutos la primera vez porque empaqueda las librerías científicas (numpy, scipy, trimesh, etc.).
