// T13: aristas de curva (2 y 100k vértices), curvas próximas a escala UTM, vista oblicua con DPR, identidad de geometría, cierre y coste de interacción en el picking (T04) y la vista previa.
import { describe, expect, it } from 'vitest';
import { PerspectiveCamera, Vector3 } from 'three';
import { pickCurveCandidate } from '../curvePicking';
import type { CurvePickCandidate, CurvePickingInput } from '../curvePicking';
import { buildCurveSelectionVisuals } from '../curveSelectionVisuals';
import { createCurveAnchor } from '../../sections/curveAnchorGeometry';
import { getCurveGeometrySnapshot } from '../../sections/curveGeometryAdapter';
import type { CurveGeometrySnapshot } from '../../sections/curveGeometryAdapter';
import { createCurveSelectionState } from '../../sections/curveSelectionState';
import type { CurveAnchor, CurveSelectionContext, MiningPoint3D } from '../../sections/curveSelectionTypes';
import type { ContourData } from '../../../api/types';

const viewport = { width: 800, height: 600 };

function obliqueCamera(): PerspectiveCamera {
  const camera = new PerspectiveCamera(50, viewport.width / viewport.height, 0.5, 500);
  camera.position.set(6, 5, 9);
  camera.lookAt(0, 0, 0);
  camera.updateProjectionMatrix();
  camera.updateMatrixWorld(true);
  return camera;
}

function cssOf(position: MiningPoint3D, camera: PerspectiveCamera, center: MiningPoint3D): { x: number; y: number } {
  const ndc = new Vector3(
    position[0] - center[0],
    position[2] - center[2],
    -(position[1] - center[1]),
  ).project(camera);
  return { x: (ndc.x * 0.5 + 0.5) * viewport.width, y: (0.5 - ndc.y * 0.5) * viewport.height };
}

function anchorFor(
  context: CurveSelectionContext,
  curveId: string,
  position: MiningPoint3D,
  overrides: Partial<Omit<CurveAnchor, 'context' | 'curveId' | 'position'>> = {},
): CurveAnchor {
  return { context, curveId, segmentIndex: 0, t: 0.5, chainage: 10, position, ...overrides };
}

function inputFor(
  candidates: readonly CurvePickCandidate[],
  camera: PerspectiveCamera,
  opts: Partial<CurvePickingInput> = {},
): CurvePickingInput {
  return {
    candidates,
    context,
    selectedCurveId: 'curva-a',
    camera,
    center: [0, 0, 0],
    viewport,
    pointer: { x: 400, y: 300 },
    ...opts,
  };
}

function withDevicePixelRatio(dpr: number, run: () => void): void {
  const previous = Object.getOwnPropertyDescriptor(window, 'devicePixelRatio');
  Object.defineProperty(window, 'devicePixelRatio', { value: dpr, configurable: true });
  try {
    run();
  } finally {
    if (previous) {
      Object.defineProperty(window, 'devicePixelRatio', previous);
    } else {
      Reflect.deleteProperty(window, 'devicePixelRatio');
    }
  }
}

function contour(lines: ContourData['lines']): ContourData {
  return { bounds: {}, elevation_min: 0, elevation_max: 0, interval: 5, lines };
}

const context: CurveSelectionContext = { designMeshId: 'mesh-t13', geometryKey: 'geo-t13' };
const utmCenter: MiningPoint3D = [700000, 7200000, 3000];

describe('picking: pocos y muchos vértices (T04)', () => {
  it('selecciona el interior de una curva de dos vértices y el último segmento de una de 100k', () => {
    const camera = obliqueCamera();
    const two: MiningPoint3D[] = [
      [0, 0, 0],
      [4, 0, 0],
    ];
    const mid = createCurveAnchor({ context, curveId: 'curva-a', points: two, segmentIndex: 0, t: 0.5 });
    if (!mid) throw new Error('ancla no generable');
    const midCss = cssOf(mid.position, camera, [0, 0, 0]);
    expect(pickCurveCandidate(inputFor([{ anchor: mid, visible: true }], camera, { pointer: midCss }))).toBe(mid);

    const many: MiningPoint3D[] = [];
    for (let i = 0; i < 100000; i += 1) many.push([i * 0.00005, 0, 0]);
    const last = createCurveAnchor({ context, curveId: 'curva-a', points: many, segmentIndex: 99998, t: 0.5 });
    if (!last) throw new Error('ancla no generable');
    const lastCss = cssOf(last.position, camera, [0, 0, 0]);
    expect(pickCurveCandidate(inputFor([{ anchor: last, visible: true }], camera, { pointer: lastCss }))).toBe(last);
  });
});

