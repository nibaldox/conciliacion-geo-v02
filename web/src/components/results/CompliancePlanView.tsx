import { memo, useCallback, useMemo, useRef, useState } from 'react';
import type { PointerEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useMeshVertices, useSectionProfiles, useSections } from '../../api/hooks';
import type { GuideCurve } from '../../stores/session';
import { selectGuideLine } from './planGuideLine';
import type { ComparisonResult } from '../../api/types';
import { useSession } from '../../stores/session';
import type { BenchStatus } from './ProfileView/domain/types';
import { Spinner } from '../ui/Spinner';
import { InfoTip, SegmentedControl, SummaryPanel } from './SummaryControls';
import { planColor, planStatusStrokeDash, sectionParameterPassRate, sectionScore, type PlanColorBy, type PlanStatusKey } from './planColors';

export type { PlanColorBy, PlanStatusKey } from './planColors';

import { createPlanProjection, useSurfaceRaster, projectPlanPoint, sectionPlanPoints, planBounds, type Projection } from './planGeometry';

export { createPlanProjection, projectPlanPoint } from './planGeometry';

function StatusLegendItem({ status, label }: { status: PlanStatusKey; label: string }) {
  const dasharray = planStatusStrokeDash(status);
  return <span className="flex items-center gap-1.5"><svg className="shrink-0" width="24" height="10" aria-hidden="true"><line data-status-swatch={status} x1="1" y1="5" x2="23" y2="5" stroke={planColor('status', status)} strokeWidth="3" strokeLinecap="round" strokeDasharray={dasharray} /></svg>{label}</span>;
}

function GuideLine({ guide, projection }: { guide: GuideCurve; projection: Projection }) {
  const points = selectGuideLine(guide);
  if (points.length < 2) return null;
  return <polyline data-guide-line="" points={points.map((point) => projectPlanPoint(...point, projection).join(',')).join(' ')} fill="none" stroke="var(--color-accent-bright)" strokeWidth="3" vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeLinejoin="round" pointerEvents="none" aria-hidden="true" />;
}

const PlanSection = memo(function PlanSection({ name, coordinates, firstX, firstY, endX, endY, status, labelX, labelY }: { name: string; coordinates: string; firstX: number; firstY: number; endX: number; endY: number; status?: BenchStatus; labelX: number; labelY: number }) {
  const { t } = useTranslation();
  const state = status ?? 'UNKNOWN';
  const color = state === 'UNKNOWN' ? 'var(--color-text-muted)' : state === 'CUMPLE' ? 'var(--status-ok-text)' : state === 'FUERA' ? 'var(--status-warn-text)' : 'var(--status-nok-text)';
  const label = `${name} · ${state === 'UNKNOWN' ? t('plan_view.no_score') : t('status.' + state.toLowerCase())}`;
  const endpoint = labelX < 500 ? [firstX, firstY] : [endX, endY];
  return (
    <g data-section-name={name} data-compliance-status={state} data-status={state}>
      <title>{label}</title>
      <polyline points={coordinates} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" strokeDasharray={planStatusStrokeDash(state)} />
      <line x1={endpoint[0]} y1={endpoint[1]} x2={labelX} y2={labelY - 4} stroke={color} strokeWidth="1" opacity="0.45" />
      <text x={labelX} y={labelY} textAnchor={labelX < 500 ? 'end' : 'start'} fill={color} fontSize="14" fontWeight="600" stroke="var(--color-surface-sunken)" strokeWidth="3" paintOrder="stroke" strokeLinejoin="round">{name}</text>
    </g>
  );
});

