import { useCallback, useMemo, useRef, useState } from 'react';
import type { PointerEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useMeshVertices, useSectionProfiles, useSections } from '../../api/hooks';
import type { ComparisonResult, SectionResponse } from '../../api/types';
import { useSession } from '../../stores/session';
import type { BenchStatus } from './ProfileView/domain/types';
import { Spinner } from '../ui/Spinner';
import { InfoTip, SegmentedControl, StatusDot, SummaryPanel } from './SummaryControls';
import { planColor, sectionParameterPassRate, sectionScore, type PlanColorBy, type PlanStatusKey } from './planColors';

export type { PlanColorBy, PlanStatusKey } from './planColors';

import { createPlanProjection, createSurfaceRaster, projectPlanPoint, sectionPlanPoints, planBounds, type Projection } from './planGeometry';

export { createPlanProjection, projectPlanPoint } from './planGeometry';

function PlanSection({ section, points, projection, status, labelPosition }: { section: SectionResponse; points: [number, number][]; projection: Projection; status?: BenchStatus; labelPosition: [number, number] }) {
  const { t } = useTranslation();
  const state = status ?? 'UNKNOWN';
  const color = state === 'UNKNOWN' ? 'var(--color-text-muted)' : state === 'CUMPLE' ? 'var(--status-ok-text)' : state === 'FUERA' ? 'var(--status-warn-text)' : 'var(--status-nok-text)';
  const label = `${section.name} · ${state === 'UNKNOWN' ? t('plan_view.no_score') : t('status.' + state.toLowerCase())}`;
  const projected = points.map((point) => projectPlanPoint(...point, projection));
  const endpoint = labelPosition[0] < 500 ? projected[0]! : projected[projected.length - 1]!;
  return (
    <g data-section-name={section.name} data-compliance-status={state} data-status={state}>
      <title>{label}</title>
      <polyline points={projected.map((point) => point.join(',')).join(' ')} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />
      <line x1={endpoint[0]} y1={endpoint[1]} x2={labelPosition[0]} y2={labelPosition[1] - 4} stroke={color} strokeWidth="1" opacity="0.45" />
      <text x={labelPosition[0]} y={labelPosition[1]} textAnchor={labelPosition[0] < 500 ? 'end' : 'start'} fill={color} fontSize="14" fontWeight="600" stroke="var(--color-surface-sunken)" strokeWidth="3" paintOrder="stroke" strokeLinejoin="round">{section.name}</text>
    </g>
  );
}

export interface CompliancePlanViewProps {
  results: readonly ComparisonResult[];
  statuses: ReadonlyMap<string, BenchStatus>;
  variant?: 'panel' | 'hero';
  colorBy?: PlanColorBy;
  visibleStatuses?: ReadonlySet<PlanStatusKey>;
  selectedSection?: string | null;
  onSelectSection?: (name: string | null) => void;
}

