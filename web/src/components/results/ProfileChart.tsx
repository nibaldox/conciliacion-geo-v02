import Plot from 'react-plotly.js';
import { useProfile } from '../../api/hooks';
import { useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';

export function ProfileChart() {
  const { selectedSection } = useSession();
  const { data: profile, isLoading, error } = useProfile(selectedSection);
  const { data: sections } = useSections();

  const sectionMeta = sections?.find((s) => s.id === selectedSection);

  // Loading state
  if (!selectedSection) {
    return (
      <div className="flex items-center justify-center h-96 text-gray-400 text-sm">
        Selecciona una sección para ver el perfil
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96 gap-3 text-gray-500">
        <svg className="animate-spin h-5 w-5 text-mine-blue" viewBox="0 0 24 24" fill="none">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        Cargando perfil...
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="flex items-center justify-center h-96 text-red-500 text-sm">
        Error al cargar el perfil de la sección
      </div>
    );
  }

  const hasDesign = profile.design && profile.design.distances.length > 0;
  const hasTopo = profile.topo && profile.topo.distances.length > 0;
  const hasRecDesign = profile.reconciled_design && profile.reconciled_design.distances.length > 0;
  const hasRecTopo = profile.reconciled_topo && profile.reconciled_topo.distances.length > 0;

  if (!hasDesign && !hasTopo) {
    return (
      <div className="flex items-center justify-center h-96 text-gray-400 text-sm">
        Sin datos de perfil disponibles para esta sección
      </div>
    );
  }

  const traces: Plotly.Data[] = [];

  if (hasDesign) {
    traces.push({
      x: profile.design!.distances,
      y: profile.design!.elevations,
      type: 'scatter',
      mode: 'lines',
      name: 'Diseño',
      line: { color: '#2F5496', width: 2.5, dash: 'solid' as const },
    });
  }

  if (hasTopo) {
    traces.push({
      x: profile.topo!.distances,
      y: profile.topo!.elevations,
      type: 'scatter',
      mode: 'lines',
      name: 'Topografía',
      line: { color: '#2E7D32', width: 2.5, dash: 'solid' as const },
    });
  }

  if (hasRecDesign) {
    traces.push({
      x: profile.reconciled_design!.distances,
      y: profile.reconciled_design!.elevations,
      type: 'scatter',
      mode: 'lines',
      name: 'Diseño (Reconciliado)',
      line: { color: '#2F5496', width: 1.5, dash: 'dash' as const },
    });
  }

  if (hasRecTopo) {
    traces.push({
      x: profile.reconciled_topo!.distances,
      y: profile.reconciled_topo!.elevations,
      type: 'scatter',
      mode: 'lines',
      name: 'Topografía (Reconciliada)',
      line: { color: '#2E7D32', width: 1.5, dash: 'dash' as const },
    });
  }

  const title = [
    profile.section_name,
    sectionMeta ? `Az: ${sectionMeta.azimuth.toFixed(1)}°` : '',
    profile.sector ? `Sector: ${profile.sector}` : '',
  ]
    .filter(Boolean)
    .join(' — ');

  return (
    <div className="w-full">
      <Plot
        data={traces}
        layout={{
          title: {
            text: title,
            font: { size: 14, color: '#333' },
          },
          xaxis: {
            title: { text: 'Distancia (m)', font: { size: 12 } },
            gridcolor: '#e5e7eb',
            zerolinecolor: '#d1d5db',
          },
          yaxis: {
            title: { text: 'Elevación (m)', font: { size: 12 } },
            gridcolor: '#e5e7eb',
            zerolinecolor: '#d1d5db',
          },
          legend: {
            orientation: 'h' as const,
            y: -0.15,
            x: 0.5,
            xanchor: 'center' as const,
            font: { size: 11 },
          },
          margin: { t: 50, r: 30, b: 80, l: 60 },
          paper_bgcolor: 'white',
          plot_bgcolor: 'white',
          autosize: true,
          height: 450,
        }}
        config={{
          responsive: true,
          scrollZoom: true,
          displayModeBar: true,
          modeBarButtonsToRemove: ['toImage'],
          displaylogo: false,
        }}
        style={{ width: '100%' }}
      />
    </div>
  );
}
