# Portable Windows Bundle (single `.exe`, no install)

**Date:** 2026-06-07
**Status:** Approved (pending spec review)
**Owner:** maintainer

## Goal

Ship a single Windows `.exe` that the maintainer can copy to a locked-down
work PC (no admin, no installer, no Python) and run by double-clicking. The
`.exe` runs the existing React + FastAPI stack end-to-end with the same UX
as the current dev workflow. Reference UX: Blender's portable `.zip` (a
single executable that contains everything, no install required).

Non-goals (out of scope for v1):

- macOS / Linux portable builds
- Auto-update
- Code signing (EV certs cost money; corporate SmartScreen click-through
  is acceptable for an internal tool)
- Portabilizing the legacy Streamlit UI (per CONTRIBUTING.md, the Streamlit
  surface is off-limits; we target the React frontend)
- Native OS integration (system tray, file dialogs, etc.) — not needed

## Architecture

```
┌───────────────────────────────────────────────────────────┐
│  conciliacion.exe  (PyInstaller --onefile, ~150-200 MB)   │
│                                                            │
│  Extracted to %TEMP%/_MEIxxxxx on launch, contains:       │
│  ┌──────────────────────────────────────────────────┐     │
│  │  Python 3.12 interpreter                          │     │
│  │  site-packages: fastapi, uvicorn, trimesh,        │     │
│  │     numpy, scipy, shapely, openpyxl, ...          │     │
│  │  api/ + core/ (project source)                    │     │
│  │  web/dist/ (React build)                          │     │
│  │  entry_portable.py (custom entrypoint)            │     │
│  └──────────────────────────────────────────────────┘     │
│                                                            │
│  On launch (entry_portable.py):                            │
│  1. Resolve %APPDATA%/conciliacion/ for data + logs        │
│  2. Set DATABASE_URL, CONCILIACION_DATA_DIR env vars       │
│  3. Mount web/dist/ as StaticFiles at "/" on the FastAPI   │
│  4. Open default browser → http://localhost:57890          │
│  5. Run uvicorn (api.main:app) on 127.0.0.1:57890          │
│  6. On Ctrl+C / window close: shutdown uvicorn, exit        │
└───────────────────────────────────────────────────────────┘
```

One process, one browser window, one `conciliacion.exe`. No WebView2
dependency, no Rust toolchain, no second process to manage.

## Bundle shape (post-build)

After running PyInstaller + zip:

```
conciliacion-portable/
└── conciliacion.exe        # the only file the user needs
```

After double-clicking, the app creates (and reuses on subsequent runs):

```
%APPDATA%/conciliacion/
├── conciliacion.db         # SQLite (sessions, meshes, results)
├── conciliacion.db-wal     # WAL journal
├── conciliacion.db-shm
├── logs/
│   └── conciliacion.log    # uvicorn + app logs
└── uploads/                # user STL/DXF inputs (optional, future)
```