interface HeroSectionProps {
  name: string; status: PlanStatusKey; statusLabel: string; coordinates: string;
  endX: number; endY: number; color: string; colorBy: PlanColorBy;
  enabled: boolean; selected: boolean; focused: boolean; opacity: number; zoom: number;
  onEnter: (name: string, event: React.MouseEvent<SVGGElement>) => void;
  onMove: (event: React.MouseEvent<SVGGElement>) => void;
  onLeave: () => void; onSelect: (name: string, enabled: boolean, keyboard: boolean) => void;
}
const HeroSection = memo(function HeroSection({ name, status, statusLabel, coordinates, endX, endY, color, colorBy, enabled, selected, focused, opacity, zoom, onEnter, onMove, onLeave, onSelect }: HeroSectionProps) {
  return <g data-section-name={name} data-status={status} opacity={opacity}
    role={enabled ? 'button' : undefined} tabIndex={enabled ? 0 : undefined} aria-label={enabled ? `${name} · ${statusLabel}` : undefined} aria-pressed={enabled ? selected : undefined}
    onMouseEnter={(event) => { if (enabled) onEnter(name, event); }} onMouseMove={onMove} onMouseLeave={onLeave}
    onClick={(event) => { event.stopPropagation(); onSelect(name, enabled, false); }}
    onKeyDown={(event) => { if (enabled && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); onSelect(name, true, true); } }}>
    {selected && <polyline points={coordinates} fill="none" stroke="var(--color-text-primary)" strokeWidth="9" vectorEffect="non-scaling-stroke" strokeLinecap="round" />}
    <polyline data-plan-line="" points={coordinates} fill="none" stroke={color} strokeWidth={focused ? 5 : 3} vectorEffect="non-scaling-stroke" strokeLinecap="round" strokeDasharray={colorBy === 'status' ? planStatusStrokeDash(status) : undefined} />
    {focused && <text x={endX} y={endY} dx={5 / zoom} dy={-5 / zoom} fill="var(--color-text-primary)" fontSize={14 / zoom} stroke="var(--color-surface-sunken)" strokeWidth={3 / zoom} paintOrder="stroke">{name}</text>}
    <polyline points={coordinates} fill="none" stroke="transparent" strokeWidth="14" vectorEffect="non-scaling-stroke" pointerEvents={enabled ? 'stroke' : 'none'} />
  </g>;
});

export interface CompliancePlanViewProps {
  results: readonly ComparisonResult[];
  frameResults?: readonly ComparisonResult[];
  statuses: ReadonlyMap<string, BenchStatus>;
  variant?: 'panel' | 'hero';
  colorBy?: PlanColorBy;
  visibleStatuses?: ReadonlySet<PlanStatusKey>;
  selectedSection?: string | null;
  onSelectSection?: (name: string | null) => void;
}

