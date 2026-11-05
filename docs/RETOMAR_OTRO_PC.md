# Continuar en otro equipo

Estado guardado el 4 de noviembre de 2026 en la rama `codex/continuidad-tronadura-20261104`. Es una copia de continuidad con trabajo en curso; la primera entrega de mejora de tronadura todavía requiere cierre de pruebas de interfaz y revisión visual.

## Obtener el código

```powershell
git clone --branch codex/continuidad-tronadura-20261104 https://github.com/nibaldox/conciliacion-geo-v02.git
cd conciliacion-geo-v02
```

Si el repositorio ya existe en ese equipo, comprobar primero sus cambios locales y después obtener esta rama con `git fetch origin` y `git switch --track origin/codex/continuidad-tronadura-20261104`. No descartar cambios existentes para cambiar de rama.

## Preparar y ejecutar

Instalar Python compatible con el proyecto y Node 20 o superior. En PowerShell, desde la raíz:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pip install -r requirements-api.txt
Set-Location web
npm ci
```

API, en una terminal desde la raíz:

```powershell
$env:CONCILIACION_DATA_DIR = Join-Path (Get-Location).Path 'data/web-local'
.\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Web, en otra terminal desde `web/`:

```powershell
npm run dev -- --host 127.0.0.1
```

Abrir `http://127.0.0.1:5173/conciliacion-geo-v02/`. En Linux o macOS comprobar además los requisitos de `libspatialindex` documentados en README.

## Datos locales

GitHub contiene código, pruebas y documentos. Las mallas STL, libros Excel, la base SQLite, dependencias y archivos ignorados por Git no forman parte de esta rama. Para repetir la prueba real, copiar por separado la carpeta de archivos de entrada del equipo original. La sesión local estaba almacenada en `data/web-prueba-20261102/`; llevar esa carpeta mediante una copia consistente con la API detenida si también se necesita recuperar la sesión, y configurar `CONCILIACION_DATA_DIR` con su nueva ubicación. Las rutas absolutas históricas del handoff no son portables.

## Punto de reanudación

1. Leer `AGENTS.md` y el final de `docs/HANDOFF.md`.
2. Consultar `docs/PLAN_MEJORA_TRONADURA_WEB.md` y `docs/REVISION_TRONADURA_STREAMLIT_WEB.md`.
3. Terminar las pruebas del nuevo mapeador y de cambios de hoja, revisar traducciones/confianza y campos opcionales, ejecutar build/lint y revisar visualmente la primera entrega.
4. Continuar con las entregas posteriores del plan cuando la primera esté verificada.

La última comprobación registrada fue de 147 pruebas backend focalizadas aprobadas y compilación TypeScript correcta. La suite completa y la revisión visual final no se acreditan para este checkpoint. La interfaz operativa de Streamlit se conserva como referencia.
