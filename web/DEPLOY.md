# Deploy

This repo ships a React/Vite SPA. GitHub Pages hosts the static bundle;
the FastAPI backend runs on Render.com (free tier). Architecture:

```
┌──────────────────────────────────────┐
│  GitHub Pages (static)               │
│  nibaldox.github.io/conciliacion-    │
│  geo-v02/                            │
└──────────────┬───────────────────────┘
               │ CORS allowlist
               ▼
┌──────────────────────────────────────┐
│  Render.com (FastAPI + Docker)       │
│  conciliacion-api.onrender.com       │
└──────────────┬───────────────────────┘
               │
       ┌───────┴────────┐
       ▼                ▼
   SQLite (sessions)  /data/*.stl (mesh BLOB)
```

## Frontend → GitHub Pages

### One-time setup (in GitHub repo Settings)

1. **Settings → Pages**
   - **Source**: "GitHub Actions"
   - Don't set a custom branch — the workflow deploys directly.

2. **Settings → Secrets and variables → Actions → New repository secret**
   (only if you're not using defaults)
   - `VITE_BASE` — `"/"` for custom domain, `"/conciliacion-geo-v02/"` for
     the default project page. **Default is fine** if you don't set it.
   - `VITE_API_URL` — full URL of the backend
     (e.g. `https://conciliacion-api.onrender.com`). Default points to
     the not-yet-deployed Render service.

3. **Settings → Environments → github-pages**
   - Deployment branches: only `main`.

### Automatic deploy

Every push to `main` runs `.github/workflows/deploy-frontend.yml`:

1. `npm ci` in `web/`
2. `tsc --noEmit`
3. `npm run build` (Vite produces `web/dist/`)
4. Copy `dist/index.html` → `dist/404.html` (SPA fallback for unknown
   routes — the client router takes over)
5. Upload as Pages artifact
6. Deploy to GitHub Pages

A `workflow_dispatch` trigger is also available for manual deploys from
the Actions tab.

### Custom domain

If you point a custom domain at the GH Pages site:

1. Drop a `CNAME` file in `web/public/` with your domain on a single
   line. The Vite plugin will copy it to `dist/`.
2. In repo Settings → Pages → Custom domain, enter the same domain.
3. Set `VITE_BASE` to `"/"` in repo secrets so assets resolve from
   the root path instead of `/conciliacion-geo-v02/`.
4. In your DNS provider, add a CNAME pointing the domain to
   `nibaldox.github.io`.

## Backend → Render.com

A `render.yaml` lives in the repo root (added in Phase 2). Render
auto-detects it and creates the service on first push to `main`.

Once deployed, the backend URL is `https://<service-name>.onrender.com`.
Configure CORS via the `CONCILIACION_CORS_ORIGINS` env var (comma-
separated list of allowed origins) — see `api/main.py`.

## Local testing of the production build

```bash
cd web
npm run build
npm run preview    # serves dist/ on :4173, no API proxy
```

For end-to-end with the backend:

```bash
# Terminal 1
cd api && uvicorn api.main:app --reload --port 8000

# Terminal 2
cd web && VITE_API_URL=http://localhost:8000 npm run dev
```
