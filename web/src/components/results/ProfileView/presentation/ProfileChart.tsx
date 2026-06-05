/**
 * ProfileChart — the Plotly chart for the cross-section profile.
 *
 * Inputs:
 *  - `viewModel` (from useProfileViewModel)
 *  - `filterState` (from useFilterState)
 *  - `crossLink` (from useCrossLinkState) — for chart↔table hover/click
 *
 * Renders:
 *  - 2 baseline polylines: design (slate blue), topo (forest green)
 *  - 0-2 reconciled polylines (dashed) when toggled on
 *  - 0-1 area-fill polygon when toggled on
 *  - 1 bench-markers trace (or 4 — one per status — when
 *    showSemaphore is on) so each bench can be color-coded
 *
 * Interactions:
 *  - Hover a bench marker → crossLink.setHovered(benchNumber)
 *  - Click a bench marker → crossLink.setSelected(benchNumber)
 *  - When crossLink.hovered/selected changes, that bench's marker
 *    grows + gets a ring (the visual highlight comes from updating
 *    the marker's size and outline via a customdata lookup).
 *
 * Strictly read-only: no business logic in this file. The only
 * computation is "translate view model + filter state into Plotly
 * traces" — a pure function that can be tested independently.
 */

import { useEffect, useMemo, useRef, useCallback } from 'react';
import Plot from 'react-plotly.js';
import type { Data, Layout, Config } from 'plotly.js';
import {
  createPlotlyConfig,
  createPlotlyLayout,
  designLineStyle,
  topoLineStyle,
  reconciledLineStyle,
} from '../infrastructure/plotlyTheme';
import type { Bench, ProfileLine, ProfileViewModel } from '../domain/types';
import { type FilterState } from '../domain/filters';
import { type UseCrossLinkStateApi } from '../application';
import { STATUS_BG_VAR, STATUS_FG_VAR, STATUS_BORDER_VAR, STATUS_ICON } from '../domain/status';
import { useTheme } from '../../../../stores/theme';

export interface ProfileChartProps {
  readonly viewModel: ProfileViewModel;
  readonly filterState: FilterState;
  readonly crossLink: UseCrossLinkStateApi;
  /** Optional: Plotly height in px. Default 480. */
  readonly height?: number;
}

export function ProfileChart({ viewModel, filterState, crossLink, height = 480 }: ProfileChartProps) {
  const { isDark } = useTheme();
  const containerRef = useRef<HTMLDivElement | null>(null);

  // ── 1. Build the data array (pure derivation) ─────────────
  const data = useMemo<Data[]>(
    () => buildTraces(viewModel, filterState, crossLink, isDark),
    [viewModel, filterState, crossLink, isDark],
  );

  // ── 2. Build the layout (pure, depends on viewModel + theme) ─
  const layout = useMemo<Partial<Layout>>(() => {
    const base = createPlotlyLayout();
    // Compute explicit axis ranges from the data so the chart is
    // tight around the profile (no huge empty areas). We use
    // 8% padding on each side — enough to leave breathing room
    // without wasting viewport on whitespace.
    const { xRange, yRange } = computeAxisRanges(viewModel, height);
    return {
      ...base,
      // We extend the layout with view-model-specific bits: title
      // is rendered in SectionHeader (above), so plotly title is off.
      title: undefined,
      height,
      // CRITICAL: lock the y-axis to the x-axis scale (1:1). Both
      // are in metres, so 1m horizontal = 1m vertical. Without this,
      // Plotly auto-fits the y-axis range and the slope angles look
      // completely wrong (the mine cross-section appears flat when
      // it should be visibly steep). Streamlit's old code had this.
      yaxis: {
        ...(base.yaxis as Partial<Layout['yaxis']>),
        scaleanchor: 'x',
        scaleratio: 1,
        range: yRange,
      },
      xaxis: {
        ...(base.xaxis as Partial<Layout['xaxis']>),
        range: xRange,
      },
      // The chart's hover/click routing is handled by the onHover
      // and onClick callbacks we attach to the Plot component,
      // not by Plotly's built-in modes.
    };
  }, [height, viewModel]);

  const config = useMemo<Partial<Config>>(() => createPlotlyConfig(), []);

  // ── 3. Hover / click → crossLink state ────────────────────
  // react-plotly.js passes PlotMouseEvent (from plotly.js), which
  // has a `points` array. We extract the bench number from the
  // first point's customdata and route it to the cross-link state.
  type PlotPoint = { customdata?: unknown };
  type PlotMouse = { points?: PlotPoint[] };

  const extractFromPoints = (event: unknown): number | null => {
    const e = event as PlotMouse | undefined;
    const first = e?.points?.[0];
    if (!first) return null;
    return extractBenchNumber(first.customdata);
  };

  const onHover = useCallback(
    (event: unknown) => {
      const n = extractFromPoints(event);
      if (n !== null) crossLink.setHovered(n);
    },
    [crossLink],
  );

  const onUnhover = useCallback(() => {
    crossLink.setHovered(null);
  }, [crossLink]);

  const onClick = useCallback(
    (event: unknown) => {
      const n = extractFromPoints(event);
      if (n !== null) crossLink.setSelected(n);
    },
    [crossLink],
  );

  // ── 4. Container ref for sizing ────────────────────────────
  useEffect(() => {
    // No-op for now; react-plotly.js handles its own resize.
  }, []);

  return (
    <div
      ref={containerRef}
      data-slot="profile-chart"
      className="w-full"
      style={{ minHeight: height }}
    >
      <Plot
        data={data}
        layout={layout}
        config={config}
        onHover={onHover as never}
        onUnhover={onUnhover as never}
        onClick={onClick as never}
        style={{ width: '100%', height: '100%' }}
        useResizeHandler
      />
    </div>
  );
}

