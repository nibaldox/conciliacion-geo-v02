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

import { useEffect, useMemo, useRef, useCallback, useState } from 'react';
import Plot from 'react-plotly.js';
import type { Data, Layout, Config } from 'plotly.js';
import {
  createPlotlyConfig,
  createPlotlyLayout,
  designLineStyle,
  topoLineStyle,
  reconciledTopoLineStyle,
} from '../infrastructure/plotlyTheme';

import type { Bench, ProfileLine, ProfileViewModel, ProfilePoint } from '../domain/types';
import { type FilterState } from '../domain/filters';
import { type UseCrossLinkStateApi } from '../application';
import type { SpillBench } from '../domain/mapping';
import { STATUS_BG_VAR, STATUS_FG_VAR, STATUS_BORDER_VAR, STATUS_ICON } from '../domain/status';
import { useTheme } from '../../../../stores/theme';
import { useSession } from '../../../../stores/session';
import { useBlastHoles } from '../../../../api/hooks';
import type { BlastHoleOnProfile } from '../../../../api/types';

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
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 });

  // Blast holes: projected markers from the backend. The hook is
  // enabled only when the user toggles `showBlastHoles` on. Mesh id
  // comes from the session store (topo = as-built, which is what
  // blast holes are drilled into). `buildTraces` receives the raw
  // holes array so it stays a pure, testable function.
  const topoMeshId = useSession((s) => s.topoMeshId);
  const blastQuery = useBlastHoles(
    viewModel.section.id,
    topoMeshId,
    filterState.blastTolerance,
    filterState.showBlastHoles,
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    let rafId = 0;
    // Throttle resize via requestAnimationFrame coalescing so that
    // continuous drags (e.g. sidebar resize) don't trigger a full
    // Plotly recompute + re-render per pixel.
    const observer = new ResizeObserver(() => {
      if (rafId) return;
      rafId = requestAnimationFrame(() => {
        rafId = 0;
        const rect = el.getBoundingClientRect();
        setContainerSize({ width: rect.width, height: rect.height });
      });
    });
    observer.observe(el);
    return () => {
      if (rafId) cancelAnimationFrame(rafId);
      observer.disconnect();
    };
  }, []);

  // ── 1. Build the data array (pure derivation) ─────────────
  const blastHoles = blastQuery.data?.holes;
  const data = useMemo<Data[]>(
    () => buildTraces(viewModel, filterState, crossLink, isDark, blastHoles),
    [viewModel, filterState, crossLink, isDark, blastHoles],
  );

  // ── 2. Build the layout (pure, depends on viewModel + theme) ─
  const layout = useMemo<Partial<Layout>>(() => {
    const base = createPlotlyLayout();
    // Compute explicit axis ranges from the data so the chart is
    // tight around the profile (no huge empty areas). We use
    // 8% padding on each side — enough to leave breathing room
    // without wasting viewport on whitespace.
    const { xRange, yRange } = computeAxisRanges(viewModel, height);

    // G08: toe annotations (B1', B2', ...) and berm shape indicators
    // (dashed horizontal lines at each bench's toe elevation) are gated
    // by the existing `showReconciledTopo` toggle — they only make
    // sense when looking at the reconciled profile. Both helpers are
    // pure so they're independently testable.
    const annotations = buildAnnotations(viewModel, filterState.showReconciledTopo);
    const shapes = filterState.showReconciledTopo ? buildBermShapes(viewModel) : [];

    return {
      ...base,
      // We extend the layout with view-model-specific bits: title
      // is rendered in SectionHeader (above), so plotly title is off.
      title: undefined,
      autosize: true,
      annotations,
      shapes,
      yaxis: {
        ...(base.yaxis as Partial<Layout['yaxis']>),
        scaleanchor: 'x',
        scaleratio: computeScaleRatio(xRange, yRange, containerSize.width, containerSize.height),
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
  }, [height, viewModel, containerSize, filterState.showReconciledTopo]);

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
      className="w-full h-full"
      style={{ minHeight: '400px' }}
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

/**
 * Computes a fixed scaleratio based on the container dimensions so that
 * the profile fills the screen (vertical exaggeration) but maintains a
 * locked ratio when the user zooms in/out.
 */
function computeScaleRatio(
  xRange: [number, number],
  yRange: [number, number],
  containerWidth: number,
  containerHeight: number,
): number {
  if (containerWidth <= 0 || containerHeight <= 0) return 1;

  // Plotly margins defined in plotlyTheme.ts
  const horizontalMargins = 60 + 24; // l: 60, r: 24
  const verticalMargins = 16 + 56;   // t: 16, b: 56

  const plotWidth = Math.max(1, containerWidth - horizontalMargins);
  const plotHeight = Math.max(1, containerHeight - verticalMargins);

  const xSpan = Math.abs(xRange[1] - xRange[0]);
  const ySpan = Math.abs(yRange[1] - yRange[0]);

  if (xSpan === 0 || ySpan === 0) return 1;

  // Ratio = (pixels per unit Y) / (pixels per unit X)
  return (plotHeight / ySpan) / (plotWidth / xSpan);
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
  blastHoles?: readonly BlastHoleOnProfile[],
): Data[] {
  const traces: Data[] = [];

  // 1. Area fill between design and topo (when showAreas)
  if (filterState.showAreas) {
    const design = vm.lines.find((l) => l.kind === 'design');
    const topo = vm.lines.find((l) => l.kind === 'topo');
    if (design && design.points.length > 1 && topo && topo.points.length > 1) {
      traces.push(...buildAreaFills(design, topo, isDark));
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

  // 4. Reconciled lines — dashed royalblue design + solid amber topo
  if (filterState.showReconciledDesign) {
    const rd = vm.lines.find((l) => l.kind === 'reconciled_design');
    if (rd && rd.points.length > 0) {
      traces.push(
        buildPolyline(rd, 'Diseño (reconciliado)', {
          color: 'royalblue',
          width: 2,
          dash: 'dash',
          shape: 'linear',
        }),
      );
    }
  }

  if (filterState.showReconciledTopo) {
    const rt = vm.lines.find((l) => l.kind === 'reconciled_topo');
    if (rt && rt.points.length > 0) {
      traces.push(buildPolyline(rt, 'Topografía (reconciliada)', reconciledTopoLineStyle()));
    }
  }

  // 5. Spill areas — filled rectangles per bench with spill data
  if (filterState.showSpillAreas) {
    traces.push(...buildSpillAreaTraces(vm.benches));
  }

  // 6. Bench markers — split by status when showSemaphore, else one trace
  traces.push(...buildBenchMarkers(vm.benches, filterState, crossLink));

  // 7. Blast-hole markers — projected pozos de tronadura.
  //    The caller passes these in from the `useBlastHoles` hook;
  //    undefined/empty is the no-data case and emits nothing.
  if (blastHoles && blastHoles.length > 0) {
    traces.push(buildBlastHolesTrace(blastHoles));
  }

  return traces;
}

// ─── Pure: bench annotations + berm shapes (G08) ────────────

/**
 * Build Plotly layout shapes for berms — the horizontal dashed
 * segments that connect each bench's toe to the next bench's crest,
 * drawn at the toe elevation of the originating bench. Mirrors the
 * dashed berm indicators in `ui/tabs/profiles.py::_add_berm_width_indicators`.
 *
 * Returns N-1 shapes for N benches (the last bench has no successor,
 * so no berm can be drawn from it). Pure: same `vm` → same output.
 *
 * Exported for unit testing.
 */
export function buildBermShapes(
  vm: ProfileViewModel,
): Partial<Plotly.Shape>[] {
  const shapes: Partial<Plotly.Shape>[] = [];
  const benches = vm.benches;
  for (let i = 0; i < benches.length - 1; i++) {
    const bench = benches[i]!;
    const next = benches[i + 1]!;
    shapes.push({
      type: 'line',
      x0: bench.toeDistance,
      x1: next.crestDistance,
      y0: bench.toeElevation,
      y1: bench.toeElevation,
      line: { color: '#888', width: 2, dash: 'dot' },
    });
  }
  return shapes;
}

/**
 * Build Plotly annotations for bench toe labels (`B1'`, `B2'`, ...).
 *
 * The prime distinguishes toe labels from crest labels — the bench
 * marker trace already renders each bench number as `B{n}` text at
 * the crest, so the toe annotation uses `B{n}'` to mark the pie (toe)
 * without colliding with the crest label. Mirrors Streamlit's `Pa{n}`
 * toe annotations in `ui/tabs/profiles.py`.
 *
 * Returns one annotation per bench when `showAnnotations` is true,
 * otherwise an empty array. Pure: same inputs → same output.
 *
 * Exported for unit testing.
 */
export function buildAnnotations(
  vm: ProfileViewModel,
  showAnnotations: boolean,
): Partial<Plotly.Annotations>[] {
  if (!showAnnotations) return [];
  const annotations: Partial<Plotly.Annotations>[] = [];
  for (const bench of vm.benches) {
    annotations.push({
      x: bench.toeDistance,
      y: bench.toeElevation,
      text: `B${bench.benchNumber}'`,
      showarrow: false,
      font: { size: 10, color: '#888' },
    });
  }
  return annotations;
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

function buildAreaFills(
  design: ProfileLine,
  topo: ProfileLine,
  isDark: boolean,
): Partial<Plotly.PlotData>[] {
  const xSet = new Set<number>([
    ...design.points.map((p) => p.distance),
    ...topo.points.map((p) => p.distance)
  ]);
  const xAll = Array.from(xSet).sort((a, b) => a - b);

  function interp(x: number, pts: readonly ProfilePoint[]): number {
    if (pts.length === 0) return NaN;
    if (x <= pts[0]!.distance) return pts[0]!.elevation;
    if (x >= pts[pts.length - 1]!.distance) return pts[pts.length - 1]!.elevation;
    for (let i = 0; i < pts.length - 1; i++) {
      const p1 = pts[i]!;
      const p2 = pts[i + 1]!;
      if (x >= p1.distance && x <= p2.distance) {
        if (p2.distance === p1.distance) return p1.elevation;
        const t = (x - p1.distance) / (p2.distance - p1.distance);
        return p1.elevation + t * (p2.elevation - p1.elevation);
      }
    }
    return NaN;
  }

  const z_ref = xAll.map(x => interp(x, design.points));
  const z_eval = xAll.map(x => interp(x, topo.points));

  const y_deuda = xAll.map((_, i) => Math.max(z_eval[i]!, z_ref[i]!));
  const y_sobrexcavacion = xAll.map((_, i) => Math.min(z_eval[i]!, z_ref[i]!));

  return [
    {
      type: 'scatter',
      mode: 'lines',
      x: xAll,
      y: z_ref,
      line: { width: 0 },
      showlegend: false,
      hoverinfo: 'skip',
    },
    {
      type: 'scatter',
      mode: 'lines',
      name: 'Deuda',
      x: xAll,
      y: y_deuda,
      fill: 'tonexty',
      fillcolor: isDark ? 'rgba(59,130,246,0.25)' : 'rgba(59,130,246,0.3)',
      line: { width: 0 },
      showlegend: true,
      hovertemplate: 'skip',
      hoverinfo: 'skip',
    },
    {
      type: 'scatter',
      mode: 'lines',
      x: xAll,
      y: z_ref,
      line: { width: 0 },
      showlegend: false,
      hoverinfo: 'skip',
    },
    {
      type: 'scatter',
      mode: 'lines',
      name: 'Sobrexcavación',
      x: xAll,
      y: y_sobrexcavacion,
      fill: 'tonexty',
      fillcolor: isDark ? 'rgba(239,68,68,0.25)' : 'rgba(239,68,68,0.3)',
      line: { width: 0 },
      showlegend: true,
      hovertemplate: 'skip',
      hoverinfo: 'skip',
    }
  ];
}

function buildSpillAreaTraces(
  benches: readonly Bench[],
): Partial<Plotly.PlotData>[] {
  const traces: Partial<Plotly.PlotData>[] = [];
  for (const bench of benches) {
    // mapping.ts guarantees the spill fields at runtime via SpillBench;
    // the cast is safe and degrades to "skip" for fixtures without them.
    const sb = bench as SpillBench;
    const width = sb.spillWidth;
    const startD = sb.spillStartDistance;
    const startE = sb.spillStartElevation;
    if (width == null || startD == null || startE == null) continue;
    if (!Number.isFinite(width) || width <= 0) continue;
    if (!Number.isFinite(startD) || !Number.isFinite(startE)) continue;
    const endD = startD + width;
    const toeEl = bench.toeElevation;
    traces.push({
      type: 'scatter',
      mode: 'lines',
      name: 'Derrame',
      x: [startD, endD, endD, startD],
      y: [startE, startE, toeEl, toeEl],
      fill: 'toself',
      fillcolor: 'rgba(255, 100, 100, 0.3)',
      line: { color: 'rgba(255, 100, 100, 0.6)', width: 1 },
      hovertext: `Spill bench ${bench.benchNumber}`,
      hoverinfo: 'skip',
      showlegend: false,
    });
  }
  return traces;
}

/**
 * Build a single marker trace holding every projected blast hole.
 *
 * One trace (not one per hole) is intentional: Plotly handles
 * per-point colours via the `marker.color` array, and a single
 * trace keeps the legend clean and the chart light. Green markers
 * are within `tolerance` of the section line; red ones are outside.
 *
 * `customdata` carries `[burden, spacing]` so the hovertemplate can
 * show both numbers without bloating `text`.
 */
function buildBlastHolesTrace(
  blastHoles: readonly BlastHoleOnProfile[],
): Partial<Plotly.PlotData> {
  return {
    type: 'scatter',
    mode: 'markers',
    name: 'Pozos de tronadura',
    x: blastHoles.map((h) => h.distance),
    y: blastHoles.map((h) => h.elevation),
    marker: {
      color: blastHoles.map((h) => (h.is_within_tolerance ? '#22c55e' : '#ef4444')),
      size: 8,
      symbol: 'diamond',
    },
    text: blastHoles.map((h) => `Hole ${h.hole_id}`),
    hovertemplate:
      '<b>%{text}</b><br>burden=%{customdata[0]:.2f}m<br>spacing=%{customdata[1]:.2f}m<extra></extra>',
    customdata: blastHoles.map((h) => [h.burden, h.spacing]),
    showlegend: true,
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
    const text = matched.map((b) => `${STATUS_ICON[b.status]} ${b.benchNumber}`);
    const customdata = matched.map((b) => {
      const crColor = b.deltaCrest && b.deltaCrest < -0.5 ? '#ef4444' : b.deltaCrest && b.deltaCrest > 0.5 ? '#3b82f6' : 'inherit';
      const toColor = b.deltaToe && b.deltaToe < -0.5 ? '#ef4444' : b.deltaToe && b.deltaToe > 0.5 ? '#3b82f6' : 'inherit';
      return [
        b.benchNumber,
        b.toeElevation ?? 0,
        b.deltaCrest != null ? `<span style="color:${crColor}">${b.deltaCrest > 0 ? '+' : ''}${b.deltaCrest.toFixed(2)}m</span>` : 'N/A',
        b.deltaToe != null ? `<span style="color:${toColor}">${b.deltaToe > 0 ? '+' : ''}${b.deltaToe.toFixed(2)}m</span>` : 'N/A',
      ];
    });
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
  return '<b>Cota %{customdata[1]:.0f}</b> %{text}<br>' +
         'ΔCr: %{customdata[2]}<br>' +
         'ΔPa: %{customdata[3]}<br>' +
         '<extra></extra>';
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
