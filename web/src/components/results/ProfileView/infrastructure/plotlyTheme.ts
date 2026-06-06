/**
 * Plotly theme factory.
 *
 * Centralises every Plotly default we override so the chart never
 * ships with plotly.js's default white-on-white look. The theme is
 * driven by CSS variables so it adapts to dark mode automatically
 * and respects whatever the design system decides to change.
 */

import type { Layout, Config, ScatterLine, ScatterMarker } from 'plotly.js';
import type { BenchStatus } from '../domain/types';
import { STATUS_FG_VAR, STATUS_BORDER_VAR } from '../domain/status';


/** Resolved theme tokens. We read CSS variables at runtime via
 *  getComputedStyle so the chart re-themes if the user toggles
 *  dark mode mid-session. */
function resolveTokens(): {
  bg: string;
  surface: string;
  textPrimary: string;
  textMuted: string;
  gridLine: string;
  designLine: string;
  topoLine: string;
  reconciledDash: string;
  fontFamily: string;
} {
  if (typeof window === 'undefined') {
    // SSR safety — fall back to a safe dark theme (matches the
    // Mission Control aesthetic that's the default in :root).
    return {
      bg: 'transparent',
      surface: '#0a0e14',
      textPrimary: '#f5f5f5',
      textMuted: '#6b7280',
      gridLine: 'rgba(255,255,255,0.08)',
      designLine: '#3b82f6',
      topoLine: '#10b981',
      reconciledDash: '#94a3b8',
      fontFamily: 'system-ui, -apple-system, sans-serif',
    };
  }
  const cs = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) =>
    cs.getPropertyValue(name).trim() || fallback;
  return {
    bg: 'transparent',
    surface: read('--color-surface', '#0a0e14'),
    textPrimary: read('--color-text-primary', '#f5f5f5'),
    textMuted: read('--color-text-muted', '#6b7280'),
    gridLine: read('--color-border', 'rgba(255,255,255,0.08)'),
    designLine: read('--color-mine-blue', '#3b82f6'),
    topoLine: read('--color-mine-green', '#10b981'),
    reconciledDash: read('--color-text-muted', '#94a3b8'),
    fontFamily: read(
      '--font-sans',
      'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    ),
  };
}

// ─── Public factory ─────────────────────────────────────────

/** Default Plotly `Config` for the profile chart. */
export function createPlotlyConfig(): Partial<Config> {
  return {
    displaylogo: false,
    displayModeBar: false,  // hide the ⚙️ modeBar entirely — we have
                            // our own cross-link UI and prev/next nav
    responsive: true,
    toImageButtonOptions: {
      format: 'png' as const,
      filename: 'cross_section',
      scale: 2,
    },
  };
}

/** Default Plotly `Layout` for the profile chart. */
export function createPlotlyLayout(): Partial<Layout> {
  const t = resolveTokens();
  return {
    paper_bgcolor: t.bg,
    plot_bgcolor: t.bg,
    font: { family: t.fontFamily, color: t.textPrimary, size: 12 },
    margin: { l: 60, r: 24, t: 16, b: 56 },
    showlegend: true,
    legend: {
      orientation: 'h',
      x: 0,
      xanchor: 'left',
      y: -0.18,
      yanchor: 'top',
      font: { size: 11, color: t.textMuted },
      bgcolor: 'transparent',
    },
    xaxis: {
      title: { text: 'Distance (m)', font: { size: 11, color: t.textMuted } },
      showgrid: false, // We only show horizontal gridlines
      zeroline: false,
      showline: true,
      linecolor: t.gridLine,
      tickfont: { size: 10, color: t.textMuted },
      ticks: 'outside',
      ticklen: 4,
      tickcolor: t.gridLine,
    },
    yaxis: {
      title: { text: 'Elevation (m)', font: { size: 11, color: t.textMuted } },
      showgrid: true,
      gridcolor: t.gridLine,
      gridwidth: 1,
      zeroline: false,
      showline: true,
      linecolor: t.gridLine,
      tickfont: { size: 10, color: t.textMuted },
      ticks: 'outside',
      ticklen: 4,
      tickcolor: t.gridLine,
    },
    hoverlabel: {
      bgcolor: t.surface,
      bordercolor: t.gridLine,
      font: { family: t.fontFamily, size: 12, color: t.textPrimary },
    },
    // Default range — caller may override.
  };
}

// ─── Line style helpers ─────────────────────────────────────

/** Style for the design polyline. */
export function designLineStyle(): Partial<ScatterLine> {
  const t = resolveTokens();
  return { color: t.designLine, width: 3, shape: 'linear' };
}

/** Style for the topo polyline. */
export function topoLineStyle(): Partial<ScatterLine> {
  const t = resolveTokens();
  return { color: t.topoLine, width: 3, shape: 'linear' };
}

/** Style for reconciled (dashed) polylines — amber so it contrasts
 *  clearly against design (blue) and topo (green). */
export function reconciledLineStyle(): Partial<ScatterLine> {
  return { color: '#f59e0b', width: 2, dash: 'dash', shape: 'linear' };
}

/** Style for the reconciled topo polyline — solid amber, thinner than
 *  the primary topo so it reads as a "derived" version of it. */
export function reconciledTopoLineStyle(): Partial<ScatterLine> {
  return { color: '#f59e0b', width: 2, shape: 'linear' };
}

/** Marker style for a bench crest, color-coded by status. */
export function benchMarkerStyle(status: BenchStatus): Partial<ScatterMarker> {
  return {
    color: statusColor(status),
    size: 10,
    line: { color: statusBorderColor(status), width: 2 },
    symbol: 'circle',
  };
}

// ─── Color helpers (resolved at call time so dark mode works) ─

function statusColor(status: BenchStatus): string {
  return cssVar(STATUS_FG_VAR[status], '#6b7280');
}

function statusBorderColor(status: BenchStatus): string {
  return cssVar(STATUS_BORDER_VAR[status], '#e5e7eb');
}

function cssVar(value: string, fallback: string): string {
  if (typeof window === 'undefined' || !value.startsWith('var(')) return fallback;
  const name = value.slice(4, value.lastIndexOf(')')).trim();
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}
