import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Chart,
  CategoryScale,
  LinearScale,
  LineElement,
  PointElement,
  Title,
  Tooltip,
  Legend,
  type ChartDataset,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import { useMeshContours, useSections, useReferenceLines } from '../../api/hooks';
import { useSession } from '../../stores/session';
import { useTheme } from '../../stores/theme';
import { ReferenceLinesOverlay, buildReferenceLineDatasets } from './ReferenceLinesOverlay';

Chart.register(CategoryScale, LinearScale, LineElement, PointElement, Title, Tooltip, Legend);

export interface ContourBounds {
  xmin: number;
  xmax: number;
  ymin: number;
  ymax: number;
}

export type ContourMeshMode = 'topo' | 'ambas' | 'design';
export type ContourResolution = 'low' | 'medium' | 'high';

/**
 * Compute the natural aspect ratio of the contour data so 1m
 * horizontal = 1m vertical on screen. Without this, Chart.js
 * stretches the y axis to fill the container, which visually
 * deforms the contour lines (steep slopes look like ripples).
 *
 * Falls back to 1 (square) when bounds are missing, zero, or
 * inverted. The fallback is a conservative default — better a
 * square chart than a divide-by-zero crash.
 */
export function computeContourAspectRatio(
  bounds: ContourBounds | undefined,
): number {
  if (!bounds) return 1;
  const dx = bounds.xmax - bounds.xmin;
  const dy = bounds.ymax - bounds.ymin;
  if (dx <= 0 || dy <= 0) return 1;
  return dx / dy;
}

const RESOLUTION_STRIDE: Record<ContourResolution, number> = {
  low: 4,
  medium: 2,
  high: 1,
};