// ─── Pure: compute axis ranges ───────────────────────────────

/**
 * Derive the x/y axis ranges from the view model so the chart is
 * tight around the profile. Without this, Plotly's auto-fit adds
 * 50%+ whitespace, making the profile look like a tiny squiggle
 * lost in a sea of grid lines.
 *
 * @param paddingPct 0..1 — fraction of the data range to add on
 *  each side. 0.08 (8%) gives breathing room without waste.
 *
 * Falls back to a sensible default when there's no data.
 */
/**
 * Derive the x/y axis ranges from the view model so the chart is
 * tight around the profile. Without this, Plotly's auto-fit adds
 * 50%+ whitespace, making the profile look like a tiny squiggle
 * lost in a sea of grid lines.
 *
 * @param paddingPct 0..1 — fraction of the data range to add on
 *  each side. 0.08 (8%) gives breathing room without waste.
 *
 * Falls back to a sensible default when there's no data.
 */
export function computeAxisRanges(
  vm: ProfileViewModel,
  _height: number,
  paddingPct = 0.08,
): { xRange: [number, number]; yRange: [number, number] } {
  let xMin = Infinity, xMax = -Infinity, yMin = Infinity, yMax = -Infinity;
  for (const line of vm.lines) {
    for (const p of line.points) {
      if (Number.isFinite(p.distance)) {
        if (p.distance < xMin) xMin = p.distance;
        if (p.distance > xMax) xMax = p.distance;
      }
      if (Number.isFinite(p.elevation)) {
        if (p.elevation < yMin) yMin = p.elevation;
        if (p.elevation > yMax) yMax = p.elevation;
      }
    }
  }
  for (const b of vm.benches) {
    if (Number.isFinite(b.crestDistance)) {
      if (b.crestDistance < xMin) xMin = b.crestDistance;
      if (b.crestDistance > xMax) xMax = b.crestDistance;
    }
    if (Number.isFinite(b.toeDistance)) {
      if (b.toeDistance < xMin) xMin = b.toeDistance;
      if (b.toeDistance > xMax) xMax = b.toeDistance;
    }
    if (Number.isFinite(b.crestElevation)) {
      if (b.crestElevation < yMin) yMin = b.crestElevation;
      if (b.crestElevation > yMax) yMax = b.crestElevation;
    }
    if (Number.isFinite(b.toeElevation)) {
      if (b.toeElevation < yMin) yMin = b.toeElevation;
      if (b.toeElevation > yMax) yMax = b.toeElevation;
    }
  }

  // Fallback for empty data: a 100m × 30m default.
  if (!Number.isFinite(xMin) || !Number.isFinite(xMax)) {
    return { xRange: [0, 100], yRange: [0, 30] };
  }
  if (!Number.isFinite(yMin) || !Number.isFinite(yMax)) {
    yMin = xMin;
    yMax = xMin + 1;
  }

  const xSpan = xMax - xMin;
  const ySpan = yMax - yMin;
  // For the y-axis, ensure at least a 20m window — many real
  // benches have only a few metres of elevation change, and
  // a 2m range with 1:1 scaleanchor would render the whole
  // profile in a 2m wide strip horizontally.
  const minYSpan = 20;
  const ySpanFinal = Math.max(ySpan, minYSpan);
  const yMid = (yMin + yMax) / 2;
  const yMinFinal = yMid - ySpanFinal / 2;
  const yMaxFinal = yMid + ySpanFinal / 2;

  return {
    xRange: [xMin - xSpan * paddingPct, xMax + xSpan * paddingPct],
    yRange: [yMinFinal - ySpanFinal * paddingPct, yMaxFinal + ySpanFinal * paddingPct],
  };
}