export function CompliancePlanView({ results, frameResults, statuses, variant = 'panel', colorBy = 'status', visibleStatuses, selectedSection, onSelectSection }: CompliancePlanViewProps) {
  const { t } = useTranslation();
  const [fullSurface, setFullSurface] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const tooltipPosition = useRef({ x: 0, y: 0 });
  const moveTooltip = useCallback((event: React.MouseEvent<SVGGElement>) => {
    const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect();
    if (!rect) return;
    tooltipPosition.current = { x: event.clientX - rect.left, y: event.clientY - rect.top };
    if (tooltipRef.current) { tooltipRef.current.style.left = `${tooltipPosition.current.x + 12}px`; tooltipRef.current.style.top = `${tooltipPosition.current.y + 12}px`; }
  }, []);
  const enterSection = useCallback((name: string, event: React.MouseEvent<SVGGElement>) => { moveTooltip(event); setHovered(name); }, [moveTooltip]);
  const leaveSection = useCallback(() => setHovered(null), []);
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 });
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
  const selectSection = useCallback((name: string, enabled: boolean, keyboard: boolean) => { if (enabled && (keyboard || !suppressClick.current)) onSelectSection?.(name); if (!keyboard) suppressClick.current = false; }, [onSelectSection]);
  const svgRef = useCallback((node: SVGSVGElement | null) => {
    if (!node) return;
    const handleWheel = (event: WheelEvent) => {
      event.preventDefault();
      const rect = node.getBoundingClientRect();
      const scale = Math.min(rect.width / 1000, rect.height / 600);
      const px = scale ? (event.clientX - rect.left - (rect.width - 1000 * scale) / 2) / (1000 * scale) : 0.5;
      const py = scale ? (event.clientY - rect.top - (rect.height - 600 * scale) / 2) / (600 * scale) : 0.5;
      setView((previous) => {
        const zoom = Math.max(1, Math.min(8, previous.zoom * Math.exp(-event.deltaY * 0.0015)));
        return { x: previous.x + px * (1000 / previous.zoom - 1000 / zoom), y: previous.y + py * (600 / previous.zoom - 600 / zoom), zoom };
      });
    };
    node.addEventListener('wheel', handleWheel, { passive: false });
    return () => node.removeEventListener('wheel', handleWheel);
  }, []);
  const topoMeshId = useSession((state) => state.topoMeshId);
  const guideCurve = useSession((state) => state.guideCurve);
  const { data: vertices, isLoading, error } = useMeshVertices(topoMeshId);
  const { data: sections } = useSections();
  const names = new Set(results.map((row) => row.section));
  const frameNames = new Set((frameResults ?? results).map((row) => row.section));
  const requestedNames = new Set([...names, ...frameNames]);
  const profileSections = sections?.filter((section) => requestedNames.has(section.name)) ?? [];
  const profiles = useSectionProfiles(profileSections.map((section) => section.id));
  const allLines = profileSections.map((section, index) => ({ section, points: sectionPlanPoints(section, profiles[index]?.data) })).filter((line) => line.points.length >= 2);
  const lines = allLines.filter(({ section }) => names.has(section.name));
  const frameLines = allLines.filter(({ section }) => frameNames.has(section.name));
  const frameBounds = planBounds(frameLines.flatMap((line) => line.points));
  const [xMin, yMin, xMax, yMax] = frameBounds ?? [];
  const projection = useMemo(() => vertices ? createPlanProjection(vertices, !fullSurface && xMin !== undefined && yMin !== undefined && xMax !== undefined && yMax !== undefined ? [[xMin, yMin], [xMax, yMax]] : [], variant === 'panel') : null, [vertices, fullSurface, xMin, yMin, xMax, yMax, variant]);
  const raster = useSurfaceRaster(vertices, projection);
  // Section/profile hooks may return fresh wrapper arrays on every render; the
  // coordinate key preserves the cached projections until actual geometry changes.
  const geometryKey = JSON.stringify(lines.map(({ section, points }) => [section.id, points]), (_key, value: unknown) => typeof value === 'number' && !Number.isFinite(value) ? String(value) : value);
  const projectedLines = useMemo(() => {
    return new Map(lines.map(({ section, points }) => {
      const projected = projection ? points.map((point) => projectPlanPoint(...point, projection)) : [];
      return [section.id, { coordinates: projected.map((point) => point.join(',')).join(' '), first: projected[0], endpoint: projected[projected.length - 1] }] as const;
    }));
  // geometryKey represents the full section geometry; wrappers may be unstable.
  }, [geometryKey, projection]);
  const sectionValues = useMemo(() => {
    const values = new Map<string, { status: PlanStatusKey; score: number | null; color: string }>();
    for (const row of results) {
      if (values.has(row.section)) continue;
      const status = statuses.get(row.section) ?? 'UNKNOWN';
      const score = sectionScore(results, row.section);
      const value = colorBy === 'status' ? status : colorBy === 'score' ? (score == null ? null : score / 100) : sectionParameterPassRate(results, row.section, colorBy);
      values.set(row.section, { status, score, color: planColor(colorBy, value) });
    }
    return values;
  }, [results, colorBy, statuses]);
  const sorted = [...lines].sort((a, b) => a.points[a.points.length - 1]![0] - b.points[b.points.length - 1]![0]);
  const half = Math.ceil(sorted.length / 2);
  const labelPositions = new Map<string, [number, number]>();
  for (const [side, group] of [sorted.slice(0, half), sorted.slice(half)].entries()) {
    group.sort((a, b) => b.points[b.points.length - 1]![1] - a.points[a.points.length - 1]![1]);
    group.forEach((line, index) => labelPositions.set(line.section.id, [side === 0 ? 200 : 800, 60 + 480 * (index + 1) / (group.length + 1)]));
  }
  const loading = isLoading || profiles.some((profile) => profile.isLoading);
  if (variant === 'hero') {
    const width = 1000 / view.zoom, height = 600 / view.zoom;
    const zoomAt = (next: number, px = 0.5, py = 0.5) => setView((previous) => {
      const zoom = Math.max(1, Math.min(8, next));
      return { x: previous.x + px * (1000 / previous.zoom - 1000 / zoom), y: previous.y + py * (600 / previous.zoom - 600 / zoom), zoom };
    });
    const move = (event: PointerEvent<SVGSVGElement>) => {
      if (!drag.current) return;
      const rect = event.currentTarget.getBoundingClientRect();
      const scale = Math.min(rect.width / 1000, rect.height / 600);
      if (!scale) return;
      const dx = event.clientX - drag.current.x, dy = event.clientY - drag.current.y;
      if (dx || dy) drag.current.moved = true;
      drag.current.x = event.clientX; drag.current.y = event.clientY;
      setView((previous) => ({ ...previous, x: previous.x - dx / scale / previous.zoom, y: previous.y - dy / scale / previous.zoom }));
    };
    const activeName = hovered ?? selectedSection;
    const activeStatus = activeName ? statuses.get(activeName) ?? 'UNKNOWN' : 'UNKNOWN';
    const activeScore = activeName ? sectionValues.get(activeName)?.score ?? null : null;
    const choices = [10, 20, 50, 100, 200, 500];
    const desired = projection ? 120 / (projection.scale * view.zoom) : 10;
    const scaleMeters = choices.reduce((best, value) => Math.abs(value - desired) < Math.abs(best - desired) ? value : best, choices[0]!);
    return <div className="relative h-full w-full overflow-hidden bg-surface-sunken" onKeyDown={(event) => { if (event.key === 'Escape') onSelectSection?.(null); }}>
      {loading ? <div className="flex h-full items-center justify-center"><Spinner /></div> : error || !projection || !lines.length ? <p className="flex h-full items-center justify-center text-sm text-text-muted">{t('plan_view.unavailable')}</p> : <>
        <svg ref={svgRef} viewBox={`${view.x} ${view.y} ${width} ${height}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label={t('plan_view.title')} className="h-full w-full touch-none"
          onPointerDown={(event) => { if (event.button !== 0) return; drag.current = { x: event.clientX, y: event.clientY, moved: false }; (event.target as Element).setPointerCapture?.(event.pointerId); }}
          onPointerMove={move} onPointerUp={() => { suppressClick.current = drag.current?.moved ?? false; drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
          onClick={() => { if (!suppressClick.current) onSelectSection?.(null); suppressClick.current = false; }}>
          <image href={raster || undefined} opacity={raster ? 1 : 0} className="transition-opacity duration-150 motion-reduce:transition-none" width="1000" height="600" />
          {lines.map(({ section }) => {
            const values = sectionValues.get(section.name)!;
            const { status, color } = values;
            const enabled = visibleStatuses?.has(status) ?? true;
            const selected = section.name === selectedSection;
            const projected = projectedLines.get(section.id)!;
            const endpoint = projected.endpoint!;
            const statusLabel = status === 'UNKNOWN' ? t('plan_view.no_score') : t('status.' + status.toLowerCase());
            return <HeroSection key={section.id} name={section.name} status={status} statusLabel={statusLabel} coordinates={projected.coordinates} endX={endpoint[0]} endY={endpoint[1]} color={color} colorBy={colorBy} enabled={enabled} selected={selected} focused={hovered === section.name || selected} opacity={!enabled ? 0.18 : selectedSection && !selected ? 0.55 : 1} zoom={view.zoom} onEnter={enterSection} onMove={moveTooltip} onLeave={leaveSection} onSelect={selectSection} />;
          })}
          {guideCurve && <GuideLine guide={guideCurve} projection={projection} />}
          {lines.filter(({ section }) => section.name === selectedSection && (visibleStatuses?.has(statuses.get(section.name) ?? 'UNKNOWN') ?? true)).map(({ section }) => <polyline key={section.id} data-selected-section-line="" points={projectedLines.get(section.id)!.coordinates} fill="none" stroke="var(--color-accent-bright)" strokeWidth="3" strokeDasharray="7 5" vectorEffect="non-scaling-stroke" strokeLinecap="round" pointerEvents="none" aria-hidden="true" />)}
        </svg>
        <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1000 600" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
          <g fill="var(--color-text-primary)" stroke="var(--color-text-primary)" strokeWidth="2" fontSize="16"><text x="40" y="477" stroke="none">N</text><path d="M 45 515 L 45 484 M 38 494 L 45 484 L 52 494" fill="none"/><path d={`M 40 552 v -6 h ${scaleMeters * projection.scale * view.zoom} v 6 M 40 549 h ${scaleMeters * projection.scale * view.zoom}`} fill="none"/><text x="40" y="575" stroke="none">{scaleMeters} m</text></g>
        </svg>
        {hovered && activeName && <div ref={tooltipRef} role="tooltip" className="pointer-events-none absolute z-10 bg-surface-raised p-2 text-xs text-text-primary" style={{ left: tooltipPosition.current.x + 12, top: tooltipPosition.current.y + 12 }}><div>{activeName}</div><div>{activeStatus === 'UNKNOWN' ? t('plan_view.no_score') : t('status.' + activeStatus.toLowerCase())}</div><div>{t('plan_view.score')}: {activeScore == null ? '—' : `${activeScore.toFixed(1)} %`}</div></div>}
      </>}
      <div className="absolute left-2 top-2 bg-surface-raised"><SegmentedControl label={t('plan_view.title')} options={[{ value: 'evaluated', label: t('plan_view.evaluated_area') }, { value: 'full', label: t('plan_view.full_surface') }]} value={fullSurface ? 'full' : 'evaluated'} onChange={(value) => setFullSurface(value === 'full')} /></div>
      <div className="absolute right-2 top-2 flex flex-col bg-surface-raised text-text-primary">{([['zoom_in', '+', () => zoomAt(view.zoom * 1.5)], ['zoom_out', '−', () => zoomAt(view.zoom / 1.5)], ['zoom_reset', '↺', () => setView({ x: 0, y: 0, zoom: 1 })]] as const).map(([key, label, action]) => <button key={key} type="button" aria-label={t(`plan_view.${key}`)} className="h-8 w-8" onClick={action}>{label}</button>)}</div>
      <div className="absolute bottom-2 left-1/2 flex -translate-x-1/2 items-center gap-3 bg-surface-raised px-2 py-1 text-xs text-text-muted">{colorBy === 'status' ? <>{([['CUMPLE', 'passing'], ['FUERA', 'outside'], ['NO_CUMPLE', 'failing'], ['UNKNOWN', 'no_score']] as const).map(([status, label]) => <StatusLegendItem status={status} label={t(`plan_view.${label}`)} key={status} />)}</> : <><span>0 %</span><span aria-label={t('plan_view.color_scale')} className="h-2 w-32" style={{ background: 'linear-gradient(to right, #eb485d, #e68f19, #39ab60)' }} /><span>100 %</span></>}</div>
    </div>;
  }
  return (
    <SummaryPanel
      slot="compliance-plan-view"
      data-extent={projection ? `${projection.xMin},${projection.yMin},${projection.xMax},${projection.yMax}` : undefined}
      title={t('plan_view.title')}
      info={<InfoTip label={t('dashboard.kpi.how_calculated', { defaultValue: '¿Cómo se calcula?' })}>{t('plan_view.description')}</InfoTip>}
      actions={(
        <SegmentedControl
          label={t('plan_view.title')}
          options={[
            { value: 'evaluated', label: t('plan_view.evaluated_area') },
            { value: 'full', label: t('plan_view.full_surface') },
          ]}
          value={fullSurface ? 'full' : 'evaluated'}
          onChange={(value) => setFullSurface(value === 'full')}
        />
      )}
    >
      {loading ? <div className="flex aspect-[5/3] items-center justify-center"><Spinner /></div> : error || !projection || !lines.length ? <p className="flex aspect-[5/3] items-center justify-center text-sm text-text-muted">{t('plan_view.unavailable')}</p> : (
        <svg viewBox="0 0 1000 600" role="img" aria-label={t('plan_view.title')} className="w-full rounded-md bg-surface-sunken" style={{ maxHeight: 620 }}>
          <image href={raster || undefined} opacity={raster ? 1 : 0} className="transition-opacity duration-150 motion-reduce:transition-none" width="1000" height="600" />
          {Array.from({ length: 5 }, (_, index) => {
            const x = projection.xMin + (projection.xMax - projection.xMin) * index / 4;
            const y = projection.yMin + (projection.yMax - projection.yMin) * index / 4;
            const [px] = projectPlanPoint(x, y, projection);
            const [, py] = projectPlanPoint(x, y, projection);
            return <g key={index} fill="var(--color-text-muted)" fontSize="11">
              <text x={px} y="575" textAnchor="middle">{x.toFixed(0)}</text>
              <text x="48" y={py} textAnchor="end">{y.toFixed(0)}</text>
            </g>;
          })}
          <text x="500" y="596" textAnchor="middle" fill="var(--color-text-secondary)" fontSize="13">{t('plan_view.east')}</text>
          <text transform="translate(15 300) rotate(-90)" textAnchor="middle" fill="var(--color-text-secondary)" fontSize="13">{t('plan_view.north')}</text>
          {lines.map(({ section }) => {
            const projected = projectedLines.get(section.id)!;
            const [labelX, labelY] = labelPositions.get(section.id)!;
            return <PlanSection key={section.id} name={section.name} coordinates={projected.coordinates} firstX={projected.first![0]} firstY={projected.first![1]} endX={projected.endpoint![0]} endY={projected.endpoint![1]} status={statuses.get(section.name)} labelX={labelX} labelY={labelY} />;
          })}
        </svg>
      )}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        <StatusLegendItem status="CUMPLE" label={t('plan_view.passing')} />
        <StatusLegendItem status="FUERA" label={t('plan_view.outside')} />
        <StatusLegendItem status="NO_CUMPLE" label={t('plan_view.failing')} />
        <StatusLegendItem status="UNKNOWN" label={t('plan_view.no_score')} />
      </div>
    </SummaryPanel>
  );
}
