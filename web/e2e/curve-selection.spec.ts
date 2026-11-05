import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { installFontFixtures } from './fixtures/fontFixtures.ts';

const EVIDENCE_DIR = process.env.T12_EVIDENCE_DIR
  ?? path.resolve(process.cwd(), '..', 'data', 'qa-curve-selection', 't12-evidence');

const E_MIN = 700000;
const E_MAX = 700100;
const N_MIN = 7200000;
const N_MAX = 7200010;
const Z_LEVEL = 100;
const CENTER_E = (E_MIN + E_MAX) / 2;
const CENTER_N = (N_MIN + N_MAX) / 2;
const CENTER_Z = Z_LEVEL;

const CURVE_A = [[E_MIN, N_MIN, Z_LEVEL], [E_MAX, N_MIN, Z_LEVEL]];
const CURVE_B = [[E_MIN, N_MIN + 1, Z_LEVEL], [E_MAX, N_MIN + 1, Z_LEVEL]];
const CURVE_A_ID = '0-0';

const MESH_IDS = { design: 'qa-curve-design', topo: 'qa-curve-topo' } as const;

const CLICK_TARGET_EW = { first: (E_MIN + E_MAX) / 2, secondE: E_MIN + 20, thirdE: E_MIN + 80 } as const;

const canvasSelector = '[data-slot="mesh-3d-viewer"] canvas';

type AnchorSnapshot = {
  curveId: string;
  segmentIndex: number;
  t: number;
  chainage: number;
  position: number[];
};

type SessionSnapshot = {
  sessionUrl: string;
  designMeshId: string | null;
  topoMeshId: string | null;
  mapClickHandlerPresent: boolean;
  curveSelection: {
    context: { designMeshId: string; geometryKey: string } | null;
    curveId: string | null;
    start: AnchorSnapshot | null;
    end: AnchorSnapshot | null;
    rejection: string | null;
  };
};

type CameraPoseSnapshot = {
  cameraPosition: number[];
  cameraQuaternion: number[];
  controlsTarget: number[] | null;
};

type CssPoint = { x: number; y: number };

const mockVertices = (() => {
  const corners = [
    [E_MIN, N_MIN, Z_LEVEL],
    [E_MAX, N_MIN, Z_LEVEL],
    [E_MAX, N_MAX, Z_LEVEL],
    [E_MIN, N_MAX, Z_LEVEL],
  ];
  return {
    x: corners.map((p) => p[0]),
    y: corners.map((p) => p[1]),
    z: corners.map((p) => p[2]),
    faces: [[0, 1, 2], [0, 2, 3]],
  };
})();

const mockBreaklines = {
  bounds: { xmin: E_MIN, ymin: N_MIN, xmax: E_MAX, ymax: N_MAX },
  elevation_min: Z_LEVEL,
  elevation_max: Z_LEVEL,
  interval: 1,
  lines: [
    { elevation: Z_LEVEL, type: 'crest', segments: [CURVE_A.map((p) => [p[0], p[1]])] },
    { elevation: Z_LEVEL, type: 'toe', segments: [CURVE_B.map((p) => [p[0], p[1]])] },
  ],
};

function mockMeshInfo(meshId: string) {
  return {
    id: meshId,
    type: meshId === MESH_IDS.design ? 'design' : 'topo',
    filename: `${meshId}.stl`,
    n_vertices: 4,
    n_faces: 2,
    bounds: mockBreaklines.bounds,
    uploaded_at: '2026-10-17T12:00:00Z',
    import_report: null,
  };
}

function miningToScene(p: number[]): number[] {
  return [p[0] - CENTER_E, p[2] - CENTER_Z, -(p[1] - CENTER_N)];
}

function selectionEquals(
  a: SessionSnapshot['curveSelection'],
  b: SessionSnapshot['curveSelection'],
): boolean {
  return a.curveId === b.curveId
    && a.rejection === b.rejection
    && JSON.stringify(a.start) === JSON.stringify(b.start)
    && JSON.stringify(a.end) === JSON.stringify(b.end);
}

function pointToSegmentDistancePx(point: CssPoint, a: CssPoint, b: CssPoint): number {
  const abx = b.x - a.x;
  const aby = b.y - a.y;
  const lenSq = abx * abx + aby * aby;
  const t = lenSq === 0 ? 0 : Math.max(0, Math.min(1, ((point.x - a.x) * abx + (point.y - a.y) * aby) / lenSq));
  return Math.hypot(point.x - (a.x + t * abx), point.y - (a.y + t * aby));
}

const readCurveSelectionInPage = async (args: { sessionUrlFallback: string }) => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  const hits = entries.filter((name) => /src\/stores\/session\.ts/.test(name));
  const sessionUrl = hits.length > 0 ? hits[hits.length - 1] : args.sessionUrlFallback;
  const mod = await import(sessionUrl);
  const state = mod.useSession.getState();
  const selection = state.curveSelection;
  const cloneAnchor = (anchor: { curveId: string; segmentIndex: number; t: number; chainage: number; position: number[] } | null) => (anchor === null
    ? null
    : { curveId: anchor.curveId, segmentIndex: anchor.segmentIndex, t: anchor.t, chainage: anchor.chainage, position: [...anchor.position] });
  return {
    sessionUrl,
    designMeshId: state.designMeshId,
    topoMeshId: state.topoMeshId,
    mapClickHandlerPresent: state.mapClickHandler !== null,
    curveSelection: {
      context: selection.context ? { ...selection.context } : null,
      curveId: selection.curveId,
      start: cloneAnchor(selection.start),
      end: cloneAnchor(selection.end),
      rejection: selection.rejection,
    },
  };
};

async function readSelection(page: Page): Promise<SessionSnapshot> {
  return page.evaluate(readCurveSelectionInPage, { sessionUrlFallback: '/conciliacion-geo-v02/src/stores/session.ts' }) as Promise<SessionSnapshot>;
}

async function waitForSelection(
  page: Page,
  predicate: (snapshot: SessionSnapshot) => boolean,
  label: string,
  timeoutMs = 15000,
): Promise<SessionSnapshot> {
  const deadline = Date.now() + timeoutMs;
  let last: SessionSnapshot | null = null;
  for (;;) {
    last = await readSelection(page);
    if (predicate(last)) return last;
    if (Date.now() > deadline) {
      throw new Error(`${label}: selection state not reached: ${JSON.stringify(last.curveSelection)}`);
    }
    await page.waitForTimeout(120);
  }
}

const setupMeshesInPage = async (ids: { design: string; topo: string; sessionUrlFallback: string }) => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  const hits = entries.filter((name) => /src\/stores\/session\.ts/.test(name));
  const sessionUrl = hits.length > 0 ? hits[hits.length - 1] : ids.sessionUrlFallback;
  const mod = await import(sessionUrl);
  const api = mod.useSession.getState();
  const before = { designMeshId: api.designMeshId, topoMeshId: api.topoMeshId, currentStep: api.currentStep, view: api.activeWorkspaceView };
  api.setDesignMeshId(ids.design);
  api.setTopoMeshId(ids.topo);
  const after = mod.useSession.getState();
  return {
    sessionUrl,
    before,
    after: { designMeshId: after.designMeshId, topoMeshId: after.topoMeshId, currentStep: after.currentStep, view: after.activeWorkspaceView },
  };
};

const prepareCameraInPage = async (canvasSel: string) => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  const fiberHits = entries.filter((name) => /deps\/@react-three_fiber\.js/.test(name));
  let fiberUrl = fiberHits.length > 0 ? fiberHits[fiberHits.length - 1] : null;
  let fiberHashSource = 'performance';
  if (!fiberUrl) {
    const meta = await (await fetch('/conciliacion-geo-v02/node_modules/.vite/deps/_metadata.json')).json();
    fiberUrl = `/conciliacion-geo-v02/node_modules/.vite/deps/@react-three_fiber.js?v=${meta.browserHash}`;
    fiberHashSource = 'metadata';
  }
  const fiber = await import(fiberUrl as string);
  const canvas = document.querySelector(canvasSel) as HTMLCanvasElement | null;
  if (canvas === null) throw new Error('r3f canvas element not found');
  const root = fiber._roots.get(canvas);
  if (!root || typeof root.store?.getState !== 'function') {
    const digest = Array.from(fiber._roots.keys() as Set<Element>).map((element) => `${element.tagName}.${element.className}`).join('|');
    throw new Error(`r3f root not found for canvas; digest keys=${digest}`);
  }
  const state = root.store.getState();
  if (!state.camera || !state.scene) throw new Error('r3f store shape unexpected');
  state.camera.position.set(0, 200, 120);
  state.camera.up.set(0, 1, 0);
  state.camera.lookAt(0, 0, 0);
  const controls = state.controls ?? null;
  let controlsSynced = false;
  if (controls && typeof controls.target?.set === 'function') {
    controls.target.set(0, 0, 0);
    controls.update();
    controlsSynced = true;
  }
  return {
    fiberUrl,
    fiberHashSource,
    controlsSynced,
    cameraPosition: state.camera.position.toArray(),
    cameraFar: state.camera.far,
    sizes: { width: state.size.width, height: state.size.height, dpr: state.viewport.dpr },
  };
};

const readCameraPoseInPage = async (): Promise<CameraPoseSnapshot> => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  const fiberHits = entries.filter((name) => /deps\/@react-three_fiber\.js/.test(name));
  const fiberUrl = fiberHits.length > 0 ? fiberHits[fiberHits.length - 1] : null;
  if (!fiberUrl) throw new Error('fiber module url not in performance entries');
  const fiber = await import(fiberUrl);
  const canvas = document.querySelector('[data-slot="mesh-3d-viewer"] canvas') as HTMLCanvasElement | null;
  if (canvas === null) throw new Error('canvas missing');
  const root = fiber._roots.get(canvas);
  if (!root || typeof root.store?.getState !== 'function') throw new Error('r3f root not found for canvas');
  const state = root.store.getState();
  const controls = state.controls ?? null;
  return {
    cameraPosition: state.camera.position.toArray(),
    cameraQuaternion: state.camera.quaternion.toArray(),
    controlsTarget: controls && typeof controls.target?.toArray === 'function' ? controls.target.toArray() : null,
  };
};

type DprSnapshot = {
  windowDpr: number;
  glPixelRatio: number;
  viewportDpr: number;
  canvasCssWidth: number;
  canvasCssHeight: number;
  canvasBufferWidth: number;
  canvasBufferHeight: number;
};

