/**
 * ProfilesGrid — renders all processed sections as a 3-column grid
 * of compact ProfileChart thumbnails. Clicking a card selects the
 * section and switches to the single-profile view.
 */

import { useTranslation } from 'react-i18next';
import Plot from 'react-plotly.js';
import type { Data, Layout } from 'plotly.js';
import { useSession } from '../../../../stores/session';
import { useSections, useProfile } from '../../../../api/hooks';
import type { SectionResponse } from '../../../../api/types';
import { Spinner } from '../../../ui/Spinner';
import { useTheme } from '../../../../stores/theme';

// ─── Mini chart per section ────────────────────────────────

interface MiniCardProps {
  section: SectionResponse;
  onSelect: () => void;
  isSelected: boolean;
}

function MiniCard({ section, onSelect, isSelected }: MiniCardProps) {
  const { isDark } = useTheme();
  const { data: profile } = useProfile(section.id);

  const gridColor = isDark ? '#1e293b' : '#e2e8f0';
  const designColor = '#7693b7';
  const topoColor = '#4ade80';

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
      tickfont: { size: 7, color: isDark ? '#64748b' : '#94a3b8' },
      showticklabels: true,
    },
    yaxis: {
      showgrid: true,
      gridcolor: gridColor,
      zeroline: false,
      tickfont: { size: 7, color: isDark ? '#64748b' : '#94a3b8' },
      showticklabels: true,
      scaleanchor: 'x',
      scaleratio: 1,
    },
    autosize: true,
    hovermode: false,
  };

  return (
    <button
      type="button"
      onClick={onSelect}
      className="rounded-xl overflow-hidden text-left transition-all hover:scale-[1.01] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      style={{
        border: isSelected
          ? '2px solid var(--color-accent-bright)'
          : '1px solid var(--color-border)',
        backgroundColor: 'var(--color-surface-raised)',
        boxShadow: isSelected ? 'var(--shadow-glow-accent)' : 'none',
      }}
    >
      {/* Header */}
      <div
        className="px-3 py-1.5 flex items-center justify-between gap-2 border-b"
        style={{ borderColor: 'var(--color-border)', backgroundColor: 'var(--color-surface)' }}
      >
        <span
          className="text-xs font-mono font-semibold truncate"
          style={{ color: isSelected ? 'var(--color-accent-bright)' : 'var(--color-text-primary)' }}
        >
          {section.name}
        </span>
        {section.sector && (
          <span
            className="text-[10px] font-mono px-1.5 py-0.5 rounded"
            style={{
              color: 'var(--color-text-muted)',
              backgroundColor: 'var(--color-surface-muted)',
            }}
          >
            {section.sector}
          </span>
        )}
      </div>

      {/* Chart */}
      <div style={{ height: 160, position: 'relative' }}>
        {!profile ? (
          <div
            className="flex items-center justify-center h-full"
            style={{ color: 'var(--color-text-dim)' }}
          >
            <Spinner size="sm" />
          </div>
        ) : (
          <Plot
            data={plotData}
            layout={layout}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: '100%' }}
            useResizeHandler
          />
        )}
      </div>
    </button>
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
      <div className="flex items-center justify-center py-16 gap-3" style={{ color: 'var(--color-text-muted)' }}>
        <Spinner />
        <span className="text-sm">{t('common.loading', { defaultValue: 'Cargando…' })}</span>
      </div>
    );
  }

  if (!sections || sections.length === 0) {
    return (
      <div
        className="flex items-center justify-center py-16 rounded-xl"
        style={{
          border: '1px dashed var(--color-border)',
          color: 'var(--color-text-muted)',
        }}
      >
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
    <div
      className="grid gap-3"
      style={{ gridTemplateColumns: 'repeat(3, minmax(0, 1fr))' }}
    >
      {sections.map((sec) => (
        <MiniCard
          key={sec.id}
          section={sec}
          isSelected={selectedSection === sec.name}
          onSelect={() => handleSelect(sec)}
        />
      ))}
    </div>
  );
}
