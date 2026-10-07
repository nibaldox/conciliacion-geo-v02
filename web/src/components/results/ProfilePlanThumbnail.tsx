import { memo, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useMeshVerticesRoi, useSections, useSectionProfiles } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { Spinner } from '../ui/Spinner';
import { createPlanProjection, createSurfaceRaster, expandPlanBounds, projectPlanPoint, sectionPlanPoints, planBounds } from './planGeometry';

export const ProfilePlanThumbnail = memo(function ProfilePlanThumbnail({ sectionId }: { sectionId: string }) {
  const { t } = useTranslation();
  const topoMeshId = useSession((state) => state.topoMeshId);
  const { data: sections } = useSections();
  const active = sections?.find((section) => section.id === sectionId);
  const neighbours = useMemo(() => active ? [...(sections ?? [])]
    .filter((section) => section.id === active.id || section.sector === active.sector)
    .sort((a, b) => Math.hypot(a.origin[0] - active.origin[0], a.origin[1] - active.origin[1]) - Math.hypot(b.origin[0] - active.origin[0], b.origin[1] - active.origin[1]))
    .slice(0, 7) : [], [active, sections]);
  const profiles = useSectionProfiles(neighbours.map((section) => section.id));
  const lines = neighbours.map((section, index) => ({ section, points: sectionPlanPoints(section, profiles[index]?.data) })).filter((line) => line.points.length >= 2);
  const [xMin, yMin, xMax, yMax] = planBounds(lines.flatMap((line) => line.points)) ?? [];
  const roiBounds = xMin !== undefined && yMin !== undefined && xMax !== undefined && yMax !== undefined
    ? expandPlanBounds([xMin, yMin, xMax, yMax], 0.24)
    : null;
  const { data: vertices, isLoading, error } = useMeshVerticesRoi(topoMeshId, roiBounds);
  const hasActive = lines.some((line) => line.section.id === sectionId);
  const projection = useMemo(() => vertices && hasActive && xMin !== undefined && yMin !== undefined && xMax !== undefined && yMax !== undefined ? createPlanProjection(vertices, [[xMin, yMin], [xMax, yMax]], false, { width: 1000, height: 900 }, 0.24) : null, [vertices, hasActive, xMin, yMin, xMax, yMax]);
  const raster = useMemo(() => vertices && projection ? createSurfaceRaster(vertices, projection) : '', [vertices, projection]);
  const loading = isLoading || profiles.some((profile) => profile.isLoading);
  return (
    <section data-slot="profile-plan-thumbnail" data-active-section={sectionId} className="min-w-0 rounded-xl border border-border bg-surface-raised p-3 space-y-2">
      <h3 className="text-xs font-semibold">{t('profile_plan.title')}</h3>
      {loading ? <Spinner /> : error || !projection || !raster ? <p className="text-xs text-text-muted">{t('plan_view.unavailable')}</p> : (
        <svg viewBox="0 0 1000 900" className="aspect-[10/9] w-full rounded-md bg-surface-sunken" role="img" aria-label={t('profile_plan.active', { name: active?.name })}>
          <image href={raster} width="1000" height="900" />
          {[...lines].sort((a, b) => Number(a.section.id === sectionId) - Number(b.section.id === sectionId)).map(({ section, points }) => (
            <polyline key={section.id} data-section-id={section.id} data-active={section.id === sectionId}
              points={points.map((point) => projectPlanPoint(...point, projection).join(',')).join(' ')}
              fill="none" stroke={section.id === sectionId ? 'var(--color-accent-bright)' : 'var(--color-text-muted)'} strokeWidth={section.id === sectionId ? 12 : 5} strokeLinecap="round">
              <title>{section.name}</title>
            </polyline>
          ))}
          <path d="M930 110 V50 M912 72 L930 50 L948 72" stroke="var(--color-text-secondary)" strokeWidth="6" fill="none" />
          <text x="930" y="35" textAnchor="middle" fill="var(--color-text-secondary)" fontSize="40">N</text>
        </svg>
      )}
      <p className="text-xs text-accent-bright">{t('profile_plan.active', { name: active?.name ?? '—' })}</p>
      <p className="text-xs text-text-muted">{t('profile_plan.neighbours')}</p>
    </section>
  );
});