This keeps user data off the `.exe` (so moving the `.exe` between folders
or upgrading to a new build doesn't lose data) and inside the standard
Windows appdata location.

## Changes to the codebase

### 1. `entry_portable.py` (new, repo root)

Custom PyInstaller entrypoint. Responsibilities:

- Resolve `%APPDATA%` (Windows) / `~/.local/share` (Linux, future)
- Set `CONCILIACION_DATA_DIR` and `DATABASE_URL` env vars BEFORE importing
  `api.database` (the module reads `DB_PATH` at import time)
- Configure logging to a file under `data_dir/logs/`
- Mount `web/dist/` as `StaticFiles(html=True)` at `/` on the FastAPI app
  (only if the directory exists, so dev workflow is unaffected)
- Pre-flight: try to bind to port 57890. If `OSError` (port busy), assume
  another instance is already running, log a clear error to the log file,
  and exit. This is the single-instance guard (simpler and more portable
  than file locks across Windows/Linux).
- Spawn a daemon thread that calls `webbrowser.open("http://localhost:57890")`
  after a short sleep (so uvicorn is ready)
- Run `uvicorn.run(app, host="127.0.0.1", port=57890, log_config=None)` on
  the main thread; propagate file logging through a custom `log_config`

### 2. `conciliacion.spec` (new, repo root)

PyInstaller spec file. Key flags:

- `datas=[('web/dist', 'web/dist')]` — bundle the React build
- `hiddenimports=[...]` — force-include lazy-loaded modules (scipy, shapely,
  trimesh, pandas internals)
- `--collect-all scipy --collect-all shapely --collect-all trimesh
  --collect-all numpy` — these packages use lazy imports + data files that
  PyInstaller's static analysis misses
- `excludes=['tkinter', 'pytest', 'matplotlib.tests', 'IPython', 'notebook']`
  — keep the bundle small
- `console=False` — no flashing console window
- `icon='assets/icon.ico'` — desktop icon (placeholder, can be added later)
- `onefile=True` (via `EXE` with all binaries packed)

### 3. `api/database.py` (modify)

Line 14 currently hardcodes:

```python
DB_PATH = Path(__file__).parent.parent / "data" / "conciliacion.db"
```

Change to honor `CONCILIACION_DATA_DIR` (already defined in
`core/config.py:DeployDefaults:94`):

```python
_DATA_DIR = Path(os.environ.get("CONCILIACION_DATA_DIR", Path(__file__).parent.parent / "data"))
DB_PATH = _DATA_DIR / "conciliacion.db"
```

This is a small additive change. The default preserves the current
behaviour for dev / Render / Streamlit. The portable entrypoint sets the
env var before importing, so the portable build gets `%APPDATA%`.

### 4. `api/main.py` (modify, additive)

After the routers are included, mount the React build at `/` if the
directory exists:

```python
_web_dist = Path(__file__).parent.parent / "web" / "dist"
if _web_dist.exists():
    app.mount("/", StaticFiles(directory=str(_web_dist), html=True), name="web")
```

`html=True` makes StaticFiles serve `index.html` for directory requests,
which is what the React SPA needs for client-side routing. The check on
`_web_dist.exists()` means dev workflow (where the React dev server runs
separately on :5173) is unaffected.

### 5. `.github/workflows/build-portable.yml` (new)

Manual trigger (`workflow_dispatch`) only for v1. Steps:

1. Checkout
2. `actions/setup-python@v5` (Python 3.12, pip cache)
3. `actions/setup-node@v4` (Node 20, npm cache)
4. `pip install -r requirements-api.txt pyinstaller`
5. `npm ci` (in `web/`)
6. `npm run build` (in `web/`, with `VITE_API_URL=/api/v1` so the React
   build uses relative paths and works for both dev and portable)
7. `pyinstaller --clean --noconfirm conciliacion.spec`
8. `Compress-Archive dist/conciliacion.exe conciliacion-portable.zip`
9. `actions/upload-artifact@v4` with path `conciliacion-portable.zip`

Build time on `windows-latest`: first run ~8-10 min (PyInstaller cold
cache), subsequent runs ~3-5 min.

### 6. `docs/PORTABLE.md` (new)

User-facing guide. Contents:

- What the `.zip` contains
- "Double-click `conciliacion.exe`" instructions
- Where data is stored (`%APPDATA%/conciliacion/`)
- How to enable devtools / see logs
- Windows SmartScreen: click "More info" → "Run anyway"
- How to update (download new `.zip`, replace `.exe`)
- Known limitations (no auto-update, port 57890 must be free)

## Design decisions

| Decision | Choice | Why |
|---|---|---|
| Packaging tech | PyInstaller `--onefile` | Blender-style UX, single file, mature for the scientific stack with `--collect-all` flags |
| Python distribution | Bundled via PyInstaller | Avoids the rust/conda/embed-Python alternatives; PyInstaller is the de-facto standard |
| Port | `57890` (hardcoded) | Avoids runtime config; not a common service port; documented as a known limitation |
| CORS | Same-origin (portable), unchanged (dev) | When FastAPI serves the React build at `/`, browser sees same origin → no CORS issues. Dev workflow unchanged. |
| Data location | `%APPDATA%/conciliacion/` (env-overridable) | Standard Windows location; survives `.exe` moves and upgrades; user can back up easily |
| Console window | Hidden (`console=False`) | Clean UX; logs go to file in `%APPDATA%` |
| Browser auto-open | `webbrowser.open()` after 1.5s sleep | Same pattern as Jupyter, Streamlit, Marimo — works on any browser the user has |
| Build trigger | `workflow_dispatch` only (v1) | Manual control until we know it works; can add `push tag:` later |
| Update strategy | Manual (download new `.zip`) | Out of scope to build an auto-update channel in v1 |

## Risks and mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| PyInstaller fails to bundle scipy | High (known) | Build broken | `--collect-all scipy --collect-all numpy` + runtime hook to import scipy submodules |
| PyInstaller fails to bundle shapely | High (known) | Build broken | `--collect-all shapely` + hidden import for `shapely.geometry` |
| Antivirus flags `.exe` | Medium | User friction | Document SmartScreen click; bundle is unsigned; can add signing in v2 |
| First cold start 3-5s | Medium | Minor UX | Acceptable for an internal tool; document it |
| Port 57890 already in use | Low | App fails to start | Entry script checks the port; if busy, picks the next free port and writes the actual URL to a log line for the user to see |
| Multiple `.exe` instances | Low | Data corruption | Entry script tries to bind to port 57890 first; if busy, exits with a clear error logged to the log file. Simpler and more portable than file locks. |
| Cesium assets (~22 MB) bloat the `.exe` | Certain | Bundle size +200 MB extra | Acceptable; Cesium is required for the 3D view. Could be lazy-loaded in v2. |
| `web/dist` size (~25-30 MB) | Certain | Bundle size | Acceptable; unavoidable for the React build |
| Browser doesn't auto-open (e.g., headless / kiosk PC) | Low | Bad UX | Fallback: log the URL to file + show a native dialog? Out of scope; document. |

## Out-of-scope follow-ups (for v2+)

- Auto-update via a Squirrel.Mac/Squirrel.Windows-style differential updater
- Code signing (EV cert from DigiCert / Sectigo, ~$300-500/yr)
- macOS / Linux portable builds (PyInstaller supports them; needs CI matrix
  + a `.spec` tweak)
- Make the entry script a Tauri/Electron shell if we ever need OS-native
  features (file dialogs, system tray, native menu)
- Bundle Cesium as an optional / lazy download so the basic `.exe` is
  smaller and 3D-view users can opt in

## Acceptance criteria

- [ ] `conciliacion-portable.zip` is uploaded as a GitHub Actions artifact
- [ ] The extracted `.exe` runs on a clean Windows 10/11 VM with no Python
      installed
- [ ] Doble click → browser opens to `http://localhost:57890` within 5s
- [ ] Uploading an STL, defining a section, processing, and exporting
      Excel all work end-to-end
- [ ] Restarting the `.exe` preserves the SQLite data (sessions, meshes)
- [ ] No console window flashes on launch
- [ ] Cesium 3D viewer loads (proves the `web/dist` mount works)
- [ ] Antivirus scan of the `.exe` does not flag it (or: a known false
      positive is documented in PORTABLE.md)
- [ ] Closing the browser tab and Ctrl+C in any open console cleanly
      shuts down uvicorn (no orphan Python process)

## Files touched (summary)

| File | Action | Why |
|---|---|---|
| `entry_portable.py` | new | Custom PyInstaller entrypoint |
| `conciliacion.spec` | new | PyInstaller build recipe |
| `api/database.py` | modify (1 line) | Honor `CONCILIACION_DATA_DIR` env var |
| `api/main.py` | modify (additive) | Mount `web/dist/` as static at `/` if present |
| `.github/workflows/build-portable.yml` | new | Windows build + artifact |
| `docs/PORTABLE.md` | new | User-facing usage doc |
| `web/src/api/client.ts` | no change | Already supports relative `VITE_API_URL` |
| `core/`, `web/`, etc. | no change | Untouched |

## Open questions (none blocking — defaults chosen)

All decisions have defaults; no follow-up needed before implementation.
