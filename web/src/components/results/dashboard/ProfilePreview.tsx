import type { Data, Layout } from 'plotly.js';
import { useTranslation } from 'react-i18next';
import { useProfile } from '../../../api/hooks';
import { useTheme } from '../../../stores/theme';
import { readThemeColor } from '../../../utils/theme';
import Plot from '../../charts/Plot';
import { Spinner } from '../../ui/Spinner';

export function ProfilePreview({ sectionId, onOpen }: { sectionId: string; onOpen: () => void }) {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const { data: profile, isPending, isError, refetch } = useProfile(sectionId);
  const design = readThemeColor('--color-mine-blue', '#7693b7');
  const topo = readThemeColor('--color-mine-green', '#4ade80');
  const grid = readThemeColor('--color-border', isDark ? '#1e293b' : '#e2e8f0');
  const tick = readThemeColor('--color-text-secondary', isDark ? '#bfccd9' : '#4b5563');
  const data: Data[] = [];
  if (profile?.design) data.push({ x: profile.design.distances, y: profile.design.elevations, type: 'scatter', mode: 'lines', name: t('dashboard.rail.profile_design'), line: { color: design, width: 1.5 }, showlegend: false });
  if (profile?.topo) data.push({ x: profile.topo.distances, y: profile.topo.elevations, type: 'scatter', mode: 'lines', name: t('dashboard.rail.profile_topo'), line: { color: topo, width: 1.5 }, showlegend: false });
  const axis = { showgrid: true, gridcolor: grid, zeroline: false, tickfont: { size: 10, color: tick }, showticklabels: true };
  const layout: Partial<Layout> = { paper_bgcolor: 'transparent', plot_bgcolor: 'transparent', margin: { l: 28, r: 4, t: 4, b: 24 }, xaxis: axis, yaxis: { ...axis, scaleanchor: 'x', scaleratio: 1 }, autosize: true, hovermode: false };
  return <div data-slot="profile-preview" className="mb-3">
    <button type="button" aria-label={t('dashboard.rail.profile_preview')} onClick={onOpen} className="block h-[180px] w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent">
      {isPending && !profile ? <div className="flex h-full items-center justify-center"><Spinner size="sm" /></div> : isError && !profile ? <div className="flex h-full items-center justify-center text-text-muted">{t('profilesGrid.profileError')}</div> : data.length ? <Plot data={data} layout={layout} config={{ displayModeBar: false, responsive: true, staticPlot: true }} style={{ width: '100%', height: '100%' }} useResizeHandler /> : <div className="flex h-full items-center justify-center text-text-muted">{t('profilesGrid.profileEmpty')}</div>}
    </button>
    {isError && <div className="flex items-center gap-2 text-text-muted">{profile && <span>{t('profilesGrid.profileRefreshError')}</span>}<button type="button" onClick={() => { void refetch(); }} className="text-accent underline-offset-2 hover:underline">{t('profilesGrid.retryProfile')}</button></div>}
    <div className="flex flex-wrap gap-x-4 gap-y-1 text-text-secondary"><span><span className="mr-1 inline-block w-4 align-middle" style={{ borderTop: `2px solid ${design}` }} />{t('dashboard.rail.profile_design')}</span><span><span className="mr-1 inline-block w-4 align-middle" style={{ borderTop: `2px solid ${topo}` }} />{t('dashboard.rail.profile_topo')}</span></div>
  </div>;
}