// ─── Pure: build Plotly traces ───────────────────────────────

/**
 * Translates the view model + filter state + cross-link state into
 * a Plotly Data[]. Pure: same inputs → same output. Memoised by
 * the caller.
 *
 * Exported for unit testing — this is the bulk of the chart's
 * logic. The React component above is a thin wrapper.
 */
export function buildTraces(
  vm: ProfileViewModel,
  filterState: FilterState,
  crossLink: UseCrossLinkStateApi,
  isDark: boolean,
): Data[] {
  const traces: Data[] = [];

  // 1. Area fill between design and topo (when showAreas)
  if (filterState.showAreas) {
    const design = vm.lines.find((l) => l.kind === 'design');
    const topo = vm.lines.find((l) => l.kind === 'topo');
    if (design && topo && design.points.length === topo.points.length) {
      traces.push(buildAreaFill(design, topo, isDark));
    }
  }

  // 2. Design polyline (always, if data exists)
  const design = vm.lines.find((l) => l.kind === 'design');
  if (design && design.points.length > 0) {
    traces.push(buildPolyline(design, 'Diseño', designLineStyle()));
  }

  // 3. Topo polyline (always, if data exists)
  const topo = vm.lines.find((l) => l.kind === 'topo');
  if (topo && topo.points.length > 0) {
    traces.push(buildPolyline(topo, 'Topografía', topoLineStyle()));
    // Subtle "ground" fill under the topo line so the profile
    // doesn't look like a floating squiggle. Uses 'tozeroy' to
    // fill down to y=0 of the axis (the y range is set tight so
    // this looks like filling the area below the profile).
    traces.push(buildGroundFill(topo, isDark));
  }

  // 4. Reconciled design (when toggled on, if data exists)
  if (filterState.showReconciledDesign) {
    const rd = vm.lines.find((l) => l.kind === 'reconciled_design');
    if (rd && rd.points.length > 0) {
      traces.push(buildPolyline(rd, 'Diseño (reconciliado)', reconciledLineStyle()));
    }
  }

  // 5. Reconciled topo (when toggled on, if data exists)
  if (filterState.showReconciledTopo) {
    const rt = vm.lines.find((l) => l.kind === 'reconciled_topo');
    if (rt && rt.points.length > 0) {
      traces.push(buildPolyline(rt, 'Topografía (reconciliada)', reconciledLineStyle()));
    }
  }

  // 6. Bench markers — split by status when showSemaphore, else one trace
  traces.push(...buildBenchMarkers(vm.benches, filterState, crossLink));

  return traces;
}

function buildPolyline(
  line: ProfileLine,
  name: string,
  style: Partial<Plotly.ScatterLine>,
): Partial<Plotly.PlotData> {
  return {
    type: 'scatter',
    mode: 'lines',
    name,
    x: line.points.map((p) => p.distance),
    y: line.points.map((p) => p.elevation),
    line: style,
    hovertemplate: '%{x:.1f} m, %{y:.1f} m<extra>' + name + '</extra>',
    showlegend: true,
  };
}

function buildGroundFill(
  topo: ProfileLine,
  isDark: boolean,
): Partial<Plotly.PlotData> {
  // We use 'tozeroy' which fills down to the y-axis minimum. The
  // y-axis is already set tight to the data, so the fill visually
  // anchors the topography to the bottom of the chart. Very
  // subtle green so it never competes with the actual lines.
  return {
    type: 'scatter',
    mode: 'lines',
    name: 'Terreno',
    x: topo.points.map((p) => p.distance),
    y: topo.points.map((p) => p.elevation),
    fill: 'tozeroy',
    fillcolor: isDark ? 'rgba(46,125,50,0.06)' : 'rgba(46,125,50,0.04)',
    line: { color: 'transparent', width: 0 },
    hovertemplate: 'skip',
    hoverinfo: 'skip',
    showlegend: false,
  };
}

