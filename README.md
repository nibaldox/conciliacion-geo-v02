# Conciliación Geotécnica — Diseño vs As-Built

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688)](https://fastapi.tiangolo.com)
[![React 19](https://img.shields.io/badge/React-19-61DAFB)](https://react.dev)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8-3178C6)](https://www.typescriptlang.org)
[![PWA](https://img.shields.io/badge/PWA-ready-5A29E4)](https://web.dev/progressive-web-apps/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-97%2F97-brightgreen)](tests/)

> **Open-source geotechnical reconciliation for open-pit mining.** Compare
> 3D design surfaces vs as-built topography, generate cross-sections,
> evaluate compliance against configurable tolerances, export
> professional Excel/Word/DXF reports. All in your browser.
>
> *Conciliación geotécnica open-source para minería a cielo abierto.
> Compara superficies 3D de diseño vs topografía real, genera
> secciones, evalúa cumplimiento contra tolerancias.*

[Live demo](https://nibaldox.github.io/conciliacion-geo-v02/) ·
[Architecture](ARCHITECTURE.md) ·
[Deploy guide](web/DEPLOY.md) ·
[Contributing](CONTRIBUTING.md)

---

## ⚡ Try it now — no signup

The hosted demo is **free, public, and requires no account**:

1. Open the [live site](https://nibaldox.github.io/conciliacion-geo-v02/)
2. Click **🎮 Try with sample data**
3. Browse the dashboard, 3D viewer, and exported reports
4. (Optional) Click **Empezar** to upload your own `.stl`

The frontend is hosted on GitHub Pages (free). The backend runs on
Render.com (free tier) only when you upload your own data.

---

## ✨ Features

- **Multi-format mesh support** — STL, OBJ, PLY, DXF
- **Auto-section generation** — by start/end line, by polyline file, or click-on-map
- **RDP + Hungarian matching** — robust bench / berm / face detection with no double-counting
- **Compliance dashboard** — CUMPLE / FUERA / NO CUMPLE per sector, parameter, bench
- **3D and 2D views** — CesiumJS for the terrain, Plotly for interactive profiles, Chart.js for charts
- **Excel / Word / DXF exports** — formatted reports ready for engineering review
- **Drill & Blast ↔ Geotech correlation** — project blast holes onto cross-sections, see which benches over- or under-excavated
- **🌐 Bilingual UI** — Spanish (default) + English, switchable from the header
- **📱 PWA** — installable, works offline, sub-330 KB initial bundle
- **🎮 Demo mode** — pre-computed synthetic pit, 4 benches, 5 sections, 40 compliance rows, no upload needed
- **🔓 Open source, MIT** — your data stays in your session, no hidden telemetry

---

## 🚀 Two ways to run it

The project ships **two complete user interfaces** that share the
same `core/` domain logic:

### 1. Web app (recommended for sharing) — `web/`

Modern React 19 + FastAPI architecture, deployed for free on
GitHub Pages + Render.com. See [web/DEPLOY.md](web/DEPLOY.md)
for the full guide.

```bash
# Backend
pip install -e .
uvicorn api.main:app --reload --port 8000

# Frontend (separate terminal)
cd web && npm install && npm run dev    # → http://localhost:5173
```

### 2. Streamlit (the maintainer uses this daily) — `app.py`

Single-file Streamlit app, no separate backend. **Not touched by
recent v2 work** — the maintainer uses it for real work and the
contributing guide explicitly forbids changes here.

```bash
pip install -r requirements.txt
streamlit run app.py                        # → http://localhost:8501
```

Both interfaces call the same `core/` library (mesh cutting,
parameter extraction, comparison, export) so results are
identical.

---

## 📸 Screenshots

The legacy Streamlit UI has screenshots in [`printscr/`](printscr/)
that show the four-step workflow. The new React webapp is
visually richer (3D Cesium viewer, drag-to-edit bench editor,
compliance dashboard with traffic-light colour coding); we're
in the process of capturing fresh screenshots — PRs welcome.

| Dashboard overview (Streamlit, legacy) | Profile analysis (Streamlit, legacy) |
|:--:|:--:|
| ![dashboard](printscr/dashboard-overview.png) | ![profile](printscr/profile-analysis.png) |

| Section definition (Streamlit, legacy) | Parameter settings (Streamlit, legacy) |
|:--:|:--:|
| ![sections](printscr/section-definition.png) | ![params](printscr/parameter-settings.png) |

---

## 🏗️ Architecture

```
                            ┌────────────────────────────┐
                            │   GitHub Pages (static)    │
                            │   nibaldox.github.io/...   │
                            │   • React 19 + Vite 6      │
                            │   • CesiumJS 1.140 (lazy)  │
                            │   • Plotly 2.35 (lazy)     │
                            │   • PWA + Workbox SW       │
                            │   • i18n ES/EN             │
                            │   • 330 KB initial bundle  │
                            └─────────┬──────────────────┘
                                      │ HTTPS + CORS allowlist
                                      ▼
                            ┌────────────────────────────┐
                            │   Render.com (Docker)      │
                            │   FastAPI + uvicorn        │
                            │   • /api/v1/* routers      │
                            │   • SQLite sessions        │
                            │   • Health probes          │
                            │   • Slowapi rate limit     │
                            └─────────┬──────────────────┘
                                      │
                                      ▼
                            ┌────────────────────────────┐
                            │   core/  (shared domain)   │
                            │   • mesh_handler           │
                            │   • section_cutter         │
                            │   • param_extractor        │
                            │   • excel_writer           │
                            │   • report_generator       │
                            │   • blast_correlation      │
                            └────────────────────────────┘
```

For the full breakdown see [ARCHITECTURE.md](ARCHITECTURE.md).
For deploy step-by-step see [web/DEPLOY.md](web/DEPLOY.md).

---

## 🧪 Running tests

```bash
pytest tests/ -v                             # 97 backend tests
python test_pipeline.py                      # end-to-end pipeline
cd web && npm run build                      # TypeScript + Vite build
cd web && npm run lint                       # ESLint
```

The frontend has no unit tests yet — Playwright is installed but
not wired into CI. PRs adding Vitest + RTL would be very welcome.

---

## 🛠️ Project structure

```
core/             ← domain logic, imported by BOTH interfaces
  blast_correlation.py   (Drill & Blast ↔ geotech correlation)
  excel_writer.py
  geom_utils.py
  mesh_handler.py
  param_extractor.py
  report_generator.py
  section_cutter.py
  config.py                (frozen dataclasses with all defaults)

api/              ← FastAPI backend (modular, /api/v1/*)
  routers/        (meshes, sections, process, export, settings, ai)
  middleware*.py  (request id, structured log, rate limit)
  main.py         (app factory + lifespan + health probes)

web/              ← React 19 + Vite 6 + CesiumJS frontend
  src/components/  (wizard steps, demo, landing, ui primitives)
  src/locales/     (es.json, en.json)
  src/api/         (axios client, TanStack Query hooks)
  public/demo/     (synthetic STLs + precomputed.json for demo mode)
  DEPLOY.md        (step-by-step deploy guide)

app.py / ui/      ← LEGACY Streamlit UI (do not modify)
scripts/          ← one-off generators (demo data, etc.)
tests/            ← pytest suite for core/ + api/
ARCHITECTURE.md   ← architecture overview
AGENTS.md         ← entry point for AI agents
CONTRIBUTING.md   ← contribution guide
CODE_OF_CONDUCT.md
LICENSE           ← MIT
```

---

## 🌐 Internationalization

UI strings live in `web/src/locales/{es,en}.json`. To add a new
key:

1. Add it to BOTH `es.json` and `en.json` under the right namespace
   (`nav`, `common`, `demo`, `step1`..`step4`, `compliance`,
   `tooltip`, `shortcuts`, `landing`)
2. Use it in the component: `const { t } = useTranslation(); t('key')`
3. For counts, use ICU plurals: `t('common.n_sections', { count: n })`
   with `_one` / `_other` keys

The language is persisted in `localStorage` and the `<html lang>`
attribute is kept in sync (for screen readers).

---

## 🔭 Observability (opt-in)

All telemetry is **off by default** — the site ships zero
observability unless you opt in. See [web/DEPLOY.md](web/DEPLOY.md)
for setup.

| Tool | What | Env var |
|---|---|---|
| Sentry (frontend) | JS errors, perf, replays on error | `VITE_SENTRY_DSN` |
| Sentry (backend) | Python exceptions, slow requests | `SENTRY_DSN` |
| Plausible / CF / etc. | Privacy-friendly page views | `VITE_ANALYTICS_URL` |
| UptimeRobot | Is `/api/v1/health` 200 every 5 min? | (no env var — set up at uptimerobot.com) |

Mesh file names never leave your server (`send_default_pii=False`
on the backend; query strings are stripped before Sentry reports
on the frontend).

---

## 🤝 Contributing

We love PRs! See [CONTRIBUTING.md](CONTRIBUTING.md) for the full
guide. Highlights:

- **Streamlit (`app.py`, `ui/`, `core/`, `cli.py`) is OFF-LIMITS** — the
  maintainer uses it daily for real work. New work goes in
  `web/` and `api/`, and must be **additive**.
- **Both locales, always** — when adding a UI string, add it to
  BOTH `es.json` and `en.json`.
- **Conventional commits** (`feat:`, `fix:`, `refactor:`, `test:`,
  `docs:`, `chore:`). No `Co-Authored-By:`. No AI attribution.
- **The maintainer triages fast** if your PR description is clear
  and you've filled in the PR template.

Our [Code of Conduct](CODE_OF_CONDUCT.md) is Contributor Covenant
2.1.

---

## 📜 License

[MIT](LICENSE) — do what you want, just keep the copyright
notice. If you build something cool on top of this, we'd love
to hear about it.

---

## 🙋 Maintainer

- **Nibaldo Aviles** ([@nibaldox](https://github.com/nibaldox)) —
  geotechnical engineer who needed this for real projects and
  decided to share.

## 🌟 Star history

If this saved you a few days of work, a star on GitHub helps
others find it. ⭐
