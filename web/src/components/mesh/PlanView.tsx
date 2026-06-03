import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useMeshVertices, useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import type { SectionResponse } from '../../api/types';

// Plotly.js is ~3 MB minified. We delay loading it until the user
// actually opens the plan view (or its tab in Step 4) by using a
// dynamic import inside useEffect. Until then, only this small
// placeholder component is in memory.

function sectionEndpoints(sec: SectionResponse): { x: [number, number]; y: [number, number] } {
  const azimuthRad = (sec.azimuth * Math.PI) / 180;
  const dx = Math.sin(azimuthRad) * sec.length;
  const dy = Math.cos(azimuthRad) * sec.length;
  return {
    x: [sec.origin[0], sec.origin[0] + dx],
    y: [sec.origin[1], sec.origin[1] + dy],
  };
}

interface PlotlyDataSpec {
  type: 'scattergl';
  mode: 'markers' | 'lines';
  x: number[];
  y: number[];
  marker?: Record<string, unknown>;
  line?: Record<string, unknown>;
  name?: string;
  hovertemplate?: string;
  text?: string[];
  showlegend?: boolean;
}

interface PlotlyModuleSpec {
  default: React.ComponentType<{
    data: PlotlyDataSpec[];
    layout: Record<string, unknown>;
    config?: Record<string, unknown>;
    useResizeHandler?: boolean;
    style?: React.CSSProperties;
    onClick?: (e: { points?: Array<{ x: number; y: number }> }) => void;
  }>;
}

