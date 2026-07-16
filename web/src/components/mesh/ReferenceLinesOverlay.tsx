import { type ChartDataset } from 'chart.js';
import type { ReferenceLine, ReferenceLinePoint } from '../../api/types';
import type { ContourBounds } from './ContourChart';

export interface ReferenceLinesOverlayProps {
  lines: ReferenceLine[];
  bounds?: ContourBounds;
}

/**
 * Build faint dashed Chart.js line datasets from reference polylines.
 *
 * The datasets use the same linear x/y parsing as the contour chart so the
 * overlay lines share the coordinate system without extra scaling.
 */
export function buildReferenceLineDatasets(
  lines: ReferenceLine[],
  isDark = false,
): ChartDataset<'line'>[] {
  const defaultColor = isDark ? 'rgba(255, 255, 255, 0.35)' : 'rgba(0, 0, 0, 0.35)';

  return lines.map((line) => {
    const points: { x: number; y: number }[] = line.points.map((p: ReferenceLinePoint) => ({
      x: p.x,
      y: p.y,
    }));

    return {
      label: line.name,
      data: points,
      borderColor: line.color ?? defaultColor,
      backgroundColor: 'transparent',
      borderWidth: 1,
      borderDash: [5, 5],
      pointRadius: 0,
      tension: 0,
      fill: false,
      spanGaps: false,
      parsing: false,
    };
  });
}

/**
 * Pure overlay component for reference lines on the 2D contour chart.
 *
 * It does not render its own DOM node; callers combine
 * `buildReferenceLineDatasets(lines)` into the chart's dataset list. The
 * component accepts bounds for future clip/validation use and remains
 * testable in isolation.
 */
export function ReferenceLinesOverlay({ lines, bounds }: ReferenceLinesOverlayProps) {
  // Bounds are intentionally accepted but unused today. This avoids a
  // future prop-drilling refactor when clipping is added.
  void bounds;
  void lines;
  return null;
}
