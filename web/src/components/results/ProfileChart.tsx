import { useRef, useEffect, useState } from 'react';
import {
  Chart,
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  type ChartDataset,
  type ScaleOptionsByType,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { useProfile } from '../../api/hooks';
import { useSections } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { useTheme } from '../../stores/theme';

Chart.register(CategoryScale, LinearScale, LineElement, PointElement, Title, Tooltip, Legend, Filler);

export function ProfileChart() {
  const { selectedSection } = useSession();
  const { data: profile, isLoading, error } = useProfile(selectedSection);
  const { data: sections } = useSections();
  const { isDark } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const [chartHeight, setChartHeight] = useState(400);

  useEffect(() => {
    const updateHeight = () => {
      if (containerRef.current) {
        const width = containerRef.current.offsetWidth;
        setChartHeight(Math.min(width, 600));
      }
    };
    updateHeight();
    window.addEventListener('resize', updateHeight);
    return () => window.removeEventListener('resize', updateHeight);
  }, []);

  const sectionMeta = sections?.find((s) => s.id === selectedSection);

  if (!selectedSection) {
    return (
      <div className="flex items-center justify-center h-96" style={{ color: 'var(--color-text-muted)' }}>
        Selecciona una sección para ver el perfil
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96 gap-3" style={{ color: 'var(--color-text-muted)' }}>
        <div className="w-5 h-5 border-2 rounded-full animate-spin" style={{ borderColor: 'var(--color-mine-blue)', borderTopColor: 'transparent' }} />
        Cargando perfil...
      </div>
    );
  }

  if (error || !profile) {
    return (
      <div className="flex items-center justify-center h-96" style={{ color: '#ef4444' }}>
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
      <div className="flex items-center justify-center h-96" style={{ color: 'var(--color-text-muted)' }}>
        Sin datos de perfil disponibles para esta sección
      </div>
    );
  }

  const title = [
    profile.section_name,
    sectionMeta ? `${sectionMeta.azimuth.toFixed(1)}°` : '',
    profile.sector || '',
  ].filter(Boolean).join(' — ');

  const textColor = isDark ? '#a3a3a3' : '#6b7280';
  const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';

  const datasets: ChartDataset<'line'>[] = [];

  if (hasDesign) {
    datasets.push({
      label: 'Diseño',
      data: profile.design!.elevations,
      borderColor: '#2F5496',
      backgroundColor: 'rgba(47,84,150,0.08)',
      borderWidth: 2.5,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0,
      fill: false,
    });
  }

  if (hasTopo) {
    datasets.push({
      label: 'Topografía',
      data: profile.topo!.elevations,
      borderColor: '#2E7D32',
      backgroundColor: 'rgba(46,125,50,0.08)',
      borderWidth: 2.5,
      pointRadius: 0,
      pointHoverRadius: 4,
      tension: 0,
      fill: false,
    });
  }

  if (hasRecDesign) {
    datasets.push({
      label: 'Diseño (Reconciliado)',
      data: profile.reconciled_design!.elevations,
      borderColor: '#2F5496',
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      borderDash: [5, 5],
      pointRadius: 0,
      pointHoverRadius: 3,
      tension: 0,
      fill: false,
    });
  }

  if (hasRecTopo) {
    datasets.push({
      label: 'Topografía (Reconciliada)',
      data: profile.reconciled_topo!.elevations,
      borderColor: '#2E7D32',
      backgroundColor: 'transparent',
      borderWidth: 1.5,
      borderDash: [5, 5],
      pointRadius: 0,
      pointHoverRadius: 3,
      tension: 0,
      fill: false,
    });
  }

  const labels = hasDesign
    ? profile.design!.distances
    : hasTopo
    ? profile.topo!.distances
    : [];

  const chartData = {
    labels,
    datasets,
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
    plugins: {
      legend: {
        position: 'bottom' as const,
        labels: {
          color: textColor,
          font: { size: 11, family: 'system-ui, sans-serif' },
          boxWidth: 30,
          padding: 16,
          usePointStyle: true,
          pointStyle: 'line',
        },
      },
      title: {
        display: true,
        text: title,
        color: isDark ? '#e5e5e5' : '#374151',
        font: { size: 13, weight: '500' as const, family: 'system-ui, sans-serif' },
        padding: { bottom: 20 },
      },
      tooltip: {
        backgroundColor: isDark ? '#1f1f1f' : '#fff',
        titleColor: isDark ? '#e5e5e5' : '#111',
        bodyColor: isDark ? '#a3a3a3' : '#374151',
        borderColor: isDark ? '#2e2e2e' : '#e5e7eb',
        borderWidth: 1,
        padding: 10,
        displayColors: true,
        callbacks: {
          title: (items: any[]) => `${items[0].label} m`,
          label: (item: any) => `${item.dataset.label}: ${item.raw} m`,
        },
      },
    },
    scales: {
      x: {
        type: 'linear' as const,
        title: {
          display: true,
          text: 'Distancia (m)',
          color: textColor,
          font: { size: 11 },
        },
        grid: {
          color: gridColor,
        },
        ticks: {
          color: textColor,
          font: { size: 10 },
        },
        border: {
          color: isDark ? '#2e2e2e' : '#e5e7eb',
        },
      },
      y: {
        title: {
          display: true,
          text: 'Elevación (m)',
          color: textColor,
          font: { size: 11 },
        },
        grid: {
          color: gridColor,
        },
        ticks: {
          color: textColor,
          font: { size: 10 },
        },
        border: {
          color: isDark ? '#2e2e2e' : '#e5e7eb',
        },
      },
    },
    interaction: {
      mode: 'index' as const,
      intersect: false,
    },
  };

  return (
    <div ref={containerRef} className="w-full" style={{ height: chartHeight }}>
      <Line
        data={chartData}
        options={chartOptions}
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  );
}
