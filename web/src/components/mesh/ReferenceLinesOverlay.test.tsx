import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import {
  ReferenceLinesOverlay,
  buildReferenceLineDatasets,
} from './ReferenceLinesOverlay';
import type { ReferenceLine } from '../../api/types';

describe('ReferenceLinesOverlay', () => {
  it('renders 0 polylines when no lines', () => {
    const datasets = buildReferenceLineDatasets([]);
    expect(datasets).toHaveLength(0);
  });

  it('renders N polylines when N lines present', () => {
    const lines: ReferenceLine[] = [
      {
        id: '1',
        name: 'malla-a',
        color: '#ff0000',
        points: [
          { x: 0, y: 0 },
          { x: 10, y: 10 },
        ],
      },
      {
        id: '2',
        name: 'malla-b',
        points: [
          { x: 5, y: 0 },
          { x: 5, y: 10 },
        ],
      },
    ];

    const datasets = buildReferenceLineDatasets(lines);
    expect(datasets).toHaveLength(2);

    const first = datasets[0];
    expect(first.label).toBe('malla-a');
    expect(first.borderColor).toBe('#ff0000');
    expect(first.data).toEqual([
      { x: 0, y: 0 },
      { x: 10, y: 10 },
    ]);
    expect(first.borderDash).toEqual([5, 5]);
    expect(first.pointRadius).toBe(0);

    const second = datasets[1];
    expect(second.label).toBe('malla-b');
    expect(second.data).toEqual([
      { x: 5, y: 0 },
      { x: 5, y: 10 },
    ]);
  });

  it('passes through bounds correctly', () => {
    const bounds = { xmin: 0, xmax: 100, ymin: 0, ymax: 100 };
    const { container } = render(
      <ReferenceLinesOverlay lines={[]} bounds={bounds} />,
    );
    expect(container.firstChild).toBeNull();
  });
});