const readDprInPage = async () => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  const fiberHits = entries.filter((name) => /deps\/@react-three_fiber\.js/.test(name));
  const fiberUrl = fiberHits.length > 0 ? fiberHits[fiberHits.length - 1] : null;
  if (!fiberUrl) throw new Error('fiber module url not in performance entries');
  const fiber = await import(fiberUrl);
  const canvas = document.querySelector('[data-slot="mesh-3d-viewer"] canvas') as HTMLCanvasElement | null;
  if (canvas === null) throw new Error('canvas missing');
  const root = fiber._roots.get(canvas);
  if (!root || typeof root.store?.getState !== 'function') throw new Error('r3f root not found for canvas');
  const state = root.store.getState();
  const rect = canvas.getBoundingClientRect();
  return {
    windowDpr: window.devicePixelRatio,
    glPixelRatio: state.gl.getPixelRatio(),
    viewportDpr: state.viewport.dpr,
    canvasCssWidth: rect.width,
    canvasCssHeight: rect.height,
    canvasBufferWidth: canvas.width,
    canvasBufferHeight: canvas.height,
  };
};

const bCanvasProbeInPage = async (args: { x: number; y: number }) => {
  const allCanvases = Array.from(document.querySelectorAll('canvas'));
  const viewer = document.querySelector('[data-slot="mesh-3d-viewer"]');
  const canvas = viewer?.querySelector('canvas') as HTMLCanvasElement | null;
  const start = document.elementFromPoint(args.x, args.y);
  const rectOf = (element: Element | null) => {
    if (element === null) return null;
    const r = element.getBoundingClientRect();
    return { left: r.left, top: r.top, width: r.width, height: r.height };
  };
  return {
    canvasTotal: allCanvases.length,
    hitIsNull: start === null,
    hit: start === null
      ? null
      : {
          tag: start.tagName,
          width: (start as HTMLCanvasElement).width,
          height: (start as HTMLCanvasElement).height,
          className: typeof (start as HTMLElement).className === 'string' ? (start as HTMLElement).className : '',
          dataSlot: (start as HTMLElement).dataset?.slot ?? null,
          parentChain: (() => {
            const chain: string[] = [];
            let node: Element | null = (start as HTMLElement).parentElement;
            while (node !== null && chain.length < 6) {
              chain.push(`${node.tagName.toLowerCase()}${(node as HTMLElement).dataset?.slot ? `[slot=${(node as HTMLElement).dataset.slot}]` : ''}${node.id ? `#${node.id}` : ''}`);
              node = node.parentElement;
            }
            return chain;
          })(),
          rect: rectOf(start),
          pointerEvents: getComputedStyle(start).pointerEvents,
          docIndex: allCanvases.indexOf(start as HTMLCanvasElement),
          isInsideViewer: viewer !== null && viewer.contains(start),
        },
    queryCanvas: canvas === null
      ? null
      : {
          width: canvas.width,
          height: canvas.height,
          rect: rectOf(canvas),
          docIndex: allCanvases.indexOf(canvas),
          pointerEvents: getComputedStyle(canvas).pointerEvents,
        },
    viewerFound: viewer !== null,
    sameElement: start === canvas,
    sameRect: rectOf(start) !== null && JSON.stringify(rectOf(start)) === JSON.stringify(rectOf(canvas)),
  };
};

const projectPointsInPage = async (args: { scenePoints: number[][] }) => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  const fiberHits = entries.filter((name) => /deps\/@react-three_fiber\.js/.test(name));
  const fiberUrl = fiberHits.length > 0 ? fiberHits[fiberHits.length - 1] : null;
  if (!fiberUrl) throw new Error('fiber module url not in performance entries');
  const fiber = await import(fiberUrl);
  const canvas = document.querySelector('[data-slot="mesh-3d-viewer"] canvas') as HTMLCanvasElement | null;
  if (canvas === null) throw new Error('canvas missing');
  const state = fiber._roots.get(canvas).store.getState();
  const camera = state.camera;
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix();
  camera.matrixWorldInverse.copy(camera.matrixWorld).invert();
  const rect = canvas.getBoundingClientRect();
  const proj = camera.projectionMatrix.elements;
  const project = (w: number[]) => {
    const q = camera.quaternion;
    const camPos = camera.position;
    const rx = 1 - 2 * (q.y * q.y + q.z * q.z); const ry = 2 * (q.x * q.y + q.z * q.w); const rz = 2 * (q.x * q.z - q.y * q.w);
    const ux = 2 * (q.x * q.y - q.z * q.w); const uy = 1 - 2 * (q.x * q.x + q.z * q.z); const uz = 2 * (q.y * q.z + q.x * q.w);
    const bx = 2 * (q.x * q.z + q.y * q.w); const by = 2 * (q.y * q.z - q.x * q.w); const bz = 1 - 2 * (q.x * q.x + q.y * q.y);
    const relX = w[0] - camPos.x; const relY = w[1] - camPos.y; const relZ = w[2] - camPos.z;
    const xv = rx * relX + ry * relY + rz * relZ;
    const yv = ux * relX + uy * relY + uz * relZ;
    const depth = -(bx * relX + by * relY + bz * relZ);
    const ndcX = (proj[0] * xv) / depth;
    const ndcY = (proj[5] * yv) / depth;
    return {
      x: rect.left + (ndcX * 0.5 + 0.5) * rect.width,
      y: rect.top + (0.5 - ndcY * 0.5) * rect.height,
      depth,
    };
  };
  return {
    fiberUrl,
    rect: { left: rect.left, top: rect.top, width: rect.width, height: rect.height },
    viewport: { width: state.size.width, height: state.size.height, dpr: state.viewport.dpr },
    cameraPosition: camera.position.toArray(),
    projected: args.scenePoints.map((w) => project(w)),
  };
};

const sceneMarkersInPage = async (args: { centerE: number; centerN: number; centerZ: number }) => {
  const entries = performance.getEntriesByType('resource').map((entry) => entry.name);
  const fiberHits = entries.filter((name) => /deps\/@react-three_fiber\.js/.test(name));
  const fiberUrl = fiberHits.length > 0 ? fiberHits[fiberHits.length - 1] : null;
  if (!fiberUrl) throw new Error('fiber module url not in performance entries');
  const fiber = await import(fiberUrl);
  const canvas = document.querySelector('[data-slot="mesh-3d-viewer"] canvas') as HTMLCanvasElement | null;
  if (canvas === null) throw new Error('canvas missing');
  const state = fiber._roots.get(canvas).store.getState();
  const camera = state.camera;
  camera.updateMatrixWorld();
  camera.updateProjectionMatrix();
  camera.matrixWorldInverse.copy(camera.matrixWorld).invert();
  const rect = canvas.getBoundingClientRect();
  const proj = camera.projectionMatrix.elements;
  const applyMatrix = (m: number[], p: number[]) => [
    m[0] * p[0] + m[4] * p[1] + m[8] * p[2] + m[12],
    m[1] * p[0] + m[5] * p[1] + m[9] * p[2] + m[13],
    m[2] * p[0] + m[6] * p[1] + m[10] * p[2] + m[14],
  ];
  const project = (w: number[]) => {
    const q = camera.quaternion;
    const camPos = camera.position;
    const rx = 1 - 2 * (q.y * q.y + q.z * q.z); const ry = 2 * (q.x * q.y + q.z * q.w); const rz = 2 * (q.x * q.z - q.y * q.w);
    const ux = 2 * (q.x * q.y - q.z * q.w); const uy = 1 - 2 * (q.x * q.x + q.z * q.z); const uz = 2 * (q.y * q.z + q.x * q.w);
    const bx = 2 * (q.x * q.z + q.y * q.w); const by = 2 * (q.y * q.z - q.x * q.w); const bz = 1 - 2 * (q.x * q.x + q.y * q.y);
    const relX = w[0] - camPos.x; const relY = w[1] - camPos.y; const relZ = w[2] - camPos.z;
    const xv = rx * relX + ry * relY + rz * relZ;
    const yv = ux * relX + uy * relY + uz * relZ;
    const depth = -(bx * relX + by * relY + bz * relZ);
    const ndcX = (proj[0] * xv) / depth;
    const ndcY = (proj[5] * yv) / depth;
    return {
      x: rect.left + (ndcX * 0.5 + 0.5) * rect.width,
      y: rect.top + (0.5 - ndcY * 0.5) * rect.height,
    };
  };
  const objects = ['curve-selection-start', 'curve-selection-end', 'curve-selection-range', 'curve-selection-preview'];
  const result: Record<string, null | {
    role: string | null;
    visible: boolean;
    count: number | null;
    pageCoords: number[][];
    miningPoints: number[][];
  }> = {};
  for (const name of objects) {
    const obj = state.scene.getObjectByName(name);
    if (!obj) {
      result[name] = null;
      continue;
    }
    const positions = (obj as unknown as { geometry?: { attributes?: { position?: { count: number; getX: (i: number) => number; getY: (i: number) => number; getZ: (i: number) => number } } } }).geometry?.attributes?.position;
    obj.updateMatrixWorld(true);
    const mw = obj.matrixWorld.elements as number[];
    const pageCoords: number[][] = [];
    const miningPoints: number[][] = [];
    if (positions) {
      for (let i = 0; i < positions.count; i += 1) {
        const local = [positions.getX(i), positions.getY(i), positions.getZ(i)];
        const world = applyMatrix(mw, local);
        const page = project(world);
        pageCoords.push([page.x, page.y]);
        miningPoints.push([world[0] + args.centerE, args.centerN - world[2], world[1] + args.centerZ]);
      }
    }
    result[name] = {
      role: (obj.userData?.role ?? null) as string | null,
      visible: obj.visible,
      count: positions ? positions.count : null,
      pageCoords,
      miningPoints,
    };
  }
  return result;
};

type MarkerSnapshot = Record<string, { role: string | null; visible: boolean; count: number | null; pageCoords: number[][]; miningPoints: number[][] } | null>;

async function waitForPreviewMarkers(
  page: Page,
  mode: 'visible' | 'hidden',
  timeoutMs = 5000,
): Promise<MarkerSnapshot> {
  const deadline = Date.now() + timeoutMs;
  let last: MarkerSnapshot | null = null;
  for (;;) {
    last = await page.evaluate(sceneMarkersInPage, { centerE: CENTER_E, centerN: CENTER_N, centerZ: CENTER_Z }) as MarkerSnapshot;
    const preview = last['curve-selection-preview'];
    const satisfied = mode === 'visible'
      ? preview !== null && preview.visible && preview.count === 1
      : preview === null || !preview.visible;
    if (satisfied) return last;
    if (Date.now() > deadline) throw new Error(`preview not ${mode}: ${JSON.stringify(preview)}`);
    await page.waitForTimeout(100);
  }
}

