import { useMemo } from 'react';
import Plot from 'react-plotly.js';
import { useMeshVertices, useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import type { SectionResponse } from '../../api/types';

interface PlanViewProps {
  /** Optional callback when user clicks on the plan view (for interactive section placement) */
  onPointClick?: (coords: { x: number; y: number }) => void;
}

/** Compute section line endpoints from section metadata */
function sectionEndpoints(sec: SectionResponse): { x: [number, number]; y: [number, number] } {
  const azimuthRad = (sec.azimuth * Math.PI) / 180;
  const dx = Math.sin(azimuthRad) * sec.length;
  const dy = Math.cos(azimuthRad) * sec.length;
  return {
    x: [sec.origin[0], sec.origin[0] + dx],
    y: [sec.origin[1], sec.origin[1] + dy],
  };
}

export function PlanView({ onPointClick }: PlanViewProps) {
  const { designMeshId, topoMeshId } = useSession();
  const { data: designVerts, isLoading: loadingDesign } = useMeshVertices(designMeshId);
  const { data: topoVerts, isLoading: loadingTopo } = useMeshVertices(topoMeshId);
  const { data: sections } = useSections();

  const isLoading = loadingDesign || loadingTopo;
  const hasNoData = !designVerts && !topoVerts;

  // Build Plotly traces
  const traces = useMemo(() => {
    const t: Plotly.Data[] = [];

    // Design mesh — blue dots colored by elevation
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
        text: designVerts.z.map((z) => Number(z.toFixed(1))),
      });
    }

    // Topo mesh — green dots colored by elevation
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
        text: topoVerts.z.map((z) => Number(z.toFixed(1))),
      });
    }

    // Section lines as red lines
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

  // Plotly layout
  const layout: Partial<Plotly.Layout> = useMemo(
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
        scaleanchor: 'x',
        scaleratio: 1,
      },
      legend: {
        orientation: 'h',
        x: 0.5,
        xanchor: 'center',
        y: -0.15,
        font: { size: 11, color: '#64748b' },
      },
      dragmode: 'pan',
      autosize: true,
    }),
    [],
  );

  const config: Partial<Plotly.Config> = useMemo(
    () => ({
      scrollZoom: true,
      displayModeBar: true,
      modeBarButtonsToRemove: ['toImage', 'sendDataToCloud'],
      displaylogo: false,
      responsive: true,
    }),
    [],
  );

  // ── Loading state ──
  if (isLoading) {
    return (
      <div
        data-slot="plan-view"
        className="flex items-center justify-center h-full min-h-[400px] bg-gray-50 rounded-xl border border-gray-200"
      >
        <div className="flex flex-col items-center gap-3 text-gray-400">
          <div className="animate-spin text-2xl">⏳</div>
          <p className="text-sm">Cargando vértices…</p>
        </div>
      </div>
    );
  }

  // ── No data state ──
  if (hasNoData) {
    return (
      <div
        data-slot="plan-view"
        className="flex items-center justify-center h-full min-h-[400px] bg-gray-50 rounded-xl border border-gray-200"
      >
        <div className="flex flex-col items-center gap-3 text-gray-400">
          <div className="text-3xl">🗺️</div>
          <p className="text-sm text-center">
            Cargue superficies para ver la vista en planta
          </p>
        </div>
      </div>
    );
  }

  // ── Plot ──
  return (
    <div data-slot="plan-view" className="h-full min-h-[400px] w-full">
      <Plot
        data={traces}
        layout={layout}
        config={config}
        useResizeHandler
        style={{ width: '100%', height: '100%', minHeight: '400px' }}
        onClick={(event) => {
          if (onPointClick && event.points.length > 0) {
            const pt = event.points[0];
            onPointClick({ x: pt.x as number, y: pt.y as number });
          }
        }}
      />
    </div>
  );
}