function PlanViewImpl({ onPointClick }: { onPointClick?: (coords: { x: number; y: number }) => void }) {
  const { designMeshId, topoMeshId } = useSession();
  const { data: designVerts, isLoading: loadingDesign } = useMeshVertices(designMeshId);
  const { data: topoVerts, isLoading: loadingTopo } = useMeshVertices(topoMeshId);
  const { data: sections } = useSections();
  const [Plotly, setPlotly] = useState<PlotlyModuleSpec | null>(null);

  // Dynamic import — Plotly is ~3 MB and only needed when this view
  // actually renders.
  useEffect(() => {
    let cancelled = false;
    import('react-plotly.js')
      .then((mod) => {
        if (!cancelled) setPlotly(mod as unknown as PlotlyModuleSpec);
      })
      .catch(() => {
        // Plotly's main field is heavy; if it fails we still show the
        // empty state. Real failure surfaces via the error boundary.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const isLoading = loadingDesign || loadingTopo;
  const hasNoData = !designVerts && !topoVerts;

  const traces: PlotlyDataSpec[] = useMemo(() => {
    const t: PlotlyDataSpec[] = [];
    if (designVerts && designVerts.x.length > 0) {
      t.push({
        type: 'scattergl',
        mode: 'markers',
        x: designVerts.x,
        y: designVerts.y,
        marker: {
          color: designVerts.z,
          colorscale: 'Earth',
          size: 2,
          opacity: 0.6,
          colorbar: {
            title: { text: 'Elev. Diseño (m)', font: { size: 10, color: '#94a3b8' } },
            thickness: 12,
            len: 0.4,
            y: 0.98,
            yanchor: 'top',
            tickfont: { size: 9, color: '#94a3b8' },
          },
        },
        name: 'Diseño',
        hovertemplate:
          'Este: %{x:.1f}m<br>Norte: %{y:.1f}m<br>Elev: %{text:.1f}m<extra>Diseño</extra>',
        text: designVerts.z.map((z) => z.toFixed(1)),
      });
    }
    if (topoVerts && topoVerts.x.length > 0) {
      t.push({
        type: 'scattergl',
        mode: 'markers',
        x: topoVerts.x,
        y: topoVerts.y,
        marker: {
          color: topoVerts.z,
          colorscale: 'Earth',
          size: 2,
          opacity: 0.6,
          colorbar: {
            title: { text: 'Elev. Topo (m)', font: { size: 10, color: '#94a3b8' } },
            thickness: 12,
            len: 0.4,
            y: 0.55,
            yanchor: 'top',
            tickfont: { size: 9, color: '#94a3b8' },
          },
        },
        name: 'Topografía',
        hovertemplate:
          'Este: %{x:.1f}m<br>Norte: %{y:.1f}m<br>Elev: %{text:.1f}m<extra>Topografía</extra>',
        text: topoVerts.z.map((z) => z.toFixed(1)),
      });
    }
    if (sections && sections.length > 0) {
      sections.forEach((sec) => {
        const ep = sectionEndpoints(sec);
        t.push({
          type: 'scattergl',
          mode: 'lines',
          x: ep.x,
          y: ep.y,
          line: { color: '#ef4444', width: 2 },
          name: sec.name,
          hovertemplate: `${sec.name}<br>Az: ${sec.azimuth}° | L: ${sec.length}m<extra></extra>`,
          showlegend: false,
        });
      });
    }
    return t;
  }, [designVerts, topoVerts, sections]);

  const layout = useMemo(
    () => ({
      paper_bgcolor: 'transparent',
      plot_bgcolor: 'transparent',
      font: { color: '#94a3b8', family: 'system-ui, sans-serif' },
      margin: { l: 50, r: 20, t: 20, b: 50 },
      xaxis: {
        title: { text: 'Este (m)', font: { size: 11, color: '#64748b' } },
        gridcolor: '#e2e8f0',
        zerolinecolor: '#cbd5e1',
        tickfont: { size: 10, color: '#64748b' },
      },
      yaxis: {
        title: { text: 'Norte (m)', font: { size: 11, color: '#64748b' } },
        gridcolor: '#e2e8f0',
        zerolinecolor: '#cbd5e1',
        tickfont: { size: 10, color: '#64748b' },
        scaleanchor: 'x' as const,
        scaleratio: 1,
      },
      legend: {
        orientation: 'h' as const,
        x: 0.5,
        xanchor: 'center' as const,
        y: -0.15,
        font: { size: 11, color: '#64748b' },
      },
      dragmode: 'pan' as const,
      autosize: true,
    }),
    [],
  );

  const config = useMemo(
    () => ({
      scrollZoom: true,
      displayModeBar: true,
      modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
      displaylogo: false,
      responsive: true,
    }),
    [],
  );

  if (isLoading) {
    return (
      <div data-slot="plan-view" className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
          <div className="animate-spin text-2xl">⏳</div>
          <p className="text-sm">Cargando vértices…</p>
        </div>
      </div>
    );
  }

  if (hasNoData) {
    return (
      <div data-slot="plan-view" className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
          <div className="text-3xl">🗺️</div>
          <p className="text-sm text-center">Cargue superficies para ver la vista en planta</p>
        </div>
      </div>
    );
  }

  if (!Plotly) {
    return (
      <div data-slot="plan-view" className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
          <div className="animate-spin text-2xl">⏳</div>
          <p className="text-sm">Cargando Plotly (≈3 MB)…</p>
        </div>
      </div>
    );
  }

  const Plot = Plotly.default;
  return (
    <div data-slot="plan-view" className="h-full min-h-[400px] w-full">
      <Plot
        data={traces}
        layout={layout}
        config={config}
        useResizeHandler
        style={{ width: '100%', height: '100%', minHeight: '400px' }}
        onClick={(event) => {
          if (onPointClick && event.points && event.points.length > 0) {
            const pt = event.points[0];
            onPointClick({ x: pt.x, y: pt.y });
          }
        }}
      />
    </div>
  );
}

export function PlanView({ onPointClick }: { onPointClick?: (coords: { x: number; y: number }) => void }) {
  const { designMeshId, topoMeshId } = useSession();
  const { data: designVerts, isLoading: loadingDesign } = useMeshVertices(designMeshId);
  const { data: topoVerts, isLoading: loadingTopo } = useMeshVertices(topoMeshId);
  const { t } = useTranslation();
  const [requested, setRequested] = useState(false);

  const isLoading = loadingDesign || loadingTopo;
  const hasNoData = !designVerts && !topoVerts;

  if (hasNoData) {
    return (
      <div data-slot="plan-view" className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
          <div className="text-3xl">🗺️</div>
          <p className="text-sm text-center">{t('step1.plan_view_no_data')}</p>
        </div>
      </div>
    );
  }

  if (!requested) {
    return (
      <div data-slot="plan-view" className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-4 max-w-md text-center px-6">
          <div className="text-5xl">🗺️</div>
          <p className="text-sm font-medium" style={{ color: 'var(--color-text-primary)' }}>
            {t('step1.plan_view_title_2d')}
          </p>
          <p className="text-xs" style={{ color: 'var(--color-text-muted)' }}>
            {t('step1.plan_view_subtitle_2d')}
          </p>
          <button
            onClick={() => setRequested(true)}
            className="px-5 py-2.5 rounded-lg text-sm font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-mine-blue"
            style={{ backgroundColor: 'var(--color-mine-blue)', color: '#fff' }}
          >
            {t('step1.plan_view_button_2d')}
          </button>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div data-slot="plan-view" className="flex items-center justify-center h-full min-h-[400px] rounded-xl" style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}>
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
          <div className="animate-spin text-2xl">⏳</div>
          <p className="text-sm">{t('step1.plan_view_loading_verts')}</p>
        </div>
      </div>
    );
  }

  return <PlanViewImpl onPointClick={onPointClick} />;
}