async function bootCurveSelectionFixture(page: Page) {
  await installFontFixtures(page);
  await page.route('**/api/v1/meshes/**', async (route) => {
    if (route.request().method() !== 'GET') {
      return route.continue();
    }
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/vertices') || url.pathname.endsWith('/vertices/roi')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockVertices) });
    }
    if (url.pathname.endsWith('/breaklines')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockBreaklines) });
    }
    if (url.pathname.endsWith('/info')) {
      const meshId = decodeURIComponent(url.pathname.split('/').slice(-2, -1)[0] ?? '');
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(mockMeshInfo(meshId)) });
    }
    return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({}) });
  });

  await page.goto('/conciliacion-geo-v02/');
  await expect(page.locator('[data-slot="mesh-3d-viewer"]')).toBeVisible({ timeout: 30000 });

  const bootSnapshot = await readSelection(page);
  expect(bootSnapshot.designMeshId).toBeNull();

  const meshSetup = await page.evaluate(setupMeshesInPage, { design: MESH_IDS.design, topo: MESH_IDS.topo, sessionUrlFallback: '/conciliacion-geo-v02/src/stores/session.ts' });
  expect(meshSetup.after.designMeshId).toBe(MESH_IDS.design);
  expect(meshSetup.after.topoMeshId).toBe(MESH_IDS.topo);

  await expect(page.locator(canvasSelector)).toBeVisible({ timeout: 30000 });

  const sectionsStep = page.locator('#workflow-step-sections');
  if (await sectionsStep.getAttribute('aria-expanded') !== 'true') await sectionsStep.click();
  await expect(page.locator('[data-slot="section-curve-form"]')).toBeVisible({ timeout: 15000 });

  const firstSnapshot = await waitForSelection(page, (snapshot) => snapshot.curveSelection.context !== null, 'context ready');

  const topoCheckbox = page.locator('[data-slot="mesh-3d-viewer"]').locator('input[type="checkbox"]').first();
  await expect(topoCheckbox).toBeChecked();
  await topoCheckbox.click();
  await expect(topoCheckbox).not.toBeChecked();

  await page.evaluate(() => new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  }));

  const cameraPrep = await page.evaluate(prepareCameraInPage, canvasSelector);
  await page.evaluate(() => new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  }));

  return { bootSnapshot, meshSetup, firstSnapshot, cameraPrep };
}

