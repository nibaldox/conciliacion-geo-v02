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

## Observability

All observability is **opt-in**. The site ships with zero telemetry
by default — to enable anything, set the env var in your deploy
provider.

### Sentry (errors + performance)

Sentry is the most actionable tool: it captures uncaught
exceptions, slow transactions, and console errors. Free tier is
5K errors/month + 10K transactions/month, plenty for a
small app.

**1. Create a Sentry project** at [sentry.io](https://sentry.io) →
New Project → JavaScript (browser) for the frontend, and
Python (FastAPI) for the backend. You'll get a DSN that looks
like `https://abc123@o987.ingest.sentry.io/123`.

**2. Frontend** — set `VITE_SENTRY_DSN` as a GitHub Actions
secret (Settings → Secrets → Actions → New repository
secret). The next push to `main` bakes it into the bundle.
Alternatively, set it in the `vars.VITE_SENTRY_DSN` GitHub
environment variable for non-sensitive defaults.

**3. Backend** — set `SENTRY_DSN` in Render → Environment
(also set `SENTRY_ENVIRONMENT=production`). The next deploy
will start sending errors.

**4. Test it** — throw a test exception in your browser console:
```js
throw new Error('test')
```
It should appear in your Sentry dashboard within ~30s.

### UptimeRobot (is the site up?)

Free plan: monitor up to 50 URLs, 5-minute interval, email/SMS
alerts. Setup:

1. Create a free account at [uptimerobot.com](https://uptimerobot.com).
2. **Add New Monitor → HTTP(s)**.
3. **URL**: `https://conciliacion-api.onrender.com/api/v1/health`
   (use your actual Render URL).
4. **Monitoring interval**: 5 minutes (free tier limit).
5. **Alert contacts**: add your email.

The `/api/v1/health` endpoint returns `{"status":"ok","version":"..."}`
when up. UptimeRobot will alert you within ~5 min if it goes
down. (The Render free tier sleeps after 15 min of inactivity,
so the first request after a quiet period takes 30-60s —
consider setting UptimeRobot to a 5-min interval, not 1-min, to
avoid false alerts during cold starts.)

For a public status page, point a custom domain at
[BetterUptime](https://betteruptime.com) (also free, nicer UI).

### Plausible-style analytics (privacy-friendly visitor count)

We support any self-hosted or SaaS analytics that loads a single
`<script src=...>` tag. No cookie banner required (these tools are
GDPR-compliant by design).

**Plausible** (recommended, paid SaaS but very cheap — $9/mo
for 100K events, or self-host the open-source version free):

1. Sign up at [plausible.io](https://plausible.io), add your
   domain (`nibaldox.github.io` and/or your custom domain).
2. Plausible gives you a snippet like
   `https://plausible.io/js/script.js`. Set that as
   `VITE_ANALYTICS_URL` in GitHub Secrets.

**Alternatives** that work with the same `VITE_ANALYTICS_URL` slot:
- **Cloudflare Web Analytics** — free if your DNS is on
  Cloudflare; the beacon is at
  `https://static.cloudflareinsights.com/beacon.min.js`.
- **GoatCounter** — free, open source, self-hostable.
- **Simple Analytics** — paid but very privacy-friendly.

To disable analytics entirely, leave `VITE_ANALYTICS_URL` unset.

### What gets sent where

| Event | Frontend → | Backend → |
|---|---|---|
| Uncaught JS exception | Sentry (if `VITE_SENTRY_DSN` set) | — |
| Unhandled rejection | Sentry | Sentry (if `SENTRY_DSN` set) |
| Page view | Plausible (if `VITE_ANALYTICS_URL` set) | — |
| API request timing | Sentry (10% sample) | Sentry (10% sample) |
| API error (4xx/5xx) | — | Sentry (5xx only) |
| Health check (`/api/v1/health`) | — | UptimeRobot only — not sent to Sentry |

Mesh file names and uploaded data **never** leave your server
(Sentry has `send_default_pii=False` on the backend integration;
the frontend strips query strings before sending).

