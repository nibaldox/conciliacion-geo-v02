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
 *  - Click a bench marker or an identified topographic point → crossLink.setSelected(benchNumber)
 *  - When crossLink.hovered/selected changes, that bench's marker
 *    grows + gets a ring (the visual highlight comes from updating
 *    the marker's size and outline via a customdata lookup).
 *
 * Strictly read-only: no business logic in this file. The only
 * computation is "translate view model + filter state into Plotly
 * traces" — a pure function that can be tested independently.
 */

import { useEffect, useMemo, useRef, useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Plot from '../../../charts/Plot';
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
import { getHorizontalDeviationColor } from '../../../../utils/horizontalDeviation';
import { readThemeColor } from '../../../../utils/theme';

export interface ProfileChartProps {
  readonly viewModel: ProfileViewModel;
  readonly filterState: FilterState;
  readonly crossLink: UseCrossLinkStateApi;
  /** Optional: Plotly height in px. Default 480. */
  readonly height?: number;
}

type PlotPoint = { customdata?: unknown; curveNumber?: number };
type PlotMouse = { points?: PlotPoint[] };
type MarkerGlyph = { benchNumber: number; centerX: number; centerY: number; radius: number };

export function ProfileChart({ viewModel, filterState, crossLink, height = 480 }: ProfileChartProps) {
  const { t, i18n } = useTranslation();
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
        setContainerSize((previous) => previous.width === rect.width && previous.height === rect.height
          ? previous
          : { width: rect.width, height: rect.height });
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
  const horizontalLabels = useMemo<HorizontalDeviationChartLabels>(() => ({
    deviation: t('horizontalDeviation.chart.deviation'),
    designBench: (number: number) => t('horizontalDeviation.chart.design_bench', { number }),
    designBenchShort: (number: number) => t('horizontalDeviation.chart.design_bench_short', { number }),
    noDesignBench: t('horizontalDeviation.chart.no_design_bench'),
    height: (value: string) => t('horizontalDeviation.chart.sample_height', { height: value }),
    datum: (value: string) => t('horizontalDeviation.chart.sample_datum', { elevation: value }),
    sample: (height: string, deviation: string) => t('horizontalDeviation.chart.sample_annotation', { height, deviation }),
    sampleUnmeasured: (height: string, status: string) => t('horizontalDeviation.chart.sample_unmeasured', { height, status }),
    status: (status: string) => {
      const known = ['measured', 'missing', 'ambiguous', 'horizontal_segment', 'unassessed', 'unmeasured'];
      const key = known.includes(status) ? status : 'unassessed';
      return t(`horizontalDeviation.chart.${key}`);
    },
  }), [t]);
  const data = useMemo<Data[]>(
    () => buildTraces(viewModel, filterState, crossLink, isDark, blastHoles, {
      elevation: t('profileView.chart.hover.elevation'),
      crestDelta: t('profileView.chart.hover.crestDelta'),
      toeDelta: t('profileView.chart.hover.toeDelta'),
      actualAngle: t('profileView.chart.hover.actualAngle'),
      plannedAngle: t('profileView.chart.hover.plannedAngle'),
      actualBerm: t('profileView.chart.hover.actualBerm'),
      plannedBerm: t('profileView.chart.hover.plannedBerm'),
      unmatched: t('profileView.chart.hover.unmatched'),
    }, horizontalLabels),
    [viewModel, filterState, crossLink, isDark, blastHoles, horizontalLabels, t],
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
    if (filterState.showHorizontalDeviation && viewModel.horizontalDeviation) {
      annotations.push(...buildHorizontalDeviationSampleAnnotations(viewModel, horizontalLabels));
    }
    const shapes = filterState.showReconciledTopo ? buildBermShapes(viewModel) : [];

    return {
      ...base,
      // We extend the layout with view-model-specific bits: title
      // is rendered in SectionHeader (above), so plotly title is off.
      title: undefined,
      autosize: true,
      width: containerSize.width || undefined,
      height: containerSize.height || height,
      annotations,
      shapes,
      yaxis: {
        ...(base.yaxis as Partial<Layout['yaxis']>),
        title: { text: t('profileView.chart.elevation'), font: { size: 12 } },
        scaleanchor: 'x',
        scaleratio: 1,
        constrain: 'range',
        range: yRange,
      },
      xaxis: {
        ...(base.xaxis as Partial<Layout['xaxis']>),
        title: { text: t('profileView.chart.distance'), font: { size: 12 } },
        constrain: 'range',
        range: xRange,
      },
      // The chart's hover/click routing is handled by the onHover
      // and onClick callbacks we attach to the Plot component,
      // not by Plotly's built-in modes.
    };
  }, [height, viewModel, containerSize, filterState.showReconciledTopo, filterState.showHorizontalDeviation, horizontalLabels, isDark, t]);

  const config = useMemo<Partial<Config>>(() => ({
    ...createPlotlyConfig(),
    displayModeBar: true,
    modeBarButtons: [['zoomIn2d', 'zoomOut2d', 'resetScale2d', 'toImage']],
    locale: i18n.resolvedLanguage?.startsWith('es') ? 'es' : 'en',
  }), [i18n.resolvedLanguage]);

  // ── 3. Hover / click → crossLink state ────────────────────
  const onHover = useCallback(
    (event: unknown) => {
      const n = getBenchNumberFromPlotEvent(event, data)
        ?? getBenchNumberFromPointerHit(event, data, containerRef.current);
      crossLink.setHovered(n);
    },
    [crossLink, data],
  );

  const onUnhover = useCallback(() => {
    crossLink.setHovered(null);
  }, [crossLink]);

  const onClick = useCallback(
    (event: unknown) => {
      const n = getBenchNumberFromPlotEvent(event, data)
        ?? getBenchNumberFromPointerHit(event, data, containerRef.current);
      if (n !== null) crossLink.setSelected(n);
    },
    [crossLink, data],
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
  blastHoles?: readonly BlastHoleOnProfile[],
  hoverLabels: BenchHoverLabels = DEFAULT_BENCH_HOVER_LABELS,
  horizontalLabels: HorizontalDeviationChartLabels = DEFAULT_HORIZONTAL_DEVIATION_CHART_LABELS,
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
    traces.push(buildTopoPolyline(topo, vm.benches, hoverLabels));
    // Subtle "ground" fill under the topo line so the profile
    // doesn't look like a floating squiggle. Uses 'tozeroy' to
    // fill down to y=0 of the axis (the y range is set tight so
    // this looks like filling the area below the profile).
    traces.push(buildGroundFill(topo, isDark));
  }

  if (filterState.showHorizontalDeviation && vm.horizontalDeviation) {
    traces.push(...buildHorizontalDeviationTraces(vm, hoverLabels, horizontalLabels));
    traces.push(...buildHorizontalDeviationSampleTraces(vm, horizontalLabels));
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
  traces.push(...buildBenchMarkers(vm.benches, filterState, crossLink, hoverLabels));

  // 7. Blast-hole markers — projected pozos de tronadura.
  //    The caller passes these in from the `useBlastHoles` hook;
  //    undefined/empty is the no-data case and emits nothing.
  if (blastHoles && blastHoles.length > 0) {
    traces.push(buildBlastHolesTrace(blastHoles));
  }

  return traces;
}

export function buildHorizontalDeviationTraces(
  vm: ProfileViewModel,
  hoverLabels: BenchHoverLabels = DEFAULT_BENCH_HOVER_LABELS,
  labels: HorizontalDeviationChartLabels = DEFAULT_HORIZONTAL_DEVIATION_CHART_LABELS,
): Partial<Plotly.ScatterData>[] {
  const points = vm.horizontalDeviation?.points ?? [];
  const runs: { category: string; points: typeof points[number][] }[] = [];
  let activeRun: { category: string; points: typeof points[number][] } | null = null;

  for (const point of points) {
    if (!Number.isFinite(point.distance) || !Number.isFinite(point.elevation)) {
      activeRun = null;
      continue;
    }
    const category = point.deviation === null || !Number.isFinite(point.deviation)
      ? 'unmeasured'
      : point.category;
    if (!activeRun || activeRun.category !== category) {
      activeRun = { category, points: [] };
      runs.push(activeRun);
    }
    activeRun.points.push(point);
  }

  return runs.map((run) => {
    const color = getHorizontalDeviationColor(run.category);
    const benches = run.points.map((point) => findUniqueBenchAtDistance(point.distance, vm.benches));
    const baseHover = (index: number) => {
      const bench = benches[index];
      if (bench) return makeHoverTemplate(hoverLabels, bench.matched);
      return '%{x:.1f} m, %{y:.1f} m<extra>Topografía</extra>';
    };
    const hovertemplate = run.points.map((point, index) => {
      const deviation = Number.isFinite(point.deviation)
        ? formatSignedDeviation(point.deviation!)
        : labels.status(point.status);
      const reference = point.design_bench_num == null
        ? labels.noDesignBench
        : labels.designBench(point.design_bench_num);
      const details = `<br>${labels.deviation}: ${deviation}<br>${reference}<br>${labels.status(point.status)}`;
      return appendHoverDetails(baseHover(index), details);
    });
    return {
      type: 'scatter',
      mode: run.points.length === 1 ? 'markers' : 'lines+markers',
      name: labels.deviation,
      meta: { profileViewRole: 'bench-face', horizontalDeviation: true },
      x: run.points.map((point) => point.distance),
      y: run.points.map((point) => point.elevation),
      customdata: benches.map((bench) => bench ? buildBenchHoverCustomdata(bench) : []),
      text: benches.map((bench) => bench ? `${STATUS_ICON[bench.status]} ${bench.benchNumber}` : ''),
      line: { color, width: 4, shape: 'linear' },
      marker: { color, size: 5 },
      hovertemplate,
      showlegend: false,
    };
  });
}

export function buildHorizontalDeviationSampleTraces(
  vm: ProfileViewModel,
  labels: HorizontalDeviationChartLabels = DEFAULT_HORIZONTAL_DEVIATION_CHART_LABELS,
): Partial<Plotly.ScatterData>[] {
  const samples = vm.horizontalDeviation?.samples ?? [];
  return samples.flatMap((sample) => {
    if (sample.deviation === null || !Number.isFinite(sample.deviation)
      || sample.design_distance === null || !Number.isFinite(sample.design_distance)
      || sample.topo_distance === null || !Number.isFinite(sample.topo_distance)
      || sample.reference_elevation === null || !Number.isFinite(sample.reference_elevation)) return [];
    const color = getHorizontalDeviationColor(sample.category);
    const heightLabel = sample.height_above_toe === null || !Number.isFinite(sample.height_above_toe)
      ? '—'
      : `${sample.height_above_toe.toFixed(1)} m`;
    const toe = sample.toe_elevation == null || !Number.isFinite(sample.toe_elevation)
      ? ''
      : `<br>${labels.datum(sample.toe_elevation.toFixed(1))}`;
    return [{
      type: 'scatter',
      mode: 'lines+markers',
      name: labels.designBench(sample.design_bench_num),
      meta: { profileViewRole: 'horizontal-deviation-sample' },
      x: [sample.design_distance, sample.topo_distance],
      y: [sample.reference_elevation, sample.reference_elevation],
      line: { color, width: 2 },
      marker: { color, size: 4 },
      hovertemplate: `<b>${labels.designBench(sample.design_bench_num)}</b><br>` +
        `${labels.height(heightLabel)}<br>${labels.deviation}: ${formatSignedDeviation(sample.deviation)}` +
        `${toe}<br>${labels.status(sample.status)}<extra></extra>`,
      showlegend: false,
    }];
  });
}

export function buildHorizontalDeviationSampleAnnotations(
  vm: ProfileViewModel,
  labels: HorizontalDeviationChartLabels = DEFAULT_HORIZONTAL_DEVIATION_CHART_LABELS,
): Partial<Plotly.Annotation>[] {
  const samples = vm.horizontalDeviation?.samples ?? [];
  return samples.flatMap((sample) => {
    if (sample.reference_elevation === null || !Number.isFinite(sample.reference_elevation)) return [];
    const availableDistances = [sample.design_distance, sample.topo_distance]
      .filter((distance): distance is number => distance !== null && Number.isFinite(distance));
    if (availableDistances.length === 0) return [];
    const x = Math.max(...availableDistances);
    const heightLabel = sample.height_above_toe === null || !Number.isFinite(sample.height_above_toe)
      ? '—'
      : `${sample.height_above_toe.toFixed(1)} m`;
    const text = sample.deviation !== null && Number.isFinite(sample.deviation)
      ? labels.sample(heightLabel, formatSignedDeviation(sample.deviation))
      : labels.sampleUnmeasured(heightLabel, labels.status(sample.status));
    return [{
      x,
      y: sample.reference_elevation,
      text: `${labels.designBenchShort(sample.design_bench_num)} · ${text}`,
      showarrow: false,
      xanchor: 'left',
      yanchor: 'middle',
      xshift: 8,
      yshift: 0,
      bgcolor: readThemeColor('--color-surface-raised', '#19232d'),
      bordercolor: readThemeColor('--color-border', '#2d3b49'),
      borderwidth: 1,
      borderpad: 3,
      font: { size: 10, color: getHorizontalDeviationColor(sample.category) },
    }];
  });
}

function formatSignedDeviation(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)} m`;
}

function appendHoverDetails(template: string, details: string): string {
  const extraStart = template.lastIndexOf('<extra>');
  return extraStart < 0
    ? `${template}${details}`
    : `${template.slice(0, extraStart)}${details}${template.slice(extraStart)}`;
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
): Partial<Plotly.Annotation>[] {
  if (!showAnnotations) return [];
  const annotations: Partial<Plotly.Annotation>[] = [];
  for (const bench of vm.benches) {
    annotations.push({
      x: bench.toeDistance,
      y: bench.toeElevation,
      text: `B${bench.benchNumber}'<br><b>${bench.toeElevation.toFixed(0)}m</b>`,
      showarrow: false,
      font: { size: 10, color: '#888' },
    });
  }
  return annotations;
}