describe('picking: curvas paralelas próximas a escala UTM', () => {
  it('no selecciona la vecina más cercana cuando hay curva activa y no cae a la vecina sin candidato propio', () => {
    const camera = obliqueCamera();
    const active = anchorFor(context, 'curva-a', [700000.1, 7200000, 3000]);
    const neighbor = anchorFor(context, 'curva-b', [700000.0, 7200000, 3000]);
    const activeCss = cssOf(active.position, camera, utmCenter);
    const neighborCss = cssOf(neighbor.position, camera, utmCenter);
    const gap = Math.hypot(activeCss.x - neighborCss.x, activeCss.y - neighborCss.y);
    expect(gap).toBeGreaterThan(0);
    expect(gap).toBeLessThanOrEqual(8);

    const candidates = [
      { anchor: active, visible: true },
      { anchor: neighbor, visible: true },
    ];
    expect(
      pickCurveCandidate(inputFor(candidates, camera, { center: utmCenter, pointer: neighborCss })),
    ).toBe(active);

    const farActive = anchorFor(context, 'curva-a', [700000.3, 7200000, 3000]);
    const farCss = cssOf(farActive.position, camera, utmCenter);
    const farGap = Math.hypot(farCss.x - neighborCss.x, farCss.y - neighborCss.y);
    expect(farGap).toBeGreaterThan(8);
    expect(
      pickCurveCandidate(inputFor(
        [
          { anchor: farActive, visible: true },
          { anchor: neighbor, visible: true },
        ],
        camera,
        { center: utmCenter, pointer: neighborCss },
      )),
    ).toBeNull();
  });
});

describe('picking: vista oblicua y DPR', () => {
  it('acepta dentro del radio CSS (inclusive por margen) y lo rechaza fuera, sin depender de devicePixelRatio', () => {
    const camera = obliqueCamera();
    const offAxis = anchorFor(context, 'curva-a', [2, 7, 1.5]);
    const offCss = cssOf(offAxis.position, camera, [0, 0, 0]);
    const candidates = [{ anchor: offAxis, visible: true }];
    const at = (x: number): CurveAnchor | null =>
      pickCurveCandidate(inputFor(candidates, camera, { pointer: { x, y: offCss.y } }));

    expect(pickCurveCandidate(inputFor(candidates, camera, { pointer: offCss }))).toBe(offAxis);
    expect(at(offCss.x + 7.5)).toBe(offAxis);
    expect(at(offCss.x + 8.5)).toBeNull();
    expect(pickCurveCandidate(inputFor(candidates, camera, { pointer: { x: offCss.x, y: offCss.y + 7.5 } }))).toBe(offAxis);
    expect(pickCurveCandidate(inputFor(candidates, camera, { pointer: { x: offCss.x, y: offCss.y + 8.5 } }))).toBeNull();

    withDevicePixelRatio(3, () => {
      expect(pickCurveCandidate(inputFor(candidates, camera, { pointer: offCss }))).toBe(offAxis);
      expect(at(offCss.x + 7.5)).toBe(offAxis);
      expect(at(offCss.x + 8.5)).toBeNull();
    });
  });
});

describe('picking: identidad de geometría obsoleta', () => {
  it('rechaza un ancla de un snapshot reemplazado y acepta la del snapshot actual', () => {
    const build = (): ContourData => contour([{ elevation: 5, segments: [[[0, 0], [100, 0]]] }]);
    const snapA = getCurveGeometrySnapshot('mesh-t13', build());
    const snapB = getCurveGeometrySnapshot('mesh-t13', build());
    if (!snapA || !snapB) throw new Error('snapshot incompleto');
    expect(snapB.context.geometryKey).not.toBe(snapA.context.geometryKey);

    const stale = anchorFor(snapA.context, '0-0', [2, 0, 5]);
    const current = anchorFor(snapB.context, '0-0', [2, 0, 5]);
    const camera = obliqueCamera();
    const pointer = cssOf(current.position, camera, [0, 0, 0]);
    const candidates = [
      { anchor: stale, visible: true },
      { anchor: current, visible: true },
    ];
    expect(
      pickCurveCandidate(inputFor(candidates, camera, { context: snapB.context, selectedCurveId: '0-0', pointer })),
    ).toBe(current);
    expect(
      pickCurveCandidate(inputFor([{ anchor: stale, visible: true }], camera, {
        context: snapB.context,
        selectedCurveId: '0-0',
        pointer,
      })),
    ).toBeNull();
  });
});

