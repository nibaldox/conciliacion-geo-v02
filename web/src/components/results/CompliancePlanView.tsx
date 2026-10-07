import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMeshVertices, useSectionProfiles, useSections } from '../../api/hooks';
import type { ComparisonResult, SectionResponse } from '../../api/types';
import { useSession } from '../../stores/session';
import type { BenchStatus } from './ProfileView/domain/types';
import { Spinner } from '../ui/Spinner';
import { Button } from '../ui/Button';
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

export function CompliancePlanView({ results, statuses }: { results: readonly ComparisonResult[]; statuses: ReadonlyMap<string, BenchStatus> }) {
  const { t } = useTranslation();
  const [fullSurface, setFullSurface] = useState(false);
  const topoMeshId = useSession((state) => state.topoMeshId);
  const { data: vertices, isLoading, error } = useMeshVertices(topoMeshId);
  const { data: sections } = useSections();
  const names = new Set(results.map((row) => row.section));
  const visibleSections = sections?.filter((section) => names.has(section.name)) ?? [];
  const profiles = useSectionProfiles(visibleSections.map((section) => section.id));
  const lines = visibleSections.map((section, index) => ({ section, points: sectionPlanPoints(section, profiles[index]?.data) })).filter((line) => line.points.length >= 2);
  const [xMin, yMin, xMax, yMax] = planBounds(lines.flatMap((line) => line.points)) ?? [];
  const projection = useMemo(() => vertices ? createPlanProjection(vertices, !fullSurface && xMin !== undefined && yMin !== undefined && xMax !== undefined && yMax !== undefined ? [[xMin, yMin], [xMax, yMax]] : [], true) : null, [vertices, fullSurface, xMin, yMin, xMax, yMax]);
  const raster = useMemo(() => vertices && projection ? createSurfaceRaster(vertices, projection) : '', [vertices, projection]);
  const sorted = [...lines].sort((a, b) => a.points[a.points.length - 1]![0] - b.points[b.points.length - 1]![0]);
  const half = Math.ceil(sorted.length / 2);
  const labelPositions = new Map<string, [number, number]>();
  for (const [side, group] of [sorted.slice(0, half), sorted.slice(half)].entries()) {
    group.sort((a, b) => b.points[b.points.length - 1]![1] - a.points[a.points.length - 1]![1]);
    group.forEach((line, index) => labelPositions.set(line.section.id, [side === 0 ? 200 : 800, 60 + 480 * (index + 1) / (group.length + 1)]));
  }
  const loading = isLoading || profiles.some((profile) => profile.isLoading);
  return (
    <section data-slot="compliance-plan-view" data-extent={projection ? `${projection.xMin},${projection.yMin},${projection.xMax},${projection.yMax}` : undefined} className="rounded-xl border border-border bg-surface-raised p-5 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{t('plan_view.title')}</h3>
        <div className="flex gap-1">
          <Button size="sm" variant={fullSurface ? 'secondary' : 'primary'} aria-pressed={!fullSurface} onClick={() => setFullSurface(false)}>{t('plan_view.evaluated_area')}</Button>
          <Button size="sm" variant={fullSurface ? 'primary' : 'secondary'} aria-pressed={fullSurface} onClick={() => setFullSurface(true)}>{t('plan_view.full_surface')}</Button>
        </div>
      </div>
      <p className="text-xs text-text-muted">{t('plan_view.description')}</p>
      {loading ? <Spinner /> : error || !projection || !raster || !lines.length ? <p className="text-sm text-text-muted">{t('plan_view.unavailable')}</p> : (
        <svg viewBox="0 0 1000 600" role="img" aria-label={t('plan_view.title')} className="w-full rounded-lg bg-surface-sunken" style={{ maxHeight: 620 }}>
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
      <div className="flex flex-wrap gap-4 text-xs">
        <span style={{ color: 'var(--status-ok-text)' }}>● {t('plan_view.passing')}</span>
        <span style={{ color: 'var(--status-warn-text)' }}>● {t('plan_view.outside')}</span>
        <span style={{ color: 'var(--status-nok-text)' }}>● {t('plan_view.failing')}</span>
        <span className="text-text-muted">● {t('plan_view.no_score')}</span>
      </div>
    </section>
  );
}
