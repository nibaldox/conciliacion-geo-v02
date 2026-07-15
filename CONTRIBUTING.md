# Contributing to Conciliación Geotécnica

Thank you for your interest in making this tool better! 🎉
This is a community project — every PR, issue, and typo fix matters.

> **Heads up**: the user uses the **Streamlit** UI (`app.py`) **daily** for
> real work, so `app.py`/`ui/` are **protected** (not forbidden). Bug fixes
> and additive improvements are welcome there — flag them clearly in your PR;
> refactors or changes to existing flows need explicit maintainer approval.
> New features go into `web/` (React frontend) and `api/` (FastAPI backend).
> `core/` changes are welcome but must preserve the public API; coordinate on
> `cli.py`.

## 🏗️ Repo layout

```
core/             ← domain logic (mesh cutting, param extraction, comparison)
                   imported by BOTH the Streamlit app and the FastAPI app
api/              ← FastAPI backend (modular, mounted under /api/v1)
  routers/        ← meshes, sections, process, export, settings, ai
  middleware*.py  ← request id, structured log, rate limit
  main.py         ← app factory + CORS + size-guard + health probes
web/              ← React 19 + Vite 6 + CesiumJS + Plotly frontend
  src/components/ ← wizard step components (Step1..4) and demo
  src/locales/     ← i18n strings (es.json, en.json)
  src/api/         ← axios client + TanStack Query hooks
app.py / ui/      ← LEGACY Streamlit UI — protected (fixes/additive OK with care)
tests/            ← pytest suite for core/ and api/
scripts/          ← one-off generators (e.g. demo data)
```

## 🚀 Local setup (10 minutes)

You need: **Python 3.10+**, **Node 20+**, **git-lfs** (optional),
**libspatialindex** system package.

```bash
# 1. Clone
git clone https://github.com/nibaldox/conciliacion-geo-v02.git
cd conciliacion-geo-v02

# 2. System dep (RTK / rtree)
# Linux:  sudo apt-get install libspatialindex-dev
# macOS:  brew install spatialindex

# 3. Python (backend + tests + core)
python -m venv .venv && source .venv/bin/activate
pip install -e .

# 4. Node (web frontend)
cd web
npm install
# See also: optionalDependencies in package.json for rollup native
# binaries (auto-pulled on most platforms).

# 5. Confirm everything works
cd .. && pytest tests/ -v               # 97 tests should pass
cd web && npm run build                  # builds dist/
cd web && npm run lint                   # ESLint over the frontend
```

## 🧪 Run the dev environment

```bash
# Terminal 1: FastAPI backend on :8000
uvicorn api.main:app --reload --port 8000

# Terminal 2: React frontend on :5173 (Vite proxies /api → :8000)
cd web && npm run dev

# Optional Terminal 3: Streamlit (legacy, used by the maintainer)
streamlit run app.py
```

## ✏️ Where to put your change

| You want to… | File(s) |
|---|---|
| Fix a bug in bench detection | `core/param_extractor.py` + add a test in `tests/test_param_extractor.py` |
| Add a new endpoint | `api/routers/<topic>.py` + register in `api/main.py` + add a hook in `web/src/api/hooks.ts` |
| Add a new column to the Excel export | `core/excel_writer.py` + update `core/blast_correlation.py` if needed |
| Translate a new UI string | `web/src/locales/es.json` and `en.json` |
| Build a new wizard tab | `web/src/components/results/<tab>.tsx` + add to `lazy.ts` and `Step4Content.tsx` |
| Add a deploy step | update `.github/workflows/*.yml` and `render.yaml` |

## 🧪 Tests

- **Backend**: `pytest tests/ -v`. 97 tests as of writing.
- **Frontend**: ESLint via `npm run lint`. No unit tests yet — happy
  to accept a PR that adds Vitest + React Testing Library setup.
- **End-to-end**: `python test_pipeline.py` runs the full pipeline on
  synthetic surfaces; useful to confirm `core/` changes don't regress
  the canonical flow.

If your PR adds a new public function, **add a test** for it. If
your PR fixes a bug, **add a regression test**.

## 🎨 Code style

- **Python**: follow PEP 8; type hints on public functions; use the
  existing frozen dataclasses in `core/config.py` for defaults
  instead of magic numbers.
- **TypeScript**: strict mode; use `satisfies` for typed object
  literals; avoid `any` (we make one exception for the Cesium module
  whose .d.ts is broken).
- **CSS**: Tailwind utility classes; theme variables (`--color-*`,
  `--status-*`) instead of raw hex codes.
- **Commits**: conventional commits (`feat:`, `fix:`, `refactor:`,
  `test:`, `docs:`, `chore:`). No AI attribution. No `Co-Authored-By:`.

## 🧪 PR process

1. **Branch off main**: `git switch -c feat/short-description`.
2. **Keep changes focused**: one PR = one logical change. If your
   branch touches the API, update the corresponding client hook.
3. **Run the test suite** before pushing:
   ```bash
   pytest tests/ -v
   cd web && npm run build && npm run lint
   ```
4. **Fill the PR template** (auto-loaded). The user triages fast if
   the description is clear.
5. **CI must be green** before merge. The CI runs pytest, the React
   build, and a docker-compose smoke test.

## 🐛 Reporting bugs

Use the **Bug report** issue template. Include:
- Repro steps (ideally with a small STL/DXF you can share)
- What you expected vs what you got
- Browser + OS + console errors
- Whether demo mode repros the issue

## 💡 Feature requests

Use the **Feature request** issue template. Check existing issues
first; this saves everyone time. The maintainer curates
high-signal issues; please be specific about the problem you're
solving, not just the implementation.

## 🌍 Translations

We support Spanish (default) and English. To add a new string:

1. Add the key under the right namespace (`nav`, `common`, `demo`,
   `step1`, etc.) in **both** `web/src/locales/es.json` and
   `web/src/locales/en.json`.
2. Use it in the component: `const { t } = useTranslation(); t('key')`.
3. ICU plurals (`_one` / `_other`) for counts: `t('common.n_sections',
   { count: n })` resolves to `n_sections_one` for count=1,
   `n_sections_other` for the rest.

## 📜 License

By contributing, you agree your contributions will be licensed under
the project's **MIT License**.
