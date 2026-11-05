import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMeshVertices, useSectionProfiles, useSections } from '../../api/hooks';
import type { ComparisonResult, SectionResponse } from '../../api/types';
import { useSession } from '../../stores/session';
import type { BenchStatus } from './ProfileView/domain/types';
import { Spinner } from '../ui/Spinner';
import { InfoTip, SegmentedControl, StatusDot, SummaryPanel } from './SummaryControls';
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