export function ContourChart() {
  const { t } = useTranslation();
  const { designMeshId, topoMeshId } = useSession();
  const [meshMode, setMeshMode] = useState<ContourMeshMode>('topo');
  const [interval, setInterval] = useState(2.0);
  const [resolution, setResolution] = useState<ContourResolution>('medium');
  const stride = RESOLUTION_STRIDE[resolution];

  const activeDesignMeshId = meshMode === 'design' || meshMode === 'ambas' ? designMeshId : null;
  const activeTopoMeshId = meshMode === 'topo' || meshMode === 'ambas' ? topoMeshId : null;

  const designContours = useMeshContours(activeDesignMeshId, interval, stride);
  const topoContours = useMeshContours(activeTopoMeshId, interval, stride);
  const { data: sections } = useSections();
  const { data: referenceLinesData } = useReferenceLines(null);
  const { isDark } = useTheme();
  const referenceLines = referenceLinesData?.lines ?? [];

  const contourData = useMemo(() => {
    if (meshMode === 'design') return designContours.data;
    if (meshMode === 'topo') return topoContours.data;
    // 'ambas': overlay both meshes if both are available; otherwise fall back
    // to whichever is loaded.
    if (!designContours.data || !topoContours.data) {
      return designContours.data ?? topoContours.data;
    }
    return {
      ...designContours.data,
      lines: [...designContours.data.lines, ...topoContours.data.lines],
    };
  }, [meshMode, designContours.data, topoContours.data]);

  const isLoading = designContours.isLoading || topoContours.isLoading;
  const error = designContours.error || topoContours.error;

  const textColor = isDark ? '#a3a3a3' : '#6b7280';
  const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)';

  // Build Chart.js datasets — one dataset per contour level (elevation)
  // NaN creates a gap/break between segments of the same level
  const contourDatasets = useMemo<ChartDataset<'line'>[]>(() => {
    if (!contourData) return [];

    // Generate colors for elevation levels — blend from blue to red based on elevation
    const { elevation_min, elevation_max } = contourData;
    const range = elevation_max - elevation_min || 1;

    return contourData.lines.map((line) => {
      // Normalize elevation to [0,1] for color interpolation
      const t = (line.elevation - elevation_min) / range;
      // Blue (#2F5496) at low elev, warmer at high elev
      const r = Math.round(47 + t * 60);
      const g = Math.round(84 + t * 40);
      const b = Math.round(150 - t * 80);
      const color = `rgb(${r},${g},${b})`;

      // Flatten all segments into a single array with NaN separators
      const points: { x: number; y: number }[] = [];
      for (const segment of line.segments) {
        for (const [px, py] of segment) {
          points.push({ x: px, y: py });
        }
        // NaN gap between segments
        points.push({ x: NaN, y: NaN });
      }

      return {
        label: `${line.elevation.toFixed(0)} m`,
        data: points,
        borderColor: color,
        backgroundColor: 'transparent',
        borderWidth: 1.2,
        pointRadius: 0,
        tension: 0,
        fill: false,
        spanGaps: false,
        parsing: false,
      };
    });
  }, [contourData]);

  // Section line datasets
  const sectionDatasets = useMemo<ChartDataset<'line'>[]>(() => {
    if (!sections || sections.length === 0) return [];
    const secColor = isDark ? '#f87171' : '#ef4444';

    return sections.map((sec) => {
      const azRad = (sec.azimuth * Math.PI) / 180;
      const dx = Math.sin(azRad) * sec.length;
      const dy = Math.cos(azRad) * sec.length;
      const x1 = sec.origin[0] - dx / 2;
      const y1 = sec.origin[1] - dy / 2;
      const x2 = sec.origin[0] + dx / 2;
      const y2 = sec.origin[1] + dy / 2;

      return {
        label: sec.name,
        data: [
          { x: x1, y: y1 },
          { x: sec.origin[0], y: sec.origin[1] },
          { x: x2, y: y2 },
          { x: NaN, y: NaN },
        ],
        borderColor: secColor,
        backgroundColor: 'transparent',
        borderWidth: 2,
        pointRadius: 0,
        tension: 0,
        fill: false,
        spanGaps: false,
        parsing: false,
      };
    });
  }, [sections, isDark]);

  const referenceLineDatasets = useMemo<ChartDataset<'line'>[]>(
    () => buildReferenceLineDatasets(referenceLines, isDark),
    [referenceLines, isDark],
  );

  const allDatasets = useMemo(
    () => [...contourDatasets, ...sectionDatasets, ...referenceLineDatasets],
    [contourDatasets, sectionDatasets, referenceLineDatasets],
  );

  const chartData = useMemo(
    () => ({ datasets: allDatasets }),
    [allDatasets],
  );

  const chartOptions = useMemo(() => {
    const bounds = contourData?.bounds;
    // Compute the data's natural aspect ratio so 1m horizontal =
    // 1m vertical (a contour line that "looks square" on the
    // ground doesn't get squashed/stretched on screen).
    // Falls back to a square aspect if no bounds yet.
    const aspectRatio = computeContourAspectRatio(bounds as unknown as ContourBounds);

    return {
      responsive: true,
      maintainAspectRatio: true,  // honor the geo aspect ratio above
      aspectRatio,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: isDark ? '#1f1f1f' : '#fff',
          titleColor: isDark ? '#e5e5e5' : '#111',
          bodyColor: isDark ? '#a3a3a3' : '#374151',
          borderColor: isDark ? '#2e2e2e' : '#e5e7eb',
          borderWidth: 1,
          callbacks: {
            title: (items: any[]) => {
              const pt = items[0]?.element?.parsed;
              if (!pt) return '';
              return `(${pt.x.toFixed(1)}, ${pt.y.toFixed(1)})`;
            },
            label: (item: any) => item.dataset.label || '',
          },
        },
      },
      scales: {
        x: {
          type: 'linear' as const,
          title: {
            display: true,
            text: 'Este (m)',
            color: textColor,
            font: { size: 11 },
          },
          grid: { color: gridColor },
          ticks: { color: textColor, font: { size: 10 }, maxTicksLimit: 10 },
          border: { color: isDark ? '#2e2e2e' : '#e5e7eb' },
          ...(bounds ? { min: bounds.xmin, max: bounds.xmax } : {}),
        },
        y: {
          type: 'linear' as const,
          title: {
            display: true,
            text: 'Norte (m)',
            color: textColor,
            font: { size: 11 },
          },
          grid: { color: gridColor },
          ticks: { color: textColor, font: { size: 10 }, maxTicksLimit: 10 },
          border: { color: isDark ? '#2e2e2e' : '#e5e7eb' },
          // Lock y aspect to x so 1m horizontal = 1m vertical.
          // Without this, Chart.js stretches y to fill the container.
          ...(bounds ? { min: bounds.ymin, max: bounds.ymax } : {}),
        },
      },
    };
  }, [contourData, isDark, textColor, gridColor]);

  const requiredMeshId = meshMode === 'design'
    ? designMeshId
    : meshMode === 'topo'
      ? topoMeshId
      : (designMeshId ?? topoMeshId);

  if (!requiredMeshId) {
    return (
      <div
        className="flex items-center justify-center h-full rounded-xl"
        style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}
      >
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
          <div className="text-3xl">&#128230;</div>
          <p className="text-sm text-center px-4">
            Carga la superficie de diseño para ver las curvas de nivel
          </p>
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-center h-full rounded-xl"
        style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}
      >
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-text-muted)' }}>
          <div className="animate-spin text-2xl">⏳</div>
          <p className="text-sm">Generando curvas de nivel...</p>
        </div>
      </div>
    );
  }

  if (error || !contourData) {
    return (
      <div
        className="flex items-center justify-center h-full rounded-xl"
        style={{ backgroundColor: 'var(--color-surface-muted)', border: '1px solid var(--color-border)' }}
      >
        <div className="flex flex-col items-center gap-3" style={{ color: 'var(--color-mine-red)' }}>
          <div className="text-3xl">⚠️</div>
          <p className="text-sm">Error al cargar curvas de nivel</p>
        </div>
      </div>
    );
  }

  return (
    <div className="w-full h-full flex flex-col">
      <div
        className="flex flex-wrap items-center gap-4 px-3 py-2 text-sm"
        style={{ borderBottom: '1px solid var(--color-border)' }}
      >
        <fieldset className="flex items-center gap-2">
          <legend className="sr-only">{t('contour.mesh_label', 'Superficie')}</legend>
          <label className="flex items-center gap-1">
            <input
              type="radio"
              name="contour-mesh"
              value="topo"
              checked={meshMode === 'topo'}
              onChange={() => setMeshMode('topo')}
            />
            {t('contour.mesh_topo', 'Topografía')}
          </label>
          <label className="flex items-center gap-1">
            <input
              type="radio"
              name="contour-mesh"
              value="ambas"
              checked={meshMode === 'ambas'}
              onChange={() => setMeshMode('ambas')}
            />
            {t('contour.mesh_ambas', 'Ambas')}
          </label>
          <label className="flex items-center gap-1">
            <input
              type="radio"
              name="contour-mesh"
              value="design"
              checked={meshMode === 'design'}
              onChange={() => setMeshMode('design')}
            />
            {t('contour.mesh_design', 'Diseño')}
          </label>
        </fieldset>

        <label className="flex items-center gap-2">
          {t('contour.interval_label', 'Intervalo (m)')}
          <input
            type="range"
            min={0.5}
            max={10}
            step={0.5}
            value={interval}
            onChange={(e) => setInterval(parseFloat(e.target.value))}
            aria-label={t('contour.interval_label', 'Intervalo (m)')}
          />
          <span className="tabular-nums">{interval.toFixed(1)} m</span>
        </label>

        <label className="flex items-center gap-2">
          {t('contour.resolution_label', 'Resolución')}
          <select
            value={resolution}
            onChange={(e) => setResolution(e.target.value as ContourResolution)}
            aria-label={t('contour.resolution_label', 'Resolución')}
          >
            <option value="low">{t('contour.resolution_low', 'Baja')}</option>
            <option value="medium">{t('contour.resolution_medium', 'Media')}</option>
            <option value="high">{t('contour.resolution_high', 'Alta')}</option>
          </select>
        </label>
      </div>
      <div className="flex-1 min-h-0">
        <Line data={chartData} options={chartOptions} />
        <ReferenceLinesOverlay lines={referenceLines} bounds={contourData?.bounds as unknown as ContourBounds} />
      </div>
    </div>
  );
}