function buildPolyline(
  line: ProfileLine,
  name: string,
  style: NonNullable<Plotly.ScatterData['line']>,
): Partial<Plotly.ScatterData> {
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
): Partial<Plotly.ScatterData> {
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
    hoverinfo: 'skip',
    showlegend: false,
  };
}

function buildAreaFills(
  design: ProfileLine,
  topo: ProfileLine,
  isDark: boolean,
): Partial<Plotly.ScatterData>[] {
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
      hoverinfo: 'skip',
    }
  ];
}

function buildSpillAreaTraces(
  benches: readonly Bench[],
): Partial<Plotly.ScatterData>[] {
  const traces: Partial<Plotly.ScatterData>[] = [];
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
): Partial<Plotly.ScatterData> {
  return {
    type: 'scatter',
    mode: 'markers',
    name: 'Pozos de tronadura',
    meta: { profileViewRole: 'blast-hole' },
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

export interface BenchHoverLabels {
  readonly elevation: string;
  readonly crestDelta: string;
  readonly toeDelta: string;
  readonly actualAngle: string;
  readonly plannedAngle: string;
  readonly actualBerm: string;
  readonly plannedBerm: string;
  readonly unmatched: string;
}

export interface HorizontalDeviationChartLabels {
  readonly deviation: string;
  readonly designBench: (number: number) => string;
  readonly designBenchShort: (number: number) => string;
  readonly noDesignBench: string;
  readonly height: (value: string) => string;
  readonly datum: (value: string) => string;
  readonly sample: (height: string, deviation: string) => string;
  readonly sampleUnmeasured: (height: string, status: string) => string;
  readonly status: (status: string) => string;
}

const DEFAULT_BENCH_HOVER_LABELS: BenchHoverLabels = {
  elevation: 'Cota',
  crestDelta: 'ΔCr',
  toeDelta: 'ΔPa',
  actualAngle: 'Ángulo real',
  plannedAngle: 'Ángulo planificado',
  actualBerm: 'Berma real',
  plannedBerm: 'Berma planificada',
  unmatched: 'Sin banco de diseño asociado',
};

const DEFAULT_HORIZONTAL_DEVIATION_CHART_LABELS: HorizontalDeviationChartLabels = {
  deviation: 'dH horizontal',
  designBench: (number) => `Banco de diseño ${number}`,
  designBenchShort: (number) => `D${number}`,
  noDesignBench: 'Sin banco de diseño asociado',
  height: (value) => `h desde pata ${value}`,
  datum: (value) => `Pata de diseño: ${value} m`,
  sample: (height, deviation) => `h ${height} · dH ${deviation}`,
  sampleUnmeasured: (height, status) => `h ${height} · ${status}`,
  status: (status) => status,
};

function buildBenchMarkers(
  benches: readonly Bench[],
  filterState: FilterState,
  crossLink: UseCrossLinkStateApi,
  hoverLabels: BenchHoverLabels,
): Partial<Plotly.ScatterData>[] {
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
  ): Partial<Plotly.ScatterData> => {
    const x = matched.map((b) => b.crestDistance);
    const y = matched.map((b) => b.crestElevation);
    const text = matched.map((b) => `${STATUS_ICON[b.status]} ${b.benchNumber}`);
    const customdata = matched.map(buildBenchHoverCustomdata);
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
      meta: { profileViewRole: 'bench-marker' },
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
      hovertemplate: matched.map((bench) => makeHoverTemplate(hoverLabels, bench.matched)),
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

function makeHoverTemplate(labels: BenchHoverLabels, matched = true): string {
  return `<b>${labels.elevation} %{customdata[1]:.0f}</b> %{text}<br>` +
         `${labels.crestDelta}: %{customdata[2]}<br>` +
         `${labels.toeDelta}: %{customdata[3]}<br>` +
         `${labels.actualAngle}: %{customdata[4]}<br>` +
         `${labels.plannedAngle}: %{customdata[5]}<br>` +
         `${labels.actualBerm}: %{customdata[6]}<br>` +
         `${labels.plannedBerm}: %{customdata[7]}<br>` +
         (matched ? '' : `${labels.unmatched}<br>`) +
         '<extra></extra>';
}

function buildTopoPolyline(
  topo: ProfileLine,
  benches: readonly Bench[],
  hoverLabels: BenchHoverLabels,
): Partial<Plotly.ScatterData> {
  const pointBenches = topo.points.map((point) => findUniqueBenchAtDistance(point.distance, benches));
  const coordinateHoverTemplate = '%{x:.1f} m, %{y:.1f} m<extra>Topografía</extra>';
  return {
    ...buildPolyline(topo, 'Topografía', topoLineStyle()),
    meta: { profileViewRole: 'bench-face' },
    customdata: pointBenches.map((bench) => bench ? buildBenchHoverCustomdata(bench) : []),
    text: pointBenches.map((bench) => bench ? `${STATUS_ICON[bench.status]} ${bench.benchNumber}` : ''),
    hovertemplate: pointBenches.map((bench) => bench ? makeHoverTemplate(hoverLabels, bench.matched) : coordinateHoverTemplate),
  };
}

function findUniqueBenchAtDistance(distance: number | null, benches: readonly Bench[]): Bench | null {
  if (distance === null || !Number.isFinite(distance)) return null;

  let match: Bench | null = null;
  for (const bench of benches) {
    if (!Number.isFinite(bench.crestDistance) || !Number.isFinite(bench.toeDistance)) continue;
    const minimum = Math.min(bench.crestDistance, bench.toeDistance);
    const maximum = Math.max(bench.crestDistance, bench.toeDistance);
    if (distance < minimum || distance > maximum) continue;
    if (match !== null) return null;
    match = bench;
  }
  return match;
}

function formatHoverMeasurement(value: number | null, unit: '°' | 'm'): string {
  return value !== null && Number.isFinite(value) ? `${value.toFixed(1)}${unit === '°' ? '°' : ' m'}` : '—';
}

export function getBenchNumberFromPlotEvent(event: unknown, traces: readonly Data[]): number | null {
  const e = event as PlotMouse | undefined;
  const points = e?.points ?? [];
  if (points.some((point) => traceHasRole(traces[point.curveNumber ?? -1], 'blast-hole'))) return null;

  const markerNumbers = new Set<number>();
  const faceNumbers = new Set<number>();
  for (const point of points) {
    const trace = traces[point.curveNumber ?? -1];
    const isMarker = traceHasRole(trace, 'bench-marker');
    if (!isMarker && !traceHasRole(trace, 'bench-face')) continue;
    const benchNumber = extractBenchNumber(point.customdata);
    if (benchNumber === null) continue;
    (isMarker ? markerNumbers : faceNumbers).add(benchNumber);
  }
  if (markerNumbers.size === 1) return markerNumbers.values().next().value ?? null;
  if (markerNumbers.size > 1) return null;
  return faceNumbers.size === 1 ? faceNumbers.values().next().value ?? null : null;
}

export function getBenchNumberFromPointerGlyph(
  event: unknown,
  traces: readonly Data[],
  glyphs: readonly MarkerGlyph[],
): number | null {
  const plotEvent = event as { event?: MouseEvent; points?: PlotPoint[] } | undefined;
  const pointer = plotEvent?.event;
  const points = plotEvent?.points ?? [];
  if (!pointer || points.some((point) => traceHasRole(traces[point.curveNumber ?? -1], 'blast-hole'))) return null;
  const hasUnidentifiedDeviationHit = points.some((point) => {
    const trace = traces[point.curveNumber ?? -1];
    return traceHasRole(trace, 'bench-face')
      && (trace.meta as { horizontalDeviation?: unknown } | undefined)?.horizontalDeviation === true
      && extractBenchNumber(point.customdata) === null;
  });
  if (!hasUnidentifiedDeviationHit) return null;
  const hits = glyphs.filter((glyph) => Number.isFinite(glyph.radius) && glyph.radius > 0
    && Math.hypot(pointer.clientX - glyph.centerX, pointer.clientY - glyph.centerY) <= glyph.radius);
  return hits.length === 1 ? hits[0]!.benchNumber : null;
}

function getBenchNumberFromPointerHit(
  event: unknown,
  traces: readonly Data[],
  container: HTMLDivElement | null,
): number | null {
  const plotEvent = event as { event?: MouseEvent; points?: PlotPoint[] } | undefined;
  const points = plotEvent?.points ?? [];
  if (!plotEvent?.event || points.some((point) => traceHasRole(traces[point.curveNumber ?? -1], 'blast-hole'))) return null;
  const hasUnidentifiedDeviationHit = points.some((point) => {
    const trace = traces[point.curveNumber ?? -1];
    return traceHasRole(trace, 'bench-face')
      && (trace.meta as { horizontalDeviation?: unknown } | undefined)?.horizontalDeviation === true
      && extractBenchNumber(point.customdata) === null;
  });
  if (!hasUnidentifiedDeviationHit) return null;
  return getBenchNumberFromPointerGlyph(event, traces, getVisibleBenchMarkerGlyphs(container, traces));
}

function getVisibleBenchMarkerGlyphs(container: HTMLDivElement | null, traces: readonly Data[]): MarkerGlyph[] {
  const plot = container?.querySelector<HTMLElement>('.js-plotly-plot') as (HTMLElement & {
    _fullData?: Array<{ uid?: string; _uid?: string }>;
  }) | null;
  if (!plot?._fullData) return [];
  const traceGroups = Array.from(plot.querySelectorAll<SVGGElement>('.scatterlayer g.trace'));
  const glyphs: MarkerGlyph[] = [];
  traces.forEach((trace, traceIndex) => {
    if (!traceHasRole(trace, 'bench-marker')) return;
    const fullTrace = plot._fullData?.[traceIndex];
    const uid = fullTrace?.uid ?? fullTrace?._uid;
    if (!uid) return;
    const group = traceGroups.find((candidate) => candidate.getAttribute('data-uid') === uid
      || candidate.classList.contains(`trace${uid}`));
    if (!group) return;
    const customdata = (trace as { customdata?: unknown[] }).customdata ?? [];
    const markerPaths = Array.from(group.querySelectorAll<SVGGraphicsElement>('.points path.point'));
    markerPaths.forEach((markerPath, pointIndex) => {
      const benchNumber = extractBenchNumber(customdata[pointIndex]);
      if (benchNumber === null) return;
      const rect = markerPath.getBoundingClientRect();
      const radius = Math.min(rect.width, rect.height) / 2;
      if (radius <= 0) return;
      glyphs.push({
        benchNumber,
        centerX: rect.left + rect.width / 2,
        centerY: rect.top + rect.height / 2,
        radius,
      });
    });
  });
  return glyphs;
}

function extractBenchNumber(customdata: unknown): number | null {
  if (typeof customdata === 'number' && Number.isFinite(customdata)) return customdata;
  if (Array.isArray(customdata) && typeof customdata[0] === 'number' && Number.isFinite(customdata[0])) {
    return customdata[0];
  }
  return null;
}

function traceHasRole(trace: Data | undefined, role: string): boolean {
  if (!trace || typeof trace.meta !== 'object' || trace.meta === null) return false;
  return (trace.meta as { profileViewRole?: unknown }).profileViewRole === role;
}

function buildBenchHoverCustomdata(bench: Bench): (number | string)[] {
  const crColor = bench.deltaCrest && bench.deltaCrest < -0.5 ? '#ef4444' : bench.deltaCrest && bench.deltaCrest > 0.5 ? '#3b82f6' : 'inherit';
  const toColor = bench.deltaToe && bench.deltaToe < -0.5 ? '#ef4444' : bench.deltaToe && bench.deltaToe > 0.5 ? '#3b82f6' : 'inherit';
  return [
    bench.benchNumber,
    bench.toeElevation ?? 0,
    bench.deltaCrest != null ? `<span style="color:${crColor}">${bench.deltaCrest > 0 ? '+' : ''}${bench.deltaCrest.toFixed(2)}m</span>` : 'N/A',
    bench.deltaToe != null ? `<span style="color:${toColor}">${bench.deltaToe > 0 ? '+' : ''}${bench.deltaToe.toFixed(2)}m</span>` : 'N/A',
    formatHoverMeasurement(bench.faceAngle, '°'),
    formatHoverMeasurement(bench.designAngle, '°'),
    formatHoverMeasurement(bench.bermWidth, 'm'),
    formatHoverMeasurement(bench.designBerm, 'm'),
  ];
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