function buildAreaFill(
  design: ProfileLine,
  topo: ProfileLine,
  isDark: boolean,
): Partial<Plotly.PlotData> {
  // Construct a closed polygon: design forward, topo reverse.
  // The fill colour is a very subtle green so it never competes
  // visually with the actual polylines.
  const x = [
    ...design.points.map((p) => p.distance),
    ...topo.points.map((p) => p.distance).reverse(),
  ];
  const y = [
    ...design.points.map((p) => p.elevation),
    ...topo.points.map((p) => p.elevation).reverse(),
  ];
  return {
    type: 'scatter',
    mode: 'lines',
    name: 'Desviación',
    x,
    y,
    fill: 'toself',
    fillcolor: isDark ? 'rgba(46,125,50,0.10)' : 'rgba(46,125,50,0.08)',
    line: { color: 'transparent', width: 0 },
    hovertemplate: 'skip',
    hoverinfo: 'skip',
    showlegend: false,
  };
}

function buildBenchMarkers(
  benches: readonly Bench[],
  filterState: FilterState,
  crossLink: UseCrossLinkStateApi,
): Partial<Plotly.PlotData>[] {
  if (benches.length === 0) return [];

  const traceColor = (status: Bench['status']): string =>
    resolveCssVar(STATUS_FG_VAR[status], isDarkFallback(status));
  const traceBorder = (status: Bench['status']): string =>
    resolveCssVar(STATUS_BORDER_VAR[status], '#e5e7eb');
  const fillColor = (status: Bench['status']): string =>
    resolveCssVar(STATUS_BG_VAR[status], '#f3f4f6');

  const makeTrace = (
    name: string,
    matched: readonly Bench[],
  ): Partial<Plotly.PlotData> => {
    const x = matched.map((b) => b.crestDistance);
    const y = matched.map((b) => b.crestElevation);
    const customdata = matched.map((b) => b.benchNumber);
    const text = matched.map((b) => `${STATUS_ICON[b.status]} ${b.benchNumber}`);
    // Highlight the currently-hovered or selected bench.
    const sizes = matched.map((b) => {
      if (crossLink.selected === b.benchNumber) return 16;
      if (crossLink.hovered === b.benchNumber) return 14;
      return 10;
    });
    const lineWidths = matched.map((b) => {
      if (crossLink.selected === b.benchNumber) return 3;
      if (crossLink.hovered === b.benchNumber) return 2.5;
      return 2;
    });
    return {
      type: 'scatter',
      mode: 'text+markers',
      name,
      x,
      y,
      customdata,
      text,
      textposition: 'top center',
      textfont: { size: 10, color: traceColor(matched[0]!.status) },
      marker: {
        size: sizes,
        color: matched.map((b) => fillColor(b.status)),
        line: {
          color: matched.map((b) => traceBorder(b.status)),
          width: lineWidths,
        },
        symbol: 'circle',
      },
      hovertemplate: makeHoverTemplate(matched),
      showlegend: false,
    };
  };

  if (filterState.showSemaphore) {
    // One trace per status (matches the design — each colour group
    // can be hidden independently via Plotly's legend).
    const groups = new Map<Bench['status'], Bench[]>();
    for (const b of benches) {
      if (!groups.has(b.status)) groups.set(b.status, []);
      groups.get(b.status)!.push(b);
    }
    return Array.from(groups.entries()).map(([status, list]) =>
      makeTrace(statusName(status), list),
    );
  }

  // Default: one trace, all benches with their natural colour.
  return [makeTrace('Bancos', benches)];
}

function statusName(status: Bench['status']): string {
  switch (status) {
    case 'CUMPLE': return 'Cumple';
    case 'FUERA': return 'Fuera';
    case 'NO_CUMPLE': return 'No cumple';
    case 'UNKNOWN': return 'Sin datos';
  }
}

function makeHoverTemplate(benches: readonly Bench[]): string {
  // Plotly lets us pass a per-point template via %{customdata}.
  // We just return a static template — the rich data goes in
  // a tooltip rendered by us on hover, not in the Plotly default
  // bubble. Simpler, less to maintain.
  void benches;
  return '%{text}<br>%{x:.1f} m, %{y:.1f} m<extra></extra>';
}

function extractBenchNumber(customdata: unknown): number | null {
  if (typeof customdata === 'number' && Number.isFinite(customdata)) return customdata;
  if (Array.isArray(customdata) && typeof customdata[0] === 'number') {
    return customdata[0];
  }
  return null;
}

// ─── CSS var resolution (client-side, runtime) ──────────────

function resolveCssVar(value: string, fallback: string): string {
  if (typeof window === 'undefined' || !value.startsWith('var(')) return fallback;
  const name = value.slice(4, value.lastIndexOf(')')).trim();
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function isDarkFallback(status: Bench['status']): string {
  return status === 'CUMPLE' ? '#10b981' : status === 'FUERA' ? '#f59e0b' : status === 'NO_CUMPLE' ? '#ef4444' : '#9ca3af';
}