describe('vista previa: curva cerrada y tamaño de buffer', () => {
  const ring: readonly MiningPoint3D[] = [
    [0, 0, 0],
    [100, 0, 0],
    [100, 100, 0],
    [0, 0, 0],
  ];

  function ringSnapshot(): CurveGeometrySnapshot {
    return { context, curves: new Map([['curva-a', { id: 'curva-a', points: ring }]]) };
  }

  it('previsualiza el recorrido directo cerrado manteniendo inicio y fin distintos', () => {
    const start = createCurveAnchor({ context, curveId: 'curva-a', points: ring, segmentIndex: 0, t: 0 });
    const end = createCurveAnchor({ context, curveId: 'curva-a', points: ring, segmentIndex: 2, t: 1 });
    if (!start || !end) throw new Error('anclas no generables');
    const data = buildCurveSelectionVisuals({
      snapshot: ringSnapshot(),
      selection: { ...createCurveSelectionState(context), curveId: 'curva-a', start, end, rejection: null },
      center: [0, 0, 0],
    });
    expect(data.range).toHaveLength(4);
    expect(data.range?.[0]).toEqual(data.range?.[3]);
    expect(data.start).toEqual([0, 0, 0]);
    expect(data.end).toEqual([0, 0, 0]);
    expect(data.rangePositions?.length).toBe(12);
  });

  it('mantiene el buffer de recorte de tamaño fijo entre llamadas y nulo para solo-inicio', () => {
    const points: MiningPoint3D[] = [];
    for (let i = 0; i < 2000; i += 1) points.push([i, 0, 0]);
    const snapshot: CurveGeometrySnapshot = { context, curves: new Map([['curva-a', { id: 'curva-a', points }]]) };
    const start = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 0, t: 0 });
    const end = createCurveAnchor({ context, curveId: 'curva-a', points, segmentIndex: 1000, t: 0.5 });
    if (!start || !end) throw new Error('anclas no generables');
    const selection = { ...createCurveSelectionState(context), curveId: 'curva-a', start, end, rejection: null };
    const first = buildCurveSelectionVisuals({ snapshot, selection, center: [0, 0, 0] });
    const second = buildCurveSelectionVisuals({ snapshot, selection, center: [10, 0, 0] });
    const rangeLength = first.range?.length ?? 0;
    expect(rangeLength).toBeGreaterThan(1000);
    expect(first.rangePositions?.length).toBe(rangeLength * 3);
    expect(second.rangePositions?.length).toBe(rangeLength * 3);
    expect(first.rangePositions?.length).toBe(second.rangePositions?.length);

    const onlyStart = { ...createCurveSelectionState(context), curveId: 'curva-a', start, end: null, rejection: null };
    const preview = buildCurveSelectionVisuals({ snapshot, selection: onlyStart, center: [0, 0, 0] });
    expect(preview.rangePositions).toBeNull();
    expect(preview.range).toBeNull();
    expect(preview.start).toEqual([0, 0, 0]);
  });
});

function denseCandidates(curveId: string, count: number, anchorContext: CurveSelectionContext): CurvePickCandidate[] {
  const list: CurvePickCandidate[] = [];
  for (let i = 0; i < count; i += 1) {
    list.push({
      anchor: {
        context: anchorContext,
        curveId,
        segmentIndex: i,
        t: 0.5,
        position: [i * 0.001 - count * 0.0005, 0, 0],
        chainage: i,
      },
      visible: true,
    });
  }
  return list;
}

function bench(fn: () => void, iterations: number): { medianMs: number; p95Ms: number; iterations: number } {
  const warmup = Math.min(5, iterations);
  for (let i = 0; i < warmup; i += 1) fn();
  const samples: number[] = [];
  for (let i = 0; i < iterations; i += 1) {
    const start = performance.now();
    fn();
    samples.push(performance.now() - start);
  }
  samples.sort((a, b) => a - b);
  const median = samples[Math.floor(samples.length * 0.5)] ?? 0;
  const p95 = samples[Math.min(samples.length - 1, Math.ceil(samples.length * 0.95) - 1)] ?? 0;
  return { medianMs: Number(median.toFixed(4)), p95Ms: Number(p95.toFixed(4)), iterations };
}

