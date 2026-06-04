/**
 * Frontend observability — Sentry init + Plausible analytics.
 *
 * Both are opt-in: if the env var is not set, the corresponding
 * module is never loaded (no SDK ships to the browser, no
 * network call is made). This means the bundle and runtime
 * overhead of observability is exactly zero unless the
 * maintainer explicitly enables it.
 *
 * To enable, set:
 *   VITE_SENTRY_DSN=https://...@oXXX.ingest.sentry.io/YYY
 *   VITE_ANALYTICS_URL=https://plausible.io/js/script.js
 *     (or any custom analytics endpoint that hosts a script tag)
 *
 * Both env vars are also read from the deploy workflow at
 * .github/workflows/deploy-frontend.yml so the same value is
 * baked into the static bundle on every deploy.
 */
import * as Sentry from '@sentry/react';

const SENTRY_DSN = import.meta.env.VITE_SENTRY_DSN;
const ANALYTICS_URL = import.meta.env.VITE_ANALYTICS_URL;
const RELEASE = import.meta.env.VITE_RELEASE ?? 'conciliacion-geo-v02@dev';
const ENVIRONMENT = import.meta.env.MODE;  // 'production' | 'development'

/**
 * Initialise Sentry. We do this eagerly on module load (before
 * React renders) so the first-paint error from a bug in the
 * initial render still gets captured. If VITE_SENTRY_DSN is
 * unset, this is a no-op (Sentry module is imported but
 * never initialised).
 */
export function initObservability(): void {
  if (SENTRY_DSN) {
    Sentry.init({
      dsn: SENTRY_DSN,
      release: RELEASE,
      environment: ENVIRONMENT,
      // Performance monitoring sample rate. 10% of transactions
      // is plenty for a low-traffic app and keeps us well under
      // the 10K events/month free tier.
      tracesSampleRate: 0.1,
      // Session replay: only capture when the user actually
      // reports an issue (a session-replay URL is attached to
      // each error event). 0% baseline to stay under the
      // 5K replays/month free tier unless the maintainer
      // explicitly opts in.
      replaysSessionSampleRate: 0,
      replaysOnErrorSampleRate: 1.0,
      // Strip query strings from URLs (PII hygiene)
      beforeSendTransaction(event) {
        if (event.request?.url) {
          try {
            const u = new URL(event.request.url, window.location.origin);
            u.search = '';
            event.request.url = u.toString();
          } catch { /* ignore */ }
        }
        return event;
      },
    });
  } else if (typeof console !== 'undefined' && ENVIRONMENT === 'development') {
    // Friendly dev-time hint so we don't forget the env var exists
    console.info(
      '[observability] VITE_SENTRY_DSN not set — frontend error reporting disabled. ' +
      'See web/DEPLOY.md to enable Sentry.',
    );
  }

  if (ANALYTICS_URL) {
    injectAnalyticsScript(ANALYTICS_URL);
  }
}

/**
 * Plausible-style analytics: dynamic <script src> injection.
 * Most analytics providers (Plausible, Cloudflare Web
 * Analytics, Simple Analytics, GoatCounter) serve a single
 * script tag that self-initialises. We don't need their SDK
 * — just load the script.
 */
function injectAnalyticsScript(url: string): void {
  // The data-api attribute lets the script know which dashboard
  // the events belong to (used by Plausible and friends).
  const apiHost = (() => {
    try {
      return new URL(url).hostname;
    } catch {
      return '';
    }
  })();
  const s = document.createElement('script');
  s.defer = true;
  s.src = url;
  if (apiHost) {
    s.setAttribute('data-api', apiHost);
    s.setAttribute('data-domain', window.location.hostname);
  }
  document.head.appendChild(s);
}
