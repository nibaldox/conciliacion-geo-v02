import { describe, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import {
  buildBlastHoleGeometry,
  getBlastHoleKeyByInstanceId,
  getBlastHoleCollarColor,
  getBlastHoleLocalCollar,
  getBlastHoleMarkerColor,
  handleBlastHoleInstanceSelection,
  type BlastHole3D,
} from '../BlastHolesLayer';

describe('buildBlastHoleGeometry', () => {
  it('builds shared buffers and counts complete, collar-only, and excluded records', () => {
    const data = buildBlastHoleGeometry([
      { key: 'complete', collar: [1, 2, 3], toe: [4, 5, 6] },
      { key: 'collar-only', collar: [-1, 0, 2], toe: null },
      { key: 'no-collar', collar: null, toe: [0, 0, 0] },
      { key: 'invalid', collar: [0, Number.NaN, 0], toe: [1, 1, 1] },
    ]);

    expect(data.linePositions).toEqual(new Float32Array([1, 3, -2, 4, 6, -5]));
    expect(data.collarPositions).toEqual(new Float32Array([1, 3, -2, -1, 2, -0]));
    expect(data.markerBatches.map((batch) => batch.holes.map((hole) => hole.key))).toEqual([
      ['complete'], ['collar-only'],
    ]);
    expect(data.completeCount).toBe(1);
    expect(data.collarOnlyCount).toBe(1);
    expect(data.excludedCount).toBe(2);
  });

  it('does not manufacture a zero elevation for a missing collar', () => {
    const data = buildBlastHoleGeometry([{ key: 'missing-z', collar: [10, Number.NaN, 20] }]);
    expect(data.collarPositions).toHaveLength(0);
    expect(data.linePositions).toHaveLength(0);
    expect(data.excludedCount).toBe(1);
  });

  it('returns empty typed buffers for no holes', () => {
    const data = buildBlastHoleGeometry([]);
    expect(data.linePositions).toHaveLength(0);
    expect(data.collarPositions).toHaveLength(0);
    expect(data.completeCount + data.collarOnlyCount + data.excludedCount).toBe(0);
  });
});

describe('BlastHolesLayer selection', () => {
  const holes: BlastHole3D[] = [
    { key: 'first', collar: [0, 0, 1] as const, toe: [0, 0, 0] as const },
    { key: 'omitted', collar: null },
    { key: 'third', collar: [2, 0, 1] as const },
  ];

  it('maps instanced marker IDs to stable keys while skipping missing collars', () => {
    expect(getBlastHoleKeyByInstanceId(holes, 0)).toBe('first');
    expect(getBlastHoleKeyByInstanceId(holes, 1)).toBe('third');
    expect(getBlastHoleKeyByInstanceId(holes, 2)).toBeNull();
    expect(getBlastHoleKeyByInstanceId(holes, undefined)).toBeNull();
  });

  it('stops scene picking and selects the matching hole key', () => {
    const onSelect = vi.fn();
    const stopPropagation = vi.fn();
    handleBlastHoleInstanceSelection(holes, 1, onSelect, stopPropagation);
    expect(stopPropagation).toHaveBeenCalledOnce();
    expect(onSelect).toHaveBeenCalledWith('third');
  });

  it('stops propagation even for an unmapped instance and does not select a key', () => {
    const onSelect = vi.fn();
    const stopPropagation = vi.fn();
    handleBlastHoleInstanceSelection(holes, 9, onSelect, stopPropagation);
    expect(stopPropagation).toHaveBeenCalledOnce();
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('keeps the default marker color for complete and collar-only holes', () => {
    expect(getBlastHoleMarkerColor(holes[0], '#f97316', '#38bdf8')).toBe('#f97316');
    expect(getBlastHoleMarkerColor(holes[2], '#f97316', '#38bdf8')).toBe('#38bdf8');
  });

  it('ignores the data color of collars when collar coloring is disabled and keeps the line data color', () => {
    const hole: BlastHole3D = { key: 'colored', collar: [0, 0, 0], toe: [0, 0, -5], color: '#ff0000' };
    expect(getBlastHoleCollarColor(hole, '#f97316', '#38bdf8', false)).toBe('#f97316');
    expect(getBlastHoleCollarColor({ ...hole, toe: null }, '#f97316', '#38bdf8', false)).toBe('#38bdf8');
    expect(getBlastHoleCollarColor(hole, '#f97316', '#38bdf8', true)).toBe('#ff0000');
    expect(getBlastHoleCollarColor(hole, '#f97316', '#38bdf8')).toBe('#ff0000');
    const data = buildBlastHoleGeometry([hole]);
    const red = new THREE.Color('#ff0000');
    expect(Array.from(data.lineColors)).toEqual([red.r, red.g, red.b, red.r, red.g, red.b]);
  });

  it('keeps the data color for the selected marker and the line buffers', () => {
    const hole: BlastHole3D = { key: 'colored', collar: [0, 0, 0], toe: [0, 0, -5], color: '#ff0000' };
    expect(getBlastHoleMarkerColor(hole, '#f97316', '#38bdf8')).toBe('#ff0000');
    const data = buildBlastHoleGeometry([hole]);
    const red = new THREE.Color('#ff0000');
    expect(Array.from(data.lineColors)).toEqual([
      red.r, red.g, red.b, red.r, red.g, red.b,
    ]);
  });

  it('places the selection halo at the local collar of the selected hole only', () => {
    const haloHoles: BlastHole3D[] = [
      { key: 'a', collar: [10, 7, 20] as const },
      { key: 'b', collar: [-4, 3, 5] as const },
      { key: 'missing', collar: null },
    ];
    expect(getBlastHoleLocalCollar(haloHoles, 'b', [0, 0, 0])).toEqual([-4, 5, -3]);
    expect(getBlastHoleLocalCollar(haloHoles, 'b', [1, 2, 3])).toEqual([-5, 2, -1]);
    expect(getBlastHoleLocalCollar(haloHoles, 'missing', [0, 0, 0])).toBeNull();
    expect(getBlastHoleLocalCollar(haloHoles, 'unknown', [0, 0, 0])).toBeNull();
    expect(getBlastHoleLocalCollar(haloHoles, null, [0, 0, 0])).toBeNull();
  });

  it('returns the same selected hole from a batched Three.js raycast as the original flat instance list', () => {
    const selectedHoles: BlastHole3D[] = [
      { key: 'a', collar: [-30, 0, 0] as const },
      { key: 'b', collar: [15, 0, 0] as const },
      { key: 'c', collar: [410, 0, 0] as const },
    ];
    const data = buildBlastHoleGeometry(selectedHoles, [0, 0, 0]);
    const geometry = new THREE.SphereGeometry(0.35, 6, 4);
    const material = new THREE.MeshBasicMaterial();
    const flat = new THREE.InstancedMesh(geometry, material, selectedHoles.length);
    const matrix = new THREE.Matrix4();
    data.markerBatches.forEach((batch) => batch.holes.forEach((hole) => {
      const flatIndex = selectedHoles.indexOf(hole);
      matrix.makeScale(0.35, 0.35, 0.35);
      matrix.setPosition(...hole.collar!);
      flat.setMatrixAt(flatIndex, matrix);
    }));
    flat.instanceMatrix.needsUpdate = true;
    flat.computeBoundingSphere();
    const raycaster = new THREE.Raycaster(new THREE.Vector3(15, 0, 5), new THREE.Vector3(0, 0, -1), 0, 10);
    const flatHits: THREE.Intersection[] = [];
    flat.raycast(raycaster, flatHits);
    const batchedHits: Array<{ key: string; distance: number }> = [];
    for (const batch of data.markerBatches) {
      const mesh = new THREE.InstancedMesh(geometry, material, batch.holes.length);
      batch.holes.forEach((hole, index) => {
        matrix.makeScale(0.35, 0.35, 0.35);
        matrix.setPosition(...hole.collar!);
        mesh.setMatrixAt(index, matrix);
      });
      mesh.instanceMatrix.needsUpdate = true;
      mesh.computeBoundingSphere();
      const hits: THREE.Intersection[] = [];
      mesh.raycast(raycaster, hits);
      for (const hit of hits) {
        if (hit.instanceId !== undefined) batchedHits.push({ key: batch.holes[hit.instanceId]!.key, distance: hit.distance });
      }
    }

    expect(flatHits[0]).toBeDefined();
    const flatKey = selectedHoles[flatHits[0]!.instanceId!]?.key;
    batchedHits.sort((left, right) => left.distance - right.distance);
    expect(batchedHits[0]?.key).toBe(flatKey);
    expect(flatKey).toBe('b');
  });
});