describe('coste de interacción (probe T13)', () => {
  it('mide resolución de candidato + vista previa y verifica cotas estructurales', () => {
    const camera = obliqueCamera();
    const sizes: { name: string; count: number; iterations: number }[] = [
      { name: 'curva_2', count: 2, iterations: 300 },
      { name: 'curva_1000', count: 1000, iterations: 100 },
      { name: 'curva_100000', count: 100000, iterations: 7 },
    ];
    const scenarios: Record<string, { medianMs: number; p95Ms: number; iterations: number }> = {};
    for (const size of sizes) {
      const candidates = denseCandidates('curva-a', size.count, context);
      const input = inputFor(candidates, camera, { pointer: { x: 400, y: 300 } });
      scenarios[`pick_${size.name}`] = bench(() => {
        pickCurveCandidate(input);
      }, size.iterations);
    }

    const previewPoints: MiningPoint3D[] = [];
    for (let i = 0; i < 2000; i += 1) previewPoints.push([i, 0, 0]);
    const previewSnapshot: CurveGeometrySnapshot = {
      context,
      curves: new Map([['curva-a', { id: 'curva-a', points: previewPoints }]]),
    };
    const start = createCurveAnchor({ context, curveId: 'curva-a', points: previewPoints, segmentIndex: 0, t: 0 });
    const end = createCurveAnchor({ context, curveId: 'curva-a', points: previewPoints, segmentIndex: 1000, t: 0.5 });
    if (!start || !end) throw new Error('anclas no generables');
    const confirmed = { ...createCurveSelectionState(context), curveId: 'curva-a', start, end, rejection: null };
    const onlyStart = { ...createCurveSelectionState(context), curveId: 'curva-a', start, end: null, rejection: null };
    scenarios.preview_range = bench(() => {
      buildCurveSelectionVisuals({ snapshot: previewSnapshot, selection: confirmed, center: [0, 0, 0] });
    }, 200);
    scenarios.preview_startOnly = bench(() => {
      buildCurveSelectionVisuals({ snapshot: previewSnapshot, selection: onlyStart, center: [0, 0, 0] });
    }, 300);

    const activeOnly = denseCandidates('curva-a', 1000, context);
    const withUnrelated = [...denseCandidates('curva-a', 1000, context)];
    for (let k = 0; k < 20; k += 1) {
      withUnrelated.push(...denseCandidates(`curva-x-${k}`, 1000, context));
    }
    const activeInput = inputFor(activeOnly, camera, { pointer: { x: 400, y: 300 } });
    const mixedInput = inputFor(withUnrelated, camera, { pointer: { x: 400, y: 300 } });
    scenarios.pick_activeOnly_1000 = bench(() => {
      pickCurveCandidate(activeInput);
    }, 60);
    scenarios.pick_activePlus21000_ajenas = bench(() => {
      pickCurveCandidate(mixedInput);
    }, 20);

    const rangeLength = buildCurveSelectionVisuals({ snapshot: previewSnapshot, selection: confirmed, center: [0, 0, 0] })
      .range?.length ?? 0;
    expect(rangeLength).toBeGreaterThan(0);
    const structuralWinner = pickCurveCandidate(mixedInput);
    expect(structuralWinner?.curveId).toBe('curva-a');
    const again = buildCurveSelectionVisuals({ snapshot: previewSnapshot, selection: confirmed, center: [0, 0, 0] });
    expect(again.rangePositions?.length).toBe(rangeLength * 3);
    expect(buildCurveSelectionVisuals({ snapshot: previewSnapshot, selection: onlyStart, center: [0, 0, 0] }).rangePositions).toBeNull();

    console.log(`__T13_COST__ ${JSON.stringify({
      fixture: {
        viewport,
        camera: { position: [6, 5, 9], fov: 50, near: 0.5, far: 500 },
        previewRangeVertices: rangeLength,
        pickSizes: sizes.map((s) => ({ name: s.name, candidates: s.count })),
        unrelatedCurves: 20,
        unrelatedCandidates: 20000,
      },
      scenarios,
    })}`);
  });
});
