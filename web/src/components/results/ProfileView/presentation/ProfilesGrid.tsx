import { readThemeColor } from '../../../../utils/theme';
/**
 * ProfilesGrid — renders all processed sections as a 3-column grid
 * of compact ProfileChart thumbnails. Clicking a card selects the
 * section and switches to the single-profile view.
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import Plot from '../../../charts/Plot';
import type { Data, Layout } from 'plotly.js';
import { useSession } from '../../../../stores/session';
import { useSections, useProfile } from '../../../../api/hooks';
import type { SectionResponse } from '../../../../api/types';
import { useTheme } from '../../../../stores/theme';

// Share the queue across cards so a single idle task never mounts more than three plots.
const pendingCharts = new Set<() => void>();
let scheduled = false;
function scheduleCharts() {
  if (scheduled || pendingCharts.size === 0) return;
  scheduled = true;
  const run = () => {
    scheduled = false;
    for (const mount of Array.from(pendingCharts).slice(0, 3)) {
      pendingCharts.delete(mount);
      mount();
    }
    scheduleCharts();
  };
  if (typeof window.requestIdleCallback === 'function') window.requestIdleCallback(run, { timeout: 200 });
  else window.setTimeout(run, 0);
}

function useVisibleChart() {
  const ref = useRef<HTMLDivElement>(null);
  const [mounted, setMounted] = useState(() => typeof IntersectionObserver === 'undefined');
  useEffect(() => {
    const target = ref.current;
    if (!target || mounted || typeof IntersectionObserver === 'undefined') return;
    const mount = () => setMounted(true);
    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        pendingCharts.add(mount);
        scheduleCharts();
      } else pendingCharts.delete(mount);
    }, { rootMargin: '200px' });
    observer.observe(target);
    return () => { observer.disconnect(); pendingCharts.delete(mount); };
  }, [mounted]);
  return { ref, mounted };
}

function ChartFade({ children }: { children: React.ReactNode }) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setVisible(true));
    return () => cancelAnimationFrame(frame);
  }, []);
  return <div className="h-full transition-opacity duration-150 ease-[cubic-bezier(0.2,0,0,1)] motion-reduce:transition-none" style={{ opacity: visible ? 1 : 0 }}>{children}</div>;
}

// ─── Mini chart per section ────────────────────────────────

interface MiniCardProps {
  section: SectionResponse;
  onSelect: () => void;
  isSelected: boolean;
}

function MiniCard({ section, onSelect, isSelected }: MiniCardProps) {
  const { t } = useTranslation();
  const { isDark } = useTheme();
  const { data: profile, isPending, isError, refetch } = useProfile(section.id);
  const { ref: chartRef, mounted } = useVisibleChart();

  const gridColor = readThemeColor('--color-border', isDark ? '#1e293b' : '#e2e8f0');
  const designColor = readThemeColor('--color-mine-blue', '#7693b7');
  const topoColor = readThemeColor('--color-mine-green', '#4ade80');
  const tickColor = readThemeColor('--color-text-secondary', isDark ? '#bfccd9' : '#4b5563');
  const tickFont = { size: 10, color: tickColor };

  const plotData: Data[] = [];
  if (profile) {
    if (profile.design) {
      plotData.push({
        x: profile.design.distances,
        y: profile.design.elevations,
        type: 'scatter',
        mode: 'lines',
        name: 'Diseño',
        line: { color: designColor, width: 1.5 },
        showlegend: false,
      });
    }
    if (profile.topo) {
      plotData.push({
        x: profile.topo.distances,
        y: profile.topo.elevations,
        type: 'scatter',
        mode: 'lines',
        name: 'Topo',
        line: { color: topoColor, width: 1.5 },
        showlegend: false,
      });
    }
  }

  const layout: Partial<Layout> = {
    paper_bgcolor: 'transparent',
    plot_bgcolor: 'transparent',
    margin: { l: 28, r: 4, t: 4, b: 24 },
    xaxis: {
      showgrid: true,
      gridcolor: gridColor,
      zeroline: false,
      tickfont: tickFont,
      showticklabels: true,
    },
    yaxis: {
      showgrid: true,
      gridcolor: gridColor,
      zeroline: false,
      tickfont: tickFont,
      showticklabels: true,
      scaleanchor: 'x',
      scaleratio: 1,
    },
    autosize: true,
    hovermode: false,
  };

  return (
    <div
      className={[
        'border-b border-border transition-colors',
        isSelected ? 'border-accent-bright' : '',
      ].join(' ')}
    >
      <button
        type="button"
        aria-pressed={isSelected}
        onClick={onSelect}
        className="block w-full text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent"
      >
        <div className="flex items-baseline justify-between gap-2 px-3 pt-2">
          <span
            className="truncate text-sm font-medium"
            style={{ color: isSelected ? 'var(--color-accent-bright)' : 'var(--color-text-primary)' }}
          >
            {section.name}
          </span>
          {section.sector && (
            <span className="truncate text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              {section.sector}
            </span>
          )}
        </div>

        <div ref={chartRef} className="relative h-40">
          {isPending && !profile ? (
            <div role="status" aria-label={t('common.loading', { defaultValue: 'Cargando…' })} className="h-full bg-surface-sunken" />
          ) : !profile && isError ? (
            <div className="flex h-full items-center justify-center px-3 text-center text-xs text-text-muted">
              {t('profilesGrid.profileError', { defaultValue: 'No se pudo cargar este perfil.' })}
            </div>
          ) : plotData.length > 0 ? mounted ? (
            <ChartFade><Plot
              data={plotData}
              layout={layout}
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: '100%', height: '100%' }}
              useResizeHandler
            /></ChartFade>
          ) : <div aria-hidden="true" className="h-full bg-surface-sunken" /> : (
            <div className="flex h-full items-center justify-center px-3 text-center text-xs text-text-muted">
              {t('profilesGrid.profileEmpty', { defaultValue: 'Este perfil no tiene datos para mostrar.' })}
            </div>
          )}
        </div>
      </button>
      {isError && (
        <div className="flex items-center justify-center gap-2 border-t border-border px-3 py-1.5">
          {profile && (
            <span className="text-xs text-text-muted">
              {t('profilesGrid.profileRefreshError', { defaultValue: 'No se pudo actualizar este perfil.' })}
            </span>
          )}
          <button
            type="button"
            onClick={() => { void refetch(); }}
            className="rounded text-xs text-accent-bright underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          >
            {t('profilesGrid.retryProfile', { defaultValue: 'Reintentar perfil' })}
          </button>
        </div>
      )}
    </div>
  );
}

// ─── Grid ──────────────────────────────────────────────────

interface ProfilesGridProps {
  onSectionSelect?: (id: string) => void;
}

export function ProfilesGrid({ onSectionSelect }: ProfilesGridProps) {
  const { t } = useTranslation();
  const selectedSection = useSession((s) => s.selectedSection);
  const setSelectedSection = useSession((s) => s.setSelectedSection);
  const { data: sections, isLoading } = useSections();

  if (isLoading) {
    return (
      <div role="status" aria-label={t('common.loading', { defaultValue: 'Cargando…' })} className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((item) => <div key={item} className="h-40 bg-surface-sunken" />)}
      </div>
    );
  }

  if (!sections || sections.length === 0) {
    return (
      <div className="flex items-center justify-center py-16 text-text-muted">
        <p className="text-sm">{t('profilesGrid.empty', { defaultValue: 'No hay secciones procesadas.' })}</p>
      </div>
    );
  }

  const handleSelect = (sec: SectionResponse) => {
    setSelectedSection(sec.id);
    if (onSectionSelect) {
      onSectionSelect(sec.id);
    }
  };

  return (
    <div>
      <div className="mb-1 text-xs text-text-muted">{t('profilesGrid.axis_descriptions')}</div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {sections.map((sec) => (
          <MiniCard
            key={sec.id}
            section={sec}
            isSelected={selectedSection === sec.id}
            onSelect={() => handleSelect(sec)}
          />
        ))}
      </div>
    </div>
  );
}