export function CompliancePlanView({ results, statuses, variant = 'panel', colorBy = 'status', visibleStatuses, selectedSection, onSelectSection }: CompliancePlanViewProps) {
  const { t } = useTranslation();
  const [fullSurface, setFullSurface] = useState(false);
  const [hovered, setHovered] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState({ x: 0, y: 0 });
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 });
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);
  const suppressClick = useRef(false);
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
  const { data: vertices, isLoading, error } = useMeshVertices(topoMeshId);
  const { data: sections } = useSections();
  const names = new Set(results.map((row) => row.section));
  const visibleSections = sections?.filter((section) => names.has(section.name)) ?? [];
  const profiles = useSectionProfiles(visibleSections.map((section) => section.id));
  const lines = visibleSections.map((section, index) => ({ section, points: sectionPlanPoints(section, profiles[index]?.data) })).filter((line) => line.points.length >= 2);
  const [xMin, yMin, xMax, yMax] = planBounds(lines.flatMap((line) => line.points)) ?? [];
  const projection = useMemo(() => vertices ? createPlanProjection(vertices, !fullSurface && xMin !== undefined && yMin !== undefined && xMax !== undefined && yMax !== undefined ? [[xMin, yMin], [xMax, yMax]] : [], variant === 'panel') : null, [vertices, fullSurface, xMin, yMin, xMax, yMax, variant]);
  const raster = useMemo(() => vertices && projection ? createSurfaceRaster(vertices, projection) : '', [vertices, projection]);
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
    const activeScore = activeName ? sectionScore(results, activeName) : null;
    const choices = [10, 20, 50, 100, 200, 500];
    const desired = projection ? 120 / (projection.scale * view.zoom) : 10;
    const scaleMeters = choices.reduce((best, value) => Math.abs(value - desired) < Math.abs(best - desired) ? value : best, choices[0]!);
    return <div className="relative h-full w-full overflow-hidden bg-surface-sunken" onKeyDown={(event) => { if (event.key === 'Escape') onSelectSection?.(null); }}>
      {loading ? <div className="flex h-full items-center justify-center"><Spinner /></div> : error || !projection || !raster || !lines.length ? <p className="flex h-full items-center justify-center text-sm text-text-muted">{t('plan_view.unavailable')}</p> : <>
        <svg ref={svgRef} viewBox={`${view.x} ${view.y} ${width} ${height}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label={t('plan_view.title')} className="h-full w-full touch-none"
          onPointerDown={(event) => { if (event.button !== 0) return; drag.current = { x: event.clientX, y: event.clientY, moved: false }; (event.target as Element).setPointerCapture?.(event.pointerId); }}
          onPointerMove={move} onPointerUp={() => { suppressClick.current = drag.current?.moved ?? false; drag.current = null; }} onPointerCancel={() => { drag.current = null; }}
          onClick={() => { if (!suppressClick.current) onSelectSection?.(null); suppressClick.current = false; }}>
          <image href={raster} width="1000" height="600" />
          {lines.map(({ section, points }) => {
            const status = statuses.get(section.name) ?? 'UNKNOWN';
            const enabled = visibleStatuses?.has(status) ?? true;
            const selected = section.name === selectedSection;
            const focused = hovered === section.name || selected;
            const value = colorBy === 'status' ? status : colorBy === 'score' ? (() => { const score = sectionScore(results, section.name); return score == null ? null : score / 100; })() : sectionParameterPassRate(results, section.name, colorBy);
            const color = planColor(colorBy, value);
            const projected = points.map((point) => projectPlanPoint(...point, projection));
            const coordinates = projected.map((point) => point.join(',')).join(' ');
            const endpoint = projected[projected.length - 1]!;
            const statusLabel = status === 'UNKNOWN' ? t('plan_view.no_score') : t('status.' + status.toLowerCase());
            return <g key={section.id} data-section-name={section.name} data-status={status} opacity={!enabled ? 0.18 : selectedSection && !selected ? 0.55 : 1}
              role={enabled ? 'button' : undefined} tabIndex={enabled ? 0 : undefined} aria-label={enabled ? `${section.name} · ${statusLabel}` : undefined} aria-pressed={enabled ? selected : undefined}
              onMouseEnter={(event) => { if (!enabled) return; setHovered(section.name); const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect(); if (rect) setTooltip({ x: event.clientX - rect.left, y: event.clientY - rect.top }); }}
              onMouseMove={(event) => { const rect = event.currentTarget.ownerSVGElement?.getBoundingClientRect(); if (rect) setTooltip({ x: event.clientX - rect.left, y: event.clientY - rect.top }); }}
              onMouseLeave={() => setHovered(null)}
              onClick={(event) => { event.stopPropagation(); if (enabled && !suppressClick.current) onSelectSection?.(section.name); suppressClick.current = false; }}
              onKeyDown={(event) => { if (enabled && (event.key === 'Enter' || event.key === ' ')) { event.preventDefault(); onSelectSection?.(section.name); } }}>
              {selected && <polyline points={coordinates} fill="none" stroke="var(--color-text-primary)" strokeWidth="9" vectorEffect="non-scaling-stroke" strokeLinecap="round" />}
              <polyline data-plan-line="" points={coordinates} fill="none" stroke={color} strokeWidth={focused ? 5 : 3} vectorEffect="non-scaling-stroke" strokeLinecap="round" />
              {focused && <text x={endpoint[0]} y={endpoint[1]} dx={5 / view.zoom} dy={-5 / view.zoom} fill="var(--color-text-primary)" fontSize={14 / view.zoom} stroke="var(--color-surface-sunken)" strokeWidth={3 / view.zoom} paintOrder="stroke">{section.name}</text>}
              <polyline points={coordinates} fill="none" stroke="transparent" strokeWidth="14" vectorEffect="non-scaling-stroke" pointerEvents={enabled ? 'stroke' : 'none'} />
            </g>;
          })}
        </svg>
        <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 1000 600" preserveAspectRatio="xMidYMid meet" aria-hidden="true">
          <g fill="var(--color-text-primary)" stroke="var(--color-text-primary)" strokeWidth="2" fontSize="16"><text x="40" y="477" stroke="none">N</text><path d="M 45 515 L 45 484 M 38 494 L 45 484 L 52 494" fill="none"/><path d={`M 40 552 v -6 h ${scaleMeters * projection.scale * view.zoom} v 6 M 40 549 h ${scaleMeters * projection.scale * view.zoom}`} fill="none"/><text x="40" y="575" stroke="none">{scaleMeters} m</text></g>
        </svg>
        {hovered && activeName && <div role="tooltip" className="pointer-events-none absolute z-10 bg-surface-raised p-2 text-xs text-text-primary" style={{ left: tooltip.x + 12, top: tooltip.y + 12 }}><div>{activeName}</div><div>{activeStatus === 'UNKNOWN' ? t('plan_view.no_score') : t('status.' + activeStatus.toLowerCase())}</div><div>{t('plan_view.score')}: {activeScore == null ? '—' : `${activeScore.toFixed(1)} %`}</div></div>}
      </>}
      <div className="absolute left-2 top-2 bg-surface-raised"><SegmentedControl label={t('plan_view.title')} options={[{ value: 'evaluated', label: t('plan_view.evaluated_area') }, { value: 'full', label: t('plan_view.full_surface') }]} value={fullSurface ? 'full' : 'evaluated'} onChange={(value) => setFullSurface(value === 'full')} /></div>
      <div className="absolute right-2 top-2 flex flex-col bg-surface-raised text-text-primary">{([['zoom_in', '+', () => zoomAt(view.zoom * 1.5)], ['zoom_out', '−', () => zoomAt(view.zoom / 1.5)], ['zoom_reset', '↺', () => setView({ x: 0, y: 0, zoom: 1 })]] as const).map(([key, label, action]) => <button key={key} type="button" aria-label={t(`plan_view.${key}`)} className="h-8 w-8" onClick={action}>{label}</button>)}</div>
      <div className="absolute bottom-2 left-1/2 flex -translate-x-1/2 items-center gap-3 bg-surface-raised px-2 py-1 text-xs text-text-muted">{colorBy === 'status' ? <>{([['ok', 'passing'], ['warn', 'outside'], ['nok', 'failing'], ['muted', 'no_score']] as const).map(([tone, label]) => <span className="flex items-center gap-1" key={tone}><StatusDot tone={tone} />{t(`plan_view.${label}`)}</span>)}</> : <><span>0 %</span><span aria-label={t('plan_view.color_scale')} className="h-2 w-32" style={{ background: 'linear-gradient(to right, #eb485d, #e68f19, #39ab60)' }} /><span>100 %</span></>}</div>
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
      {loading ? <div className="flex aspect-[5/3] items-center justify-center"><Spinner /></div> : error || !projection || !raster || !lines.length ? <p className="flex aspect-[5/3] items-center justify-center text-sm text-text-muted">{t('plan_view.unavailable')}</p> : (
        <svg viewBox="0 0 1000 600" role="img" aria-label={t('plan_view.title')} className="w-full rounded-md bg-surface-sunken" style={{ maxHeight: 620 }}>
          <image href={raster} width="1000" height="600" />
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
          {lines.map(({ section, points }) => <PlanSection key={section.id} section={section} points={points} projection={projection} status={statuses.get(section.name)} labelPosition={labelPositions.get(section.id)!} />)}
        </svg>
      )}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-muted">
        <span className="flex items-center gap-1.5"><StatusDot tone="ok" />{t('plan_view.passing')}</span>
        <span className="flex items-center gap-1.5"><StatusDot tone="warn" />{t('plan_view.outside')}</span>
        <span className="flex items-center gap-1.5"><StatusDot tone="nok" />{t('plan_view.failing')}</span>
        <span className="flex items-center gap-1.5"><StatusDot tone="muted" />{t('plan_view.no_score')}</span>
      </div>
    </SummaryPanel>
  );
}