test('T12a continuous curve selection picks, renders markers, generates real sections', async ({ page, request }, testInfo) => {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  const t0 = Date.now();
  const consoleErrors: Array<{ type: string; text: string; at: string }> = [];
  const pageErrors: string[] = [];
  const apiResponses: Array<{ url: string; status: number; method: string }> = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push({ type: message.type(), text: message.text(), at: new Date().toISOString() });
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  page.on('response', (response) => {
    if (response.url().includes('/api/v1/')) {
      apiResponses.push({ url: response.url(), status: response.status(), method: response.request().method() });
    }
  });

  const fixture = await bootCurveSelectionFixture(page);
  const bootSnapshot = fixture.bootSnapshot;
  const meshSetup = fixture.meshSetup;
  const firstSnapshot = fixture.firstSnapshot;
  const cameraPrep = fixture.cameraPrep;

  const click1Scene = miningToScene([CLICK_TARGET_EW.first, N_MIN, Z_LEVEL]);
  const click2Scene = miningToScene([CLICK_TARGET_EW.secondE, N_MIN, Z_LEVEL]);
  const click3Scene = miningToScene([CLICK_TARGET_EW.thirdE, N_MIN, Z_LEVEL]);
  const projected = await page.evaluate(projectPointsInPage, { scenePoints: [click1Scene, click2Scene, click3Scene] });

  const click1Coords = projected.projected[0];
  const click2Coords = projected.projected[1];
  const click3Coords = projected.projected[2];

  await page.mouse.click(click1Coords.x, click1Coords.y);
  const afterClick1 = await waitForSelection(page, (snapshot) => snapshot.curveSelection.curveId === CURVE_A_ID && snapshot.curveSelection.start === null, 'click1 curve chosen');
  expect(afterClick1.curveSelection.rejection).toBeNull();
  expect(afterClick1.curveSelection.end).toBeNull();
  await expect(page.locator('[data-slot="section-curve-form"] span[title="0-0"]')).toBeVisible();

  await page.mouse.click(click2Coords.x, click2Coords.y);
  const afterClick2 = await waitForSelection(page, (snapshot) => snapshot.curveSelection.start !== null && snapshot.curveSelection.curveId === CURVE_A_ID, 'click2 start anchor');
  expect(afterClick2.curveSelection.rejection).toBeNull();
  expect(afterClick2.curveSelection.end).toBeNull();
  const startAnchor = afterClick2.curveSelection.start;
  if (startAnchor === null) throw new Error('start anchor expected after click2');
  await expect(page.locator('[data-slot="curve-start-summary"]')).toContainText(startAnchor.position[0].toFixed(3));
  await expect(page.locator('[data-slot="curve-start-summary"]')).toContainText(startAnchor.position[1].toFixed(3));

  await page.mouse.click(click3Coords.x, click3Coords.y);
  const afterClick3 = await waitForSelection(page, (snapshot) => snapshot.curveSelection.end !== null, 'click3 end anchor');
  expect(afterClick3.curveSelection.rejection).toBeNull();
  const endAnchor = afterClick3.curveSelection.end;
  if (endAnchor === null) throw new Error('end anchor expected after click3');
  await expect(page.locator('[data-slot="curve-end-summary"]')).toContainText(endAnchor.position[0].toFixed(3));
  await expect(page.locator('[data-slot="curve-end-summary"]')).toContainText(endAnchor.position[1].toFixed(3));

  expect(afterClick3.curveSelection.curveId).toBe(CURVE_A_ID);
  expect(startAnchor.segmentIndex).toBe(0);
  expect(endAnchor.segmentIndex).toBe(0);
  expect(startAnchor.chainage).toBeLessThan(endAnchor.chainage - 40);
  expect(startAnchor.t).toBeGreaterThan(0);
  expect(startAnchor.t).toBeLessThan(1);
  expect(endAnchor.t).toBeGreaterThan(0);
  expect(endAnchor.t).toBeLessThan(1);
  expect(startAnchor.position[0]).toBeGreaterThan(E_MIN);
  expect(startAnchor.position[0]).toBeLessThan(E_MAX);
  expect(endAnchor.position[0]).toBeGreaterThan(E_MIN);
  expect(endAnchor.position[0]).toBeLessThan(E_MAX);
  expect(startAnchor.position[1]).toBeCloseTo(N_MIN, 6);
  expect(endAnchor.position[1]).toBeCloseTo(N_MIN, 6);

  const markers = await page.evaluate(sceneMarkersInPage, { centerE: CENTER_E, centerN: CENTER_N, centerZ: CENTER_Z }) as MarkerSnapshot;
  const startMarker = markers['curve-selection-start'];
  const endMarker = markers['curve-selection-end'];
  const rangeMarker = markers['curve-selection-range'];
  if (startMarker === null || endMarker === null || rangeMarker === null) {
    throw new Error(`marker objects missing: ${JSON.stringify(Object.fromEntries(Object.entries(markers).map(([key, value]) => [key, value !== null])))}`);
  }
  expect(startMarker.count).toBe(1);
  expect(endMarker.count).toBe(1);
  expect(startMarker.role).toBe('start');
  expect(endMarker.role).toBe('end');
  expect(startMarker.visible).toBe(true);
  expect(endMarker.visible).toBe(true);

  const startMarkerError = Math.hypot(startMarker.pageCoords[0][0] - click2Coords.x, startMarker.pageCoords[0][1] - click2Coords.y);
  const endMarkerError = Math.hypot(endMarker.pageCoords[0][0] - click3Coords.x, endMarker.pageCoords[0][1] - click3Coords.y);
  expect(startMarkerError).toBeLessThanOrEqual(1.0);
  expect(endMarkerError).toBeLessThanOrEqual(1.0);

  expect(rangeMarker.count).toBe(2);
  expect(rangeMarker.visible).toBe(true);
  expect(rangeMarker.role).toBe('range');
  const rangeStart = rangeMarker.miningPoints[0];
  const rangeEnd = rangeMarker.miningPoints[1];
  expect(Math.abs(rangeStart[0] - startAnchor.position[0])).toBeLessThan(1e-4);
  expect(Math.abs(rangeStart[1] - startAnchor.position[1])).toBeLessThan(1e-4);
  expect(Math.abs(rangeEnd[0] - endAnchor.position[0])).toBeLessThan(1e-4);
  expect(Math.abs(rangeEnd[1] - endAnchor.position[1])).toBeLessThan(1e-4);
  expect(Math.abs(rangeStart[0] - E_MIN)).toBeGreaterThan(5);
  expect(Math.abs(rangeEnd[0] - E_MAX)).toBeGreaterThan(5);

  await expect(page.locator('[data-slot="curve-range-length"]')).toBeVisible();

  const preGenerationShot = path.join(EVIDENCE_DIR, `t12a-${testInfo.project.name}-pre-generation.png`);
  await page.screenshot({ path: preGenerationShot, fullPage: true });

  const generateButton = page.locator('[data-slot="section-curve-form"]').getByRole('button', { name: 'Generar perfiles' });
  await expect(generateButton).toBeEnabled();

  const [postResponse] = await Promise.all([
    page.waitForResponse((response) => response.request().method() === 'POST' && response.url().includes('/api/v1/sections/curve'), { timeout: 30000 }),
    generateButton.click(),
  ]);
  expect(postResponse.status()).toBe(200);
  const postRequest = postResponse.request();
  const postHeaders = postRequest.headers();
  const postBody = postRequest.postDataJSON();
  const postJson = await postResponse.json();
  const postSessionId = postHeaders['x-session-id'] ?? postResponse.headers()['x-session-id'] ?? null;
  expect(postSessionId).not.toBeNull();

  expect(Array.isArray(postBody.points)).toBe(true);
  expect(postBody.points).toHaveLength(2);
  for (const point of postBody.points) {
    expect(Array.isArray(point)).toBe(true);
    expect(point).toHaveLength(2);
  }
  expect(postBody.points[0]).toEqual([startAnchor.position[0], startAnchor.position[1]]);
  expect(postBody.points[1]).toEqual([endAnchor.position[0], endAnchor.position[1]]);
  expect(postBody.spacing).toBe(10);
  expect(postBody.length).toBe(200);
  expect(postBody.length_up).toBe(100);
  expect(postBody.length_down).toBe(100);
  expect(postBody.sector).toBe('');

  const postSelection = await waitForSelection(page, (snapshot) => snapshot.curveSelection.start === null && snapshot.curveSelection.end === null, 'selection reset after generate');
  expect(postSelection.curveSelection.rejection).toBeNull();

  const readbackResponse = await request.get('http://127.0.0.1:8000/api/v1/sections', {
    headers: { 'X-Session-ID': postSessionId as string },
  });
  expect(readbackResponse.ok()).toBe(true);
  const readback = await readbackResponse.json();
  expect(Array.isArray(readback)).toBe(true);
  expect(readback.length).toBeGreaterThan(0);

  const spanStart = postBody.points[0];
  const spanEnd = postBody.points[1];
  const spanDir = [spanEnd[0] - spanStart[0], spanEnd[1] - spanStart[1]];
  const spanSq = spanDir[0] * spanDir[0] + spanDir[1] * spanDir[1];
  const readbackChecks = (readback as Array<{ name: string; origin: number[]; azimuth: number; length: number }>).map((section, index) => {
    const rel = [section.origin[0] - spanStart[0], section.origin[1] - spanStart[1]];
    const t = (rel[0] * spanDir[0] + rel[1] * spanDir[1]) / spanSq;
    const projection = [spanStart[0] + t * spanDir[0], spanStart[1] + t * spanDir[1]];
    const distance = Math.hypot(projection[0] - section.origin[0], projection[1] - section.origin[1]);
    return { name: section.name, origin: section.origin, azimuth: section.azimuth, length: section.length, t, distanceToSpanLine: distance, index };
  });
  expect(readbackChecks.length).toBeGreaterThan(0);
  for (const check of readbackChecks) {
    expect(check.t).toBeGreaterThan(0);
    expect(check.t).toBeLessThan(1);
    expect(check.distanceToSpanLine).toBeLessThan(1e-6);
  }
  expect(readbackChecks[readbackChecks.length - 1].t).toBeLessThan(1);
  expect(readbackChecks[0].t).toBeGreaterThan(0);

  const postSections = (postJson as { sections?: unknown }).sections;
  expect(Array.isArray(postSections)).toBe(true);
  expect(postSections).toHaveLength(6);
  expect(readback).toEqual(postSections);

  const postGenerationShot = path.join(EVIDENCE_DIR, `t12a-${testInfo.project.name}-post-generation.png`);
  await page.screenshot({ path: postGenerationShot, fullPage: true });

  const evidence = {
    fixtureScope: {
      mocked: 'browser GET /api/v1/meshes/** (info, vertices, breaklines) served deterministic synthetic geometry in the browser only; non-GET mesh requests are not fulfilled and continue to the network; mesh upload/extraction is not exercised by design; every POST/GET /api/v1/sections** request hit the real backend at 127.0.0.1:8000',
      fonts: 'external font network isolated via installFontFixtures (web/e2e/fixtures/fontFixtures.ts): GET https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Outfit:wght@400;500;600;700&display=swap and the two latin-subset fonts.gstatic.com woff2 files are fulfilled from pinned licensed local fixtures (web/e2e/fixtures/fonts, SIL OFL 1.1, sources.json) in addition to the mocked GET /api/v1/meshes/**; unmatched requests continue to the network',
      programmaticSetup: 'design/topo mesh ids set via imported session store module (URL resolved from performance entries) and R3F camera position (0,200,120) set programmatically; sections accordion, curves tab, topo-layer checkbox off, the three canvas clicks and the Generate button click were real user-level UI actions',
      curves: { '0-0': CURVE_A, '1-0': CURVE_B },
    },
    moduleUrls: { session: bootSnapshot.sessionUrl, fiber: cameraPrep.fiberUrl, fiberHashSource: cameraPrep.fiberHashSource },
    sessionSetup: meshSetup,
    selectionContext: firstSnapshot.curveSelection.context,
    cameraPrep,
    clickProjections: projected,
    clicks: [
      { label: 'click1', mining: [CLICK_TARGET_EW.first, N_MIN, Z_LEVEL], scene: click1Scene, pageCoords: click1Coords, acceptedCurveId: afterClick1.curveSelection.curveId },
      { label: 'click2', mining: [CLICK_TARGET_EW.secondE, N_MIN, Z_LEVEL], scene: click2Scene, pageCoords: click2Coords, acceptedStartAnchor: startAnchor },
      { label: 'click3', mining: [CLICK_TARGET_EW.thirdE, N_MIN, Z_LEVEL], scene: click3Scene, pageCoords: click3Coords, acceptedEndAnchor: endAnchor },
    ],
    markerMetrics: {
      startMarkerPixelError: startMarkerError,
      endMarkerPixelError: endMarkerError,
      startMarkerMining: startMarker.miningPoints,
      endMarkerMining: endMarker.miningPoints,
      rangeMining: rangeMarker.miningPoints,
      rangeCount: rangeMarker.count,
    },
    curveSelectionAfterClicks: { click1: afterClick1.curveSelection, click2: afterClick2.curveSelection, click3: afterClick3.curveSelection, afterGenerate: postSelection.curveSelection },
    generation: {
      requestBody: postBody,
      requestSessionId: postHeaders['x-session-id'] ?? null,
      status: postResponse.status(),
      responseJson: postJson,
    },
    apiReadback: { url: 'http://127.0.0.1:8000/api/v1/sections', requestSessionId: postSessionId, sectionsCount: readbackChecks.length, sections: readbackChecks },
    apiResponses: apiResponses.filter((entry) => entry.url.includes('/sections')),
    consoleErrors,
    pageErrors,
    timings: [{ label: 'total', elapsedMs: Date.now() - t0 }],
    artifacts: { preGeneration: preGenerationShot, postGeneration: postGenerationShot, evidence: path.join(EVIDENCE_DIR, `t12a-${testInfo.project.name}-run-evidence.json`) },
  };
  fs.writeFileSync(path.join(EVIDENCE_DIR, `t12a-${testInfo.project.name}-run-evidence.json`), JSON.stringify(evidence, null, 2));
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test('T12b1 hover preview, active-curve priority and drag keep confirmed selection', async ({ page }, testInfo) => {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  const t0 = Date.now();
  const consoleErrors: Array<{ type: string; text: string; at: string }> = [];
  const pageErrors: string[] = [];
  const apiResponses: Array<{ url: string; status: number; method: string }> = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push({ type: message.type(), text: message.text(), at: new Date().toISOString() });
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  page.on('response', (response) => {
    if (response.url().includes('/api/v1/')) {
      apiResponses.push({ url: response.url(), status: response.status(), method: response.request().method() });
    }
  });

  const fixture = await bootCurveSelectionFixture(page);

  const projected = await page.evaluate(projectPointsInPage, {
    scenePoints: [
      miningToScene([CLICK_TARGET_EW.first, N_MIN, Z_LEVEL]),
      miningToScene([CLICK_TARGET_EW.secondE, N_MIN, Z_LEVEL]),
      miningToScene([CLICK_TARGET_EW.thirdE, N_MIN, Z_LEVEL]),
      miningToScene([CENTER_E, N_MIN + 1, Z_LEVEL]),
      miningToScene([E_MIN, N_MIN, Z_LEVEL]),
      miningToScene([E_MAX, N_MIN, Z_LEVEL]),
      miningToScene([E_MIN, N_MIN + 1, Z_LEVEL]),
      miningToScene([E_MAX, N_MIN + 1, Z_LEVEL]),
    ],
  });
  const aCenter = projected.projected[0];
  const p20 = projected.projected[1];
  const p80 = projected.projected[2];
  const bCenter = projected.projected[3];
  const aStartProj = projected.projected[4];
  const aEndProj = projected.projected[5];
  const bStartProj = projected.projected[6];
  const bEndProj = projected.projected[7];

  const abCenterDistancePx = Math.hypot(bCenter.x - aCenter.x, bCenter.y - aCenter.y);
  expect(abCenterDistancePx).toBeLessThan(8);

  await page.mouse.click(aCenter.x, aCenter.y);
  const afterChoose = await waitForSelection(page, (snapshot) => snapshot.curveSelection.curveId === CURVE_A_ID && snapshot.curveSelection.start === null && snapshot.curveSelection.end === null, 'choose curve A');
  expect(afterChoose.curveSelection.rejection).toBeNull();
  await expect(page.locator('[data-slot="section-curve-form"] span[title="0-0"]')).toBeVisible();

  const hoverObservations: Array<{ label: string; hoveredPageCoords: number[]; role: string | null; visible: boolean; count: number | null; pageCoords: number[][]; miningPoints: number[][]; pixelError: number }> = [];
  const hoverPoints: Array<[string, CssPoint]> = [['p20', p20], ['center', aCenter], ['p80', p80]];
  for (const [label, point] of hoverPoints) {
    await page.mouse.move(point.x, point.y, { steps: 8 });
    const markers = await waitForPreviewMarkers(page, 'visible');
    const preview = markers['curve-selection-preview'];
    if (preview === null) throw new Error('preview object missing');
    const pixelError = Math.hypot(preview.pageCoords[0][0] - point.x, preview.pageCoords[0][1] - point.y);
    hoverObservations.push({ label, hoveredPageCoords: [point.x, point.y], role: preview.role, visible: preview.visible, count: preview.count, pageCoords: preview.pageCoords, miningPoints: preview.miningPoints, pixelError });
    expect(preview.visible).toBe(true);
    expect(preview.count).toBe(1);
    expect(pixelError).toBeLessThanOrEqual(2);
    const mining = preview.miningPoints[0];
    expect(Math.abs(mining[1] - N_MIN)).toBeLessThan(1e-6);
    expect(mining[0]).toBeGreaterThanOrEqual(E_MIN + 20 - 1e-6);
    expect(mining[0]).toBeLessThanOrEqual(E_MIN + 80 + 1e-6);
  }
  const previewTravelPx = Math.hypot(
    hoverObservations[2].pageCoords[0][0] - hoverObservations[0].pageCoords[0][0],
    hoverObservations[2].pageCoords[0][1] - hoverObservations[0].pageCoords[0][1],
  );
  expect(previewTravelPx).toBeGreaterThan(50);
  const afterHover = await readSelection(page);
  expect(afterHover.curveSelection.curveId).toBe(CURVE_A_ID);
  expect(afterHover.curveSelection.start).toBeNull();
  expect(afterHover.curveSelection.end).toBeNull();
  expect(afterHover.curveSelection.rejection).toBeNull();

  const previewShot = path.join(EVIDENCE_DIR, `t12b1-${testInfo.project.name}-preview-hover.png`);
  await page.screenshot({ path: previewShot, fullPage: true });

  await page.mouse.click(bCenter.x, bCenter.y);
  const afterBClick = await waitForSelection(page, (snapshot) => snapshot.curveSelection.curveId === CURVE_A_ID && snapshot.curveSelection.end === null, 'click on neighbor B center must resolve on active curve A');
  expect(afterBClick.curveSelection.curveId).toBe(CURVE_A_ID);
  expect(afterBClick.curveSelection.end).toBeNull();
  const startAfterB = afterBClick.curveSelection.start;
  let bClickOutcome: string;
  if (startAfterB === null) {
    bClickOutcome = 'rejected-with-reason';
    expect(afterBClick.curveSelection.rejection).not.toBeNull();
  } else {
    bClickOutcome = 'accepted-on-active-curve-A';
    expect(startAfterB.curveId).toBe(CURVE_A_ID);
    expect(startAfterB.segmentIndex).toBe(0);
    expect(Math.abs(startAfterB.position[1] - N_MIN)).toBeLessThan(1e-6);
    expect(afterBClick.curveSelection.rejection).toBeNull();
  }

  const beforeOutsideClick = await readSelection(page);
  const awaySign = bCenter.y <= aCenter.y ? 1 : -1;
  const outsidePoint: CssPoint = { x: aCenter.x, y: aCenter.y + 25 * awaySign };
  const outsideToADistance = pointToSegmentDistancePx(outsidePoint, aStartProj, aEndProj);
  const outsideToBDistance = pointToSegmentDistancePx(outsidePoint, bStartProj, bEndProj);
  expect(outsideToADistance).toBeGreaterThan(8);
  expect(outsideToBDistance).toBeGreaterThan(8);

  await page.mouse.move(outsidePoint.x, outsidePoint.y, { steps: 8 });
  const previewHiddenAfterMove = await waitForPreviewMarkers(page, 'hidden');
  await page.mouse.click(outsidePoint.x, outsidePoint.y);
  await page.waitForTimeout(400);
  const afterOutsideClick = await readSelection(page);
  expect(selectionEquals(afterOutsideClick.curveSelection, beforeOutsideClick.curveSelection)).toBe(true);
  const afterOutsideClickMarkers = await waitForPreviewMarkers(page, 'hidden');
  const outsidePreview = afterOutsideClickMarkers['curve-selection-preview'];
  expect(outsidePreview === null || !outsidePreview.visible).toBe(true);

  const preDrag = await readSelection(page);
  const poseBeforeDrag = await page.evaluate(readCameraPoseInPage);
  const dragStart: CssPoint = { x: aCenter.x, y: aCenter.y };
  const dragEnd: CssPoint = { x: aCenter.x, y: aCenter.y + 60 * awaySign };
  const dragLengthPx = Math.hypot(dragEnd.x - dragStart.x, dragEnd.y - dragStart.y);
  expect(dragLengthPx).toBeGreaterThan(3);
  const dragEndToA = pointToSegmentDistancePx(dragEnd, aStartProj, aEndProj);
  const dragEndToB = pointToSegmentDistancePx(dragEnd, bStartProj, bEndProj);
  expect(dragEndToA).toBeGreaterThan(8);
  expect(dragEndToB).toBeGreaterThan(8);

  await page.mouse.move(dragStart.x, dragStart.y);
  await page.mouse.down();
  await page.mouse.move(dragEnd.x, dragEnd.y, { steps: 12 });
  await page.mouse.up();
  const poseAfterDrag = await page.evaluate(readCameraPoseInPage);
  const cameraTravel = Math.hypot(
    poseAfterDrag.cameraPosition[0] - poseBeforeDrag.cameraPosition[0],
    poseAfterDrag.cameraPosition[1] - poseBeforeDrag.cameraPosition[1],
    poseAfterDrag.cameraPosition[2] - poseBeforeDrag.cameraPosition[2],
  );
  expect(cameraTravel).toBeGreaterThan(1);
  await page.waitForTimeout(400);
  const afterDrag = await readSelection(page);
  expect(afterDrag.curveSelection.end).toBeNull();
  expect(selectionEquals(afterDrag.curveSelection, preDrag.curveSelection)).toBe(true);

  const evidence = {
    task: 'T12b1',
    test: testInfo.title,
    project: testInfo.project.name,
    fixtureScope: {
      mocked: 'browser GET /api/v1/meshes/** (info, vertices, breaklines) served deterministic synthetic geometry in the browser only; non-GET mesh requests are not fulfilled and continue to the network; no sections generation HTTP is exercised by this test',
      programmaticSetup: 'design/topo mesh ids set via imported session store module (URL resolved from performance entries) and R3F camera position (0,200,120) set programmatically; sections accordion, curves tab, topo-layer checkbox, canvas clicks, native mouse moves and the native drag were real user-level input',
      curves: { '0-0': CURVE_A, '1-0': CURVE_B },
    },
    moduleUrls: { session: fixture.bootSnapshot.sessionUrl, fiber: fixture.cameraPrep.fiberUrl, fiberHashSource: fixture.cameraPrep.fiberHashSource },
    selectionContext: fixture.firstSnapshot.curveSelection.context,
    projections: { rect: projected.rect, viewport: projected.viewport, cameraPosition: projected.cameraPosition, points: { aCenter, p20, p80, bCenter, aStartProj, aEndProj, bStartProj, bEndProj } },
    abCenterDistancePx,
    hover: { observations: hoverObservations, travelPx: previewTravelPx, selectionAfter: afterHover.curveSelection },
    bCenterClick: { projected: bCenter, outcome: bClickOutcome, selectionAfter: afterBClick.curveSelection },
    outsideClick: {
      point: outsidePoint,
      awaySign,
      distanceToCurveAPx: outsideToADistance,
      distanceToCurveBPx: outsideToBDistance,
      selectionBefore: beforeOutsideClick.curveSelection,
      selectionAfter: afterOutsideClick.curveSelection,
      previewHiddenAfterMove: previewHiddenAfterMove['curve-selection-preview'] === null || previewHiddenAfterMove['curve-selection-preview']?.visible === false,
      previewHiddenAfterClick: outsidePreview === null || !outsidePreview.visible,
    },
    drag: {
      start: dragStart,
      end: dragEnd,
      lengthPx: dragLengthPx,
      endDistanceToCurveAPx: dragEndToA,
      endDistanceToCurveBPx: dragEndToB,
      poseBefore: poseBeforeDrag,
      poseAfter: poseAfterDrag,
      cameraTravel,
      selectionBefore: preDrag.curveSelection,
      selectionAfter: afterDrag.curveSelection,
    },
    apiResponses,
    consoleErrors,
    pageErrors,
    timings: [{ label: 'total', elapsedMs: Date.now() - t0 }],
    artifacts: { previewHover: previewShot, evidence: path.join(EVIDENCE_DIR, `t12b1-${testInfo.project.name}-preview-eligibility-drag.json`) },
  };
  fs.writeFileSync(path.join(EVIDENCE_DIR, `t12b1-${testInfo.project.name}-preview-eligibility-drag.json`), JSON.stringify(evidence, null, 2));
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test('T12b1 reset and escape clear selection, retain context and params, focus help summary', async ({ page }, testInfo) => {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  const t0 = Date.now();
  const consoleErrors: Array<{ type: string; text: string; at: string }> = [];
  const pageErrors: string[] = [];
  const apiResponses: Array<{ url: string; status: number; method: string }> = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push({ type: message.type(), text: message.text(), at: new Date().toISOString() });
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  page.on('response', (response) => {
    if (response.url().includes('/api/v1/')) {
      apiResponses.push({ url: response.url(), status: response.status(), method: response.request().method() });
    }
  });

  const fixture = await bootCurveSelectionFixture(page);

  const projected = await page.evaluate(projectPointsInPage, {
    scenePoints: [
      miningToScene([CLICK_TARGET_EW.first, N_MIN, Z_LEVEL]),
      miningToScene([CLICK_TARGET_EW.secondE, N_MIN, Z_LEVEL]),
    ],
  });
  const aCenter = projected.projected[0];
  const p20 = projected.projected[1];

  await page.mouse.click(aCenter.x, aCenter.y);
  await waitForSelection(page, (snapshot) => snapshot.curveSelection.curveId === CURVE_A_ID && snapshot.curveSelection.start === null, 'choose curve A via mouse');
  await page.mouse.click(p20.x, p20.y);
  const withStart = await waitForSelection(page, (snapshot) => snapshot.curveSelection.start !== null, 'start anchor via mouse');
  const contextBeforeReset = withStart.curveSelection.context;
  expect(contextBeforeReset).not.toBeNull();

  const spacingInput = page.locator('#curve-spacing');
  const spacingBefore = await spacingInput.inputValue();
  await spacingInput.fill('25');
  const spacingTyped = await spacingInput.inputValue();
  expect(spacingTyped).toBe('25');
  expect(spacingTyped).not.toBe(spacingBefore);

  const poseBeforeReset = await page.evaluate(readCameraPoseInPage);
  const resetButton = page.locator('[data-slot="section-curve-form"]').getByRole('button', { name: 'RESTABLECER SELECCIÓN' });
  await expect(resetButton).toBeVisible();
  await resetButton.click();
  const afterReset = await waitForSelection(page, (snapshot) => snapshot.curveSelection.curveId === null && snapshot.curveSelection.start === null && snapshot.curveSelection.end === null, 'reset clears selection');
  expect(afterReset.curveSelection.rejection).toBeNull();
  expect(afterReset.curveSelection.context).toEqual(contextBeforeReset);
  const spacingAfterReset = await spacingInput.inputValue();
  expect(spacingAfterReset).toBe(spacingTyped);
  const helpSummary = page.locator('[data-slot="section-curve-form"] summary');
  await expect(helpSummary).toBeFocused();
  const poseAfterReset = await page.evaluate(readCameraPoseInPage);
  const afterResetShot = path.join(EVIDENCE_DIR, `t12b1-${testInfo.project.name}-after-reset.png`);
  await page.screenshot({ path: afterResetShot, fullPage: true });

  await page.mouse.click(aCenter.x, aCenter.y);
  const reChosen = await waitForSelection(page, (snapshot) => snapshot.curveSelection.curveId === CURVE_A_ID && snapshot.curveSelection.start === null, 're-choose curve A for escape');
  const markersAfterRechoose = await page.evaluate(sceneMarkersInPage, { centerE: CENTER_E, centerN: CENTER_N, centerZ: CENTER_Z }) as MarkerSnapshot;

  await spacingInput.click();
  await expect(spacingInput).toBeFocused();
  await page.keyboard.press('Escape');
  const afterEscape1 = await waitForSelection(page, (snapshot) => snapshot.curveSelection.curveId === null && snapshot.curveSelection.start === null && snapshot.curveSelection.end === null, 'escape clears active curve');
  expect(afterEscape1.curveSelection.rejection).toBeNull();
  const spacingAfterEscape1 = await spacingInput.inputValue();
  expect(spacingAfterEscape1).toBe(spacingTyped);
  await expect(helpSummary).toBeFocused();

  await spacingInput.click();
  await expect(spacingInput).toBeFocused();
  await page.keyboard.press('Escape');
  await page.waitForTimeout(300);
  await expect(spacingInput).toBeFocused();
  const afterEscape2 = await readSelection(page);
  expect(afterEscape2.curveSelection.curveId).toBeNull();
  expect(afterEscape2.curveSelection.start).toBeNull();
  expect(afterEscape2.curveSelection.end).toBeNull();
  const spacingAfterEscape2 = await spacingInput.inputValue();

  const sectionPosts = apiResponses.filter((entry) => entry.method === 'POST' && entry.url.includes('/sections'));
  expect(sectionPosts).toHaveLength(0);

  const afterEscapeShot = path.join(EVIDENCE_DIR, `t12b1-${testInfo.project.name}-after-escape.png`);
  await page.screenshot({ path: afterEscapeShot, fullPage: true });

  const evidence = {
    task: 'T12b1',
    test: testInfo.title,
    project: testInfo.project.name,
    fixtureScope: {
      mocked: 'browser GET /api/v1/meshes/** (info, vertices, breaklines) served deterministic synthetic geometry in the browser only; non-GET mesh requests are not fulfilled and continue to the network; no sections generation HTTP is exercised by this test and no HTTP cancellation is claimed',
      programmaticSetup: 'design/topo mesh ids set via imported session store module (URL resolved from performance entries) and R3F camera position (0,200,120) set programmatically; sections accordion, curves tab, topo-layer checkbox, canvas clicks, reset button, numeric input focus and keyboard Escape were real user-level input; session store was only read after the mesh setup',
      curves: { '0-0': CURVE_A, '1-0': CURVE_B },
    },
    moduleUrls: { session: fixture.bootSnapshot.sessionUrl, fiber: fixture.cameraPrep.fiberUrl, fiberHashSource: fixture.cameraPrep.fiberHashSource },
    selectionContext: fixture.firstSnapshot.curveSelection.context,
    projections: { rect: projected.rect, viewport: projected.viewport, cameraPosition: projected.cameraPosition, points: { aCenter, p20 } },
    selectionBeforeReset: withStart.curveSelection,
    spacing: { before: spacingBefore, typed: spacingTyped, afterReset: spacingAfterReset, afterEscape1: spacingAfterEscape1, afterEscape2: spacingAfterEscape2 },
    cameraPose: { beforeReset: poseBeforeReset, afterReset: poseAfterReset },
    reset: { selectionAfter: afterReset.curveSelection, contextBefore: contextBeforeReset, contextAfter: afterReset.curveSelection.context },
    escape: {
      rechooseSelection: reChosen.curveSelection,
      previewAfterRechoose: markersAfterRechoose['curve-selection-preview'],
      selectionAfterEscape1: afterEscape1.curveSelection,
      selectionAfterEscape2: afterEscape2.curveSelection,
    },
    apiResponses,
    consoleErrors,
    pageErrors,
    timings: [{ label: 'total', elapsedMs: Date.now() - t0 }],
    artifacts: { afterReset: afterResetShot, afterEscape: afterEscapeShot, evidence: path.join(EVIDENCE_DIR, `t12b1-${testInfo.project.name}-reset-escape.json`) },
  };
  fs.writeFileSync(path.join(EVIDENCE_DIR, `t12b1-${testInfo.project.name}-reset-escape.json`), JSON.stringify(evidence, null, 2));
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});

test('T12b2 native wheel zoom separates neighbor and reversed real selection generates reversed real sections', async ({ page, request }, testInfo) => {
  fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
  const t0 = Date.now();
  const consoleErrors: Array<{ type: string; text: string; at: string }> = [];
  const pageErrors: string[] = [];
  const apiResponses: Array<{ url: string; status: number; method: string }> = [];
  const dialogs: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push({ type: message.type(), text: message.text(), at: new Date().toISOString() });
  });
  page.on('pageerror', (error) => pageErrors.push(String(error)));
  page.on('dialog', (dialog) => {
    dialogs.push(`${dialog.type()}: ${dialog.message()}`);
    dialog.dismiss().catch(() => undefined);
  });
  page.on('response', (response) => {
    if (response.url().includes('/api/v1/')) {
      apiResponses.push({ url: response.url(), status: response.status(), method: response.request().method() });
    }
  });

  const projectTag = testInfo.project.name.endsWith('-dpr2') ? 'dpr2' : 'dpr1';
  const expectedDpr = projectTag === 'dpr2' ? 2 : 1;

  const fixture = await bootCurveSelectionFixture(page);

  const dprBefore = await page.evaluate(readDprInPage) as DprSnapshot;
  expect(dprBefore.windowDpr).toBe(expectedDpr);
  expect(dprBefore.glPixelRatio).toBe(expectedDpr);
  expect(dprBefore.viewportDpr).toBe(expectedDpr);
  expect(dprBefore.canvasBufferWidth).toBe(Math.round(dprBefore.canvasCssWidth * expectedDpr));
  expect(dprBefore.canvasBufferHeight).toBe(Math.round(dprBefore.canvasCssHeight * expectedDpr));

  const stationEs = { p20: E_MIN + 20, p40: E_MIN + 40, p60: E_MIN + 60, p80: E_MIN + 80 } as const;
  const projectedBefore = await page.evaluate(projectPointsInPage, {
    scenePoints: [
      miningToScene([CLICK_TARGET_EW.first, N_MIN, Z_LEVEL]),
      miningToScene([CENTER_E, N_MIN + 1, Z_LEVEL]),
    ],
  });
  const [aCenterBefore, bCenterBefore] = projectedBefore.projected;
  const abGapBefore = Math.hypot(bCenterBefore.x - aCenterBefore.x, bCenterBefore.y - aCenterBefore.y);
  expect(abGapBefore).toBeGreaterThan(0);

  await page.mouse.click(aCenterBefore.x, aCenterBefore.y);
  const afterChoose = await waitForSelection(page, (snapshot) => snapshot.curveSelection.curveId === CURVE_A_ID && snapshot.curveSelection.start === null && snapshot.curveSelection.end === null, 'choose curve A via real click');
  expect(afterChoose.curveSelection.rejection).toBeNull();
  await expect(page.locator('[data-slot="section-curve-form"] span[title="0-0"]')).toBeVisible();

  const poseBeforeZoom = await page.evaluate(readCameraPoseInPage);
  const cameraDistanceOf = (pose: CameraPoseSnapshot): number => {
    const target = pose.controlsTarget ?? [0, 0, 0];
    return Math.hypot(pose.cameraPosition[0] - target[0], pose.cameraPosition[1] - target[1], pose.cameraPosition[2] - target[2]);
  };
  const zoomSamples: Array<{ iteration: number; abGapPx: number; cameraDistance: number }> = [];
  zoomSamples.push({ iteration: 0, abGapPx: abGapBefore, cameraDistance: cameraDistanceOf(poseBeforeZoom) });

  await page.mouse.move(aCenterBefore.x, aCenterBefore.y, { steps: 4 });
  let zoomIterations = 0;
  const zoomMaxIterations = 40;
  let wheelDeltaTotal = 0;
  let poseNow = poseBeforeZoom;
  while (zoomIterations < zoomMaxIterations) {
    await page.mouse.wheel(0, -240);
    wheelDeltaTotal -= 240;
    zoomIterations += 1;
    await page.waitForTimeout(300);
    const reprojected = await page.evaluate(projectPointsInPage, {
      scenePoints: [
        miningToScene([CLICK_TARGET_EW.first, N_MIN, Z_LEVEL]),
        miningToScene([CENTER_E, N_MIN + 1, Z_LEVEL]),
      ],
    });
    const aNow = reprojected.projected[0];
    const bNow = reprojected.projected[1];
    const abGapNow = Math.hypot(bNow.x - aNow.x, bNow.y - aNow.y);
    poseNow = await page.evaluate(readCameraPoseInPage);
    zoomSamples.push({ iteration: zoomIterations, abGapPx: abGapNow, cameraDistance: cameraDistanceOf(poseNow) });
    if (abGapNow > 10) break;
  }
  const gapInLoopMet = zoomSamples[zoomSamples.length - 1].abGapPx > 10;
  expect(gapInLoopMet).toBe(true);
  expect(zoomIterations).toBeLessThan(zoomMaxIterations);

  let settleGap = zoomSamples[zoomSamples.length - 1].abGapPx;
  for (let settleRound = 0; settleRound < 12; settleRound += 1) {
    await page.waitForTimeout(400);
    const settleProjection = await page.evaluate(projectPointsInPage, {
      scenePoints: [
        miningToScene([CLICK_TARGET_EW.first, N_MIN, Z_LEVEL]),
        miningToScene([CENTER_E, N_MIN + 1, Z_LEVEL]),
      ],
    });
    const stableGap = Math.hypot(settleProjection.projected[1].x - settleProjection.projected[0].x, settleProjection.projected[1].y - settleProjection.projected[0].y);
    if (Math.abs(stableGap - settleGap) < 0.05) {
      settleGap = stableGap;
      break;
    }
    settleGap = stableGap;
  }

  const cameraTravelZoom = Math.hypot(
    poseNow.cameraPosition[0] - poseBeforeZoom.cameraPosition[0],
    poseNow.cameraPosition[1] - poseBeforeZoom.cameraPosition[1],
    poseNow.cameraPosition[2] - poseBeforeZoom.cameraPosition[2],
  );
  expect(cameraTravelZoom).toBeGreaterThan(1);
  expect(settleGap).toBeGreaterThan(abGapBefore);
  const selectionAfterZoom = await readSelection(page);
  expect(selectionEquals(selectionAfterZoom.curveSelection, afterChoose.curveSelection)).toBe(true);

  const dprAfterZoom = await page.evaluate(readDprInPage) as DprSnapshot;
  expect(dprAfterZoom.windowDpr).toBe(expectedDpr);
  expect(dprAfterZoom.glPixelRatio).toBe(expectedDpr);
  expect(dprAfterZoom.canvasBufferWidth).toBe(Math.round(dprAfterZoom.canvasCssWidth * expectedDpr));

  const afterZoomShot = path.join(EVIDENCE_DIR, `t12b2-${projectTag}-after-zoom.png`);
  await page.screenshot({ path: afterZoomShot, fullPage: true });

  const projectedAfterZoom = await page.evaluate(projectPointsInPage, {
    scenePoints: [
      miningToScene([stationEs.p20, N_MIN, Z_LEVEL]),
      miningToScene([stationEs.p40, N_MIN, Z_LEVEL]),
      miningToScene([stationEs.p60, N_MIN, Z_LEVEL]),
      miningToScene([stationEs.p80, N_MIN, Z_LEVEL]),
      miningToScene([CENTER_E, N_MIN + 1, Z_LEVEL]),
      miningToScene([E_MIN, N_MIN, Z_LEVEL]),
      miningToScene([E_MAX, N_MIN, Z_LEVEL]),
      miningToScene([CENTER_E, N_MIN, Z_LEVEL]),
    ],
  });
  const [p20After, p40After, p60After, p80After, bCenterAfter, aStartAfter, aEndAfter, aCenterAfter] = projectedAfterZoom.projected;
  const rectAfterZoom = projectedAfterZoom.rect;
  const onScreen = (point: CssPoint): boolean => (
    point.x >= rectAfterZoom.left + 10
    && point.x <= rectAfterZoom.left + rectAfterZoom.width - 10
    && point.y >= rectAfterZoom.top + 10
    && point.y <= rectAfterZoom.top + rectAfterZoom.height - 10
  );
  const stationPairs = [
    { label: '80-20', hi: p80After, lo: p20After },
    { label: '60-40', hi: p60After, lo: p40After },
  ];
  const stationPairChecks = stationPairs.map((pair) => ({ label: pair.label, hiOnScreen: onScreen(pair.hi), loOnScreen: onScreen(pair.lo) }));
  const chosenPair = stationPairs.find((pair) => onScreen(pair.hi) && onScreen(pair.lo));
  if (chosenPair === undefined) {
    throw new Error(`no interior station pair onscreen after zoom: ${JSON.stringify({ rect: rectAfterZoom, checks: stationPairChecks })}`);
  }

  const abGapAfterZoom = Math.hypot(bCenterAfter.x - aCenterAfter.x, bCenterAfter.y - aCenterAfter.y);
  const bCenterToCurveAPx = pointToSegmentDistancePx(bCenterAfter, aStartAfter, aEndAfter);
  expect(settleGap).toBeGreaterThan(10);
  expect(bCenterAfter.depth).toBeGreaterThan(0);
  expect(onScreen(bCenterAfter)).toBe(true);
  const bCanvasProbe = await page.evaluate(bCanvasProbeInPage, { x: bCenterAfter.x, y: bCenterAfter.y }) as Record<string, unknown>;
  expect(bCanvasProbe.hitIsNull).toBe(false);
  expect((bCanvasProbe.hit as { tag: string }).tag).toBe('CANVAS');
  expect(bCanvasProbe.sameElement).toBe(true);
  expect(bCanvasProbe.sameRect).toBe(true);
  expect((bCanvasProbe.hit as { isInsideViewer: boolean }).isInsideViewer).toBe(true);
  expect(Math.abs(abGapAfterZoom - settleGap)).toBeLessThanOrEqual(0.1);
  expect(abGapAfterZoom).toBeGreaterThan(10);
  expect(bCenterToCurveAPx).toBeGreaterThan(8);

  const selectionBeforeBClick = await readSelection(page);
  await page.mouse.click(bCenterAfter.x, bCenterAfter.y);
  await page.waitForTimeout(400);
  const selectionAfterBClick = await readSelection(page);
  expect(selectionEquals(selectionAfterBClick.curveSelection, selectionBeforeBClick.curveSelection)).toBe(true);
  expect(selectionAfterBClick.curveSelection.curveId).toBe(CURVE_A_ID);
  expect(selectionAfterBClick.curveSelection.start).toBeNull();
  expect(selectionAfterBClick.curveSelection.end).toBeNull();
  expect(selectionAfterBClick.curveSelection.rejection).toBeNull();
  expect(dialogs).toEqual([]);

  await page.mouse.click(chosenPair.hi.x, chosenPair.hi.y);
  const withReversedStart = await waitForSelection(page, (snapshot) => snapshot.curveSelection.start !== null && snapshot.curveSelection.curveId === CURVE_A_ID, 'reversed start anchor at higher station');
  const reversedStart = withReversedStart.curveSelection.start;
  if (reversedStart === null) throw new Error('reversed start anchor missing');

  await page.mouse.click(chosenPair.lo.x, chosenPair.lo.y);
  const withReversedEnd = await waitForSelection(page, (snapshot) => snapshot.curveSelection.end !== null, 'reversed end anchor at lower station');
  const reversedEnd = withReversedEnd.curveSelection.end;
  if (reversedEnd === null) throw new Error('reversed end anchor missing');

  expect(withReversedEnd.curveSelection.start).toEqual(reversedStart);
  expect(withReversedEnd.curveSelection.curveId).toBe(CURVE_A_ID);
  expect(withReversedEnd.curveSelection.rejection).toBeNull();
  expect(reversedStart.curveId).toBe(CURVE_A_ID);
  expect(reversedEnd.curveId).toBe(CURVE_A_ID);
  expect(reversedStart.segmentIndex).toBe(0);
  expect(reversedEnd.segmentIndex).toBe(0);
  expect(reversedStart.chainage).toBeGreaterThan(reversedEnd.chainage);
  expect(reversedStart.t).toBeGreaterThan(reversedEnd.t);
  expect(reversedStart.t).toBeGreaterThan(0);
  expect(reversedStart.t).toBeLessThan(1);
  expect(reversedEnd.t).toBeGreaterThan(0);
  expect(reversedEnd.t).toBeLessThan(1);
  expect(reversedStart.position[1]).toBeCloseTo(N_MIN, 6);
  expect(reversedEnd.position[1]).toBeCloseTo(N_MIN, 6);
  expect(reversedStart.position[0]).toBeGreaterThan(E_MIN);
  expect(reversedStart.position[0]).toBeLessThan(E_MAX);
  expect(reversedEnd.position[0]).toBeGreaterThan(E_MIN);
  expect(reversedEnd.position[0]).toBeLessThan(E_MAX);
  expect(reversedStart.position[0]).toBeGreaterThan(reversedEnd.position[0]);
  await expect(page.locator('[data-slot="curve-start-summary"]')).toContainText(reversedStart.position[0].toFixed(3));
  await expect(page.locator('[data-slot="curve-start-summary"]')).toContainText(reversedStart.position[1].toFixed(3));
  await expect(page.locator('[data-slot="curve-end-summary"]')).toContainText(reversedEnd.position[0].toFixed(3));
  await expect(page.locator('[data-slot="curve-end-summary"]')).toContainText(reversedEnd.position[1].toFixed(3));

  const markersReversed = await page.evaluate(sceneMarkersInPage, { centerE: CENTER_E, centerN: CENTER_N, centerZ: CENTER_Z }) as MarkerSnapshot;
  const startMarkerReversed = markersReversed['curve-selection-start'];
  const endMarkerReversed = markersReversed['curve-selection-end'];
  const rangeMarkerReversed = markersReversed['curve-selection-range'];
  if (startMarkerReversed === null || endMarkerReversed === null || rangeMarkerReversed === null) {
    throw new Error(`reversed marker objects missing: ${JSON.stringify(Object.fromEntries(Object.entries(markersReversed).map(([key, value]) => [key, value !== null])))}`);
  }
  expect(startMarkerReversed.count).toBe(1);
  expect(endMarkerReversed.count).toBe(1);
  expect(startMarkerReversed.role).toBe('start');
  expect(endMarkerReversed.role).toBe('end');
  expect(startMarkerReversed.visible).toBe(true);
  expect(endMarkerReversed.visible).toBe(true);
  const startMarkerErrorPx = Math.hypot(startMarkerReversed.pageCoords[0][0] - chosenPair.hi.x, startMarkerReversed.pageCoords[0][1] - chosenPair.hi.y);
  const endMarkerErrorPx = Math.hypot(endMarkerReversed.pageCoords[0][0] - chosenPair.lo.x, endMarkerReversed.pageCoords[0][1] - chosenPair.lo.y);
  expect(startMarkerErrorPx).toBeLessThanOrEqual(1.0);
  expect(endMarkerErrorPx).toBeLessThanOrEqual(1.0);

  expect(rangeMarkerReversed.count).toBe(2);
  expect(rangeMarkerReversed.visible).toBe(true);
  expect(rangeMarkerReversed.role).toBe('range');
  const rangeStartReversed = rangeMarkerReversed.miningPoints[0];
  const rangeEndReversed = rangeMarkerReversed.miningPoints[1];
  expect(Math.abs(rangeStartReversed[0] - reversedStart.position[0])).toBeLessThan(1e-4);
  expect(Math.abs(rangeStartReversed[1] - reversedStart.position[1])).toBeLessThan(1e-4);
  expect(Math.abs(rangeEndReversed[0] - reversedEnd.position[0])).toBeLessThan(1e-4);
  expect(Math.abs(rangeEndReversed[1] - reversedEnd.position[1])).toBeLessThan(1e-4);
  expect(rangeStartReversed[0]).toBeGreaterThan(rangeEndReversed[0]);
  expect(Math.abs(rangeStartReversed[0] - E_MIN)).toBeGreaterThan(5);
  expect(Math.abs(rangeEndReversed[0] - E_MAX)).toBeGreaterThan(5);
  await expect(page.locator('[data-slot="curve-range-length"]')).toBeVisible();

  const reversedSelectedShot = path.join(EVIDENCE_DIR, `t12b2-${projectTag}-reversed-selected.png`);
  await page.screenshot({ path: reversedSelectedShot, fullPage: true });

  const generateButton = page.locator('[data-slot="section-curve-form"]').getByRole('button', { name: 'Generar perfiles' });
  await expect(generateButton).toBeEnabled();

  const [postResponse] = await Promise.all([
    page.waitForResponse((response) => response.request().method() === 'POST' && response.url().includes('/api/v1/sections/curve'), { timeout: 30000 }),
    generateButton.click(),
  ]);
  expect(postResponse.status()).toBe(200);
  const postRequest = postResponse.request();
  const postHeaders = postRequest.headers();
  const postBody = postRequest.postDataJSON();
  const postJson = await postResponse.json();
  const postSessionId = postHeaders['x-session-id'] ?? postResponse.headers()['x-session-id'] ?? null;
  expect(postSessionId).not.toBeNull();

  expect(Array.isArray(postBody.points)).toBe(true);
  expect(postBody.points).toHaveLength(2);
  for (const point of postBody.points) {
    expect(Array.isArray(point)).toBe(true);
    expect(point).toHaveLength(2);
  }
  expect(postBody.points[0]).toEqual([reversedStart.position[0], reversedStart.position[1]]);
  expect(postBody.points[1]).toEqual([reversedEnd.position[0], reversedEnd.position[1]]);
  expect(postBody.spacing).toBe(10);
  expect(postBody.length).toBe(200);
  expect(postBody.length_up).toBe(100);
  expect(postBody.length_down).toBe(100);
  expect(postBody.sector).toBe('');

  const postSelection = await waitForSelection(page, (snapshot) => snapshot.curveSelection.start === null && snapshot.curveSelection.end === null, 'selection reset after generate');
  expect(postSelection.curveSelection.rejection).toBeNull();

  const readbackResponse = await request.get('http://127.0.0.1:8000/api/v1/sections', {
    headers: { 'X-Session-ID': postSessionId as string },
  });
  expect(readbackResponse.ok()).toBe(true);
  const readback = await readbackResponse.json();
  expect(Array.isArray(readback)).toBe(true);
  expect(readback.length).toBeGreaterThan(0);

  const spanStart = postBody.points[0];
  const spanEnd = postBody.points[1];
  const spanDir = [spanEnd[0] - spanStart[0], spanEnd[1] - spanStart[1]];
  const spanLength = Math.hypot(spanDir[0], spanDir[1]);
  const spanSq = spanDir[0] * spanDir[0] + spanDir[1] * spanDir[1];
  const readbackChecks = (readback as Array<{ name: string; origin: number[]; azimuth: number; length: number }>).map((section, index) => {
    const rel = [section.origin[0] - spanStart[0], section.origin[1] - spanStart[1]];
    const t = (rel[0] * spanDir[0] + rel[1] * spanDir[1]) / spanSq;
    const projection = [spanStart[0] + t * spanDir[0], spanStart[1] + t * spanDir[1]];
    const distance = Math.hypot(projection[0] - section.origin[0], projection[1] - section.origin[1]);
    const alongFromNewStart = t * spanLength;
    return { name: section.name, origin: section.origin, azimuth: section.azimuth, length: section.length, t, distanceToSpanLine: distance, alongFromNewStart, index };
  });
  expect(readbackChecks.length).toBeGreaterThan(0);
  const halfSpacing = 5;
  const spacingUsed = 10;
  const expectedCount = spanLength < spacingUsed ? 1 : Math.ceil((spanLength - halfSpacing) / spacingUsed);
  expect(readbackChecks).toHaveLength(expectedCount);
  for (let index = 0; index < readbackChecks.length; index += 1) {
    const check = readbackChecks[index];
    expect(check.t).toBeGreaterThan(0);
    expect(check.t).toBeLessThan(1);
    expect(check.distanceToSpanLine).toBeLessThan(1e-6);
    expect(Math.abs(check.alongFromNewStart - (halfSpacing + spacingUsed * index))).toBeLessThan(1e-6);
    expect(check.azimuth).toBe(0);
  }
  for (let index = 1; index < readbackChecks.length; index += 1) {
    expect(readbackChecks[index].origin[0]).toBeLessThan(readbackChecks[index - 1].origin[0]);
  }
  expect(readbackChecks[readbackChecks.length - 1].origin[0]).toBeGreaterThan(spanEnd[0]);

  const postSections = (postJson as { sections?: unknown }).sections;
  expect(Array.isArray(postSections)).toBe(true);
  expect(postSections).toHaveLength(expectedCount);
  expect(readback).toEqual(postSections);

  const postGenerationShot = path.join(EVIDENCE_DIR, `t12b2-${projectTag}-post-generation.png`);
  await page.screenshot({ path: postGenerationShot, fullPage: true });

  const evidence = {
    task: 'T12b2',
    test: testInfo.project.name,
    project: testInfo.project.name,
    devicePixelRatio: { expected: expectedDpr, before: dprBefore, afterZoom: dprAfterZoom },
    fixtureScope: {
      mocked: 'browser GET /api/v1/meshes/** (info, vertices, breaklines) served deterministic synthetic geometry in the browser only; non-GET mesh requests are not fulfilled and continue to the network; every POST/GET /api/v1/sections** request hit the real backend at 127.0.0.1:8000; no anchor was injected via store or callback anywhere in this test',
      fonts: 'external font network isolated via installFontFixtures (web/e2e/fixtures/fontFixtures.ts): GET https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;700&family=Outfit:wght@400;500;600;700&display=swap and the two latin-subset fonts.gstatic.com woff2 files are fulfilled from pinned licensed local fixtures (web/e2e/fixtures/fonts, SIL OFL 1.1, sources.json) in addition to the mocked GET /api/v1/meshes/**; unmatched requests continue to the network',
      programmaticSetup: 'declared existing allowed prep: design/topo mesh ids set via imported session store module and R3F camera position (0,200,120) set programmatically; sections accordion, curves tab, topo-layer checkbox, the wheel zoom, every canvas click (curve A activation, neighbor B rejection probe, reversed start and end anchors) and the Generate button click were real user-level input',
      curves: { '0-0': CURVE_A, '1-0': CURVE_B },
    },
    moduleUrls: { session: fixture.bootSnapshot.sessionUrl, fiber: fixture.cameraPrep.fiberUrl, fiberHashSource: fixture.cameraPrep.fiberHashSource },
    selectionContext: fixture.firstSnapshot.curveSelection.context,
    projections: {
      beforeZoom: { rect: projectedBefore.rect, viewport: projectedBefore.viewport, cameraPosition: projectedBefore.cameraPosition, aCenter: aCenterBefore, bCenter: bCenterBefore },
      afterZoom: { rect: rectAfterZoom, viewport: projectedAfterZoom.viewport, cameraPosition: projectedAfterZoom.cameraPosition, points: { p20: p20After, p40: p40After, p60: p60After, p80: p80After, bCenter: bCenterAfter, aCenter: aCenterAfter, aStart: aStartAfter, aEnd: aEndAfter } },
    },
    zoom: {
      gapBeforePx: abGapBefore,
      gapInLoopFinalPx: gapInLoopMet ? zoomSamples[zoomSamples.length - 1].abGapPx : null,
      gapSettledPx: settleGap,
      gapAfterZoomPx: abGapAfterZoom,
      iterations: zoomIterations,
      wheelDeltaTotal,
      samples: zoomSamples,
      cameraDistanceBefore: cameraDistanceOf(poseBeforeZoom),
      cameraDistanceAfter: cameraDistanceOf(poseNow),
      cameraTravel: cameraTravelZoom,
      poseBefore: poseBeforeZoom,
      poseAfter: poseNow,
      selectionUnchangedByZoom: selectionEquals(selectionAfterZoom.curveSelection, afterChoose.curveSelection),
    },
    stationPairChoice: { checks: stationPairChecks, chosen: chosenPair.label },
    neighborSeparation: { abCenterGapPx: abGapAfterZoom, bCenterToCurveAPx, bCenterProjected: bCenterAfter },
    bClickWhileAActive: { projected: bCenterAfter, dialogsSeen: dialogs, selectionBefore: selectionBeforeBClick.curveSelection, selectionAfter: selectionAfterBClick.curveSelection, unchanged: true },
    reversedAnchors: { start: reversedStart, end: reversedEnd, trigger: 'real mouse clicks at projected stations, no anchor injection' },
    markerMetrics: {
      startMarkerErrorPx,
      endMarkerErrorPx,
      startMarkerMining: startMarkerReversed.miningPoints,
      endMarkerMining: endMarkerReversed.miningPoints,
      rangeMining: rangeMarkerReversed.miningPoints,
      rangeCount: rangeMarkerReversed.count,
      rangeOrderedStartToEndDescendingE: rangeStartReversed[0] > rangeEndReversed[0],
    },
    generation: {
      requestBody: postBody,
      requestSessionId: postHeaders['x-session-id'] ?? null,
      status: postResponse.status(),
      responseJson: postJson,
    },
    halfSpacingEngine: { spacing: spacingUsed, halfSpacingOffset: halfSpacing, spanLength, expectedCount, rule: 'origins at spacing/2 + k*spacing measured from the NEW reversed start anchor (west-bound), within span, not the old forward grid' },
    apiReadback: { url: 'http://127.0.0.1:8000/api/v1/sections', requestSessionId: postSessionId, sectionsCount: readbackChecks.length, sections: readbackChecks, azimuthFlip: { westBoundAzimuthActual: 0, eastBoundForwardReference: 180 } },
    apiResponses: apiResponses.filter((entry) => entry.url.includes('/sections')),
    consoleErrors,
    pageErrors,
    timings: [{ label: 'total', elapsedMs: Date.now() - t0 }],
    artifacts: { afterZoom: afterZoomShot, reversedSelected: reversedSelectedShot, postGeneration: postGenerationShot, evidence: path.join(EVIDENCE_DIR, `t12b2-${projectTag}-zoom-reverse-api.json`) },
  };
  fs.writeFileSync(path.join(EVIDENCE_DIR, `t12b2-${projectTag}-zoom-reverse-api.json`), JSON.stringify(evidence, null, 2));
  expect(dialogs).toEqual([]);
  expect(consoleErrors).toEqual([]);
  expect(pageErrors).toEqual([]);
});
