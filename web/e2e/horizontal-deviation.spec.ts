import { test, expect } from '@playwright/test';

const designId = 'design-fixture';
const topoId = 'topo-fixture';
const section = {
  id: 'sec-1',
  name: 'S-001',
  origin: [1000, 2000],
  azimuth: 45,
  length: 200,
  sector: 'Norte',
};

const comparisons = [1, 2].map((benchNum) => ({
  sector: 'Norte',
  section: 'S-001',
  bench_num: benchNum,
  bench_num_topo: benchNum,
  type: 'MATCH',
  level: `D${benchNum}`,
  height_design: 15,
  height_real: 15,
  height_dev: 0,
  height_status: 'CUMPLE',
  angle_design: 65,
  angle_real: 64,
  angle_dev: -1,
  angle_status: 'CUMPLE',
  berm_design: 8,
  berm_real: 8,
  berm_min: 6,
  berm_status: 'CUMPLE',
  delta_crest: 0,
  delta_toe: 0,
}));

const profile = {
  section_name: 'S-001',
  sector: 'Norte',
  origin: section.origin,
  azimuth: section.azimuth,
  design: { distances: [0, 10, 12, 20, 30, 40], elevations: [115, 100, 100, 85, 70, 55] },
  topo: { distances: [0, 10, 12, 20, 30, 40], elevations: [115, 100, 100, 85, 70, 55] },
  reconciled_design: null,
  reconciled_topo: null,
  benches_topo: [
    { bench_number: 1, crest_elevation: 115, crest_distance: 0, toe_elevation: 100, toe_distance: 10, bench_height: 15, face_angle: 65, berm_width: 8, is_ramp: false },
    { bench_number: 2, crest_elevation: 100, crest_distance: 12, toe_elevation: 85, toe_distance: 20, bench_height: 15, face_angle: 65, berm_width: 8, is_ramp: false },
  ],
  floor_elevation: 70,
  crest_elevation_max: 115,
  horizontal_deviation: {
    unit: 'm',
    method: 'horizontal_at_equal_elevation',
    direction: 'positive_overbreak_negative_underbreak',
    thresholds: { within: 1, moderate: 1.8, severe: 3 },
    points: [
      { distance: 10, elevation: 100, deviation: 0.4, category: 'within_tolerance', design_bench_num: 2, status: 'measured' },
      { distance: 12, elevation: 100, deviation: 0.4, category: 'within_tolerance', design_bench_num: 2, status: 'measured' },
      { distance: 12, elevation: 97, deviation: 4.2, category: 'overbreak_severe', design_bench_num: 2, status: 'measured' },
      { distance: 13, elevation: 92.5, deviation: -1.4, category: 'underbreak_minor', design_bench_num: 2, status: 'measured' },
      { distance: 14, elevation: 88, deviation: null, category: 'unmeasured', design_bench_num: 2, status: 'ambiguous' },
    ],
    samples: [
      { design_bench_num: 2, height_above_toe: 3, toe_elevation: 85, elevation: 88, reference_elevation: 88, design_distance: 18.4, topo_distance: 26.4, deviation: 8, category: 'overbreak_severe', status: 'measured' },
      { design_bench_num: 2, height_above_toe: 7.5, toe_elevation: 85, elevation: 92.5, reference_elevation: 92.5, design_distance: 16, topo_distance: 24, deviation: 8, category: 'overbreak_severe', status: 'measured' },
      { design_bench_num: 2, height_above_toe: 12, toe_elevation: 85, elevation: 97, reference_elevation: 97, design_distance: 13.6, topo_distance: 21.6, deviation: 8, category: 'overbreak_severe', status: 'measured' },
    ],
    summary: { measured: 4, total: 5, within_percent: 0, max_abs_deviation: 8 },
    warnings: [],
  },
};

const meshVertices = {
  x: [1000, 1020, 1000, 1020],
  y: [2000, 2000, 2020, 2020],
  z: [85, 100, 85, 100],
  faces: [[0, 1, 2], [1, 3, 2]],
};

const heatmap = {
  vertices: meshVertices,
  faces: [[0, 1, 2], [1, 3, 2]],
  cell_index_by_face: [0, 1],
  cells: [
    { deviation_m: 1.4, category: 'overbreak_minor', status: 'measured', station_m: 0, elevation_m: 92 },
    { deviation_m: 2.4, category: 'overbreak_moderate', status: 'measured', station_m: 2, elevation_m: 92 },
  ],
  unit: 'm',
  method: 'horizontal_at_equal_elevation',
  direction: 'positive_overbreak_negative_underbreak',
  thresholds: { within: 1, moderate: 1.8, severe: 3 },
  resolution: { longitudinal_step: 2, vertical_step: 1 },
  effective_resolution: { longitudinal_step_min: 2, longitudinal_step_max: 2, vertical_step_min: 1, vertical_step_max: 1 },
  summary: { measured: 2, total: 2, within_percent: 0, max_abs_deviation: 2.4 },
  warnings: [],
  assumptions: [],
  sector: 'Norte',
  bench_num: null,
};

async function mockApi(page: import('@playwright/test').Page, sector = section.sector) {
  const intercepted: string[] = [];
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace(/^\/api\/v1/, '');
    intercepted.push(`${route.request().method()} ${path}`);

    if (path === '/sections') return route.fulfill({ json: [{ ...section, sector }] });
    if (path === '/process/status') return route.fulfill({ json: { status: 'complete', current_section: null, total_sections: 1, completed_sections: 1, n_results: 2 } });
    if (path === '/process/results') return route.fulfill({ json: comparisons.map((row) => ({ ...row, sector })) });
    if (path === '/process/profiles/sec-1') return route.fulfill({ json: profile });
    if (path === `/meshes/${designId}/vertices` || path === `/meshes/${topoId}/vertices`) return route.fulfill({ json: meshVertices });
    if (path === `/meshes/${designId}/breaklines`) return route.fulfill({ json: { lines: [] } });
    if (path === `/meshes/${topoId}/horizontal-deviation`) return route.fulfill({ json: { ...heatmap, sector } });
    if (path === '/settings') return route.fulfill({ json: {
      process: { resolution: 0.1, face_threshold: 40, berm_threshold: 20 },
      tolerances: {
        bench_height: { neg: 1, pos: 1 },
        face_angle: { neg: 3, pos: 3 },
        berm_width: { min: 6 },
        inter_ramp_angle: { neg: 3, pos: 3 },
        overall_angle: { neg: 3, pos: 3 },
      },
    } });
    return route.fulfill({ json: {} });
  });
  return intercepted;
}

async function seedNonDemoSession(page: import('@playwright/test').Page) {
  await page.goto('/');
  await page.evaluate(async ({ designId: designMeshId, topoId: topoMeshId }) => {
    const { useSession } = await import('/conciliacion-geo-v02/src/stores/session.ts');
    useSession.setState({
      activeWorkspaceView: '3d',
      currentStep: 4,
      demoMode: false,
      demoData: null,
      designMeshId,
      topoMeshId,
      selectedSection: 'sec-1',
    });
  }, { designId, topoId });
}

test('non-demo 3D horizontal-deviation overlay renders colored cells', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  const intercepted = await mockApi(page);
  await seedNonDemoSession(page);

  const toggle = page.getByTestId('horizontal-deviation-toggle');
  await expect(toggle).toBeEnabled();
  await toggle.check();
  await expect(page.getByTestId('horizontal-deviation-sector')).toHaveValue('Norte');
  await expect.poll(() => intercepted.some((request) => request.includes(`/meshes/${topoId}/horizontal-deviation`))).toBe(true);
  await expect(page.locator('[data-slot="horizontal-deviation-legend"]')).toBeVisible();

  const canvas = page.locator('[data-slot="mesh-3d-viewer"] canvas');
  await expect(canvas).toBeVisible();
  await expect.poll(() => canvas.evaluate((element) => {
    const canvasElement = element as HTMLCanvasElement;
    const gl = canvasElement.getContext('webgl2') ?? canvasElement.getContext('webgl');
    return !!gl && gl.getParameter(gl.VERSION) !== null;
  })).toBe(true);
  await page.locator('[data-slot="mesh-3d-viewer"]').screenshot({ path: '../docs/design/horizontal-deviation-3d.png' });
});

test('processed sections without a sector name enable the heatmap and keep the empty sector in requests', async ({ page }) => {
  const intercepted = await mockApi(page, '');
  await seedNonDemoSession(page);
  const toggle = page.getByTestId('horizontal-deviation-toggle');
  await expect(toggle).toBeEnabled();
  const request = page.waitForRequest((item) => item.url().includes(`/meshes/${topoId}/horizontal-deviation`));
  await toggle.check();
  await expect(page.getByTestId('horizontal-deviation-sector')).toHaveValue('');
  await expect(page.getByTestId('horizontal-deviation-sector').locator('option:checked')).toHaveText('Sin sector');
  expect(new URL((await request).url()).searchParams.get('sector')).toBe('');
  await expect(page.getByTestId('horizontal-deviation-bench').locator('option')).toHaveCount(3);
  await expect(page.locator('[data-slot="horizontal-deviation-legend"]')).toBeVisible();
  expect(intercepted.some((item) => item.includes('/horizontal-deviation'))).toBe(true);
});

test('real surfaces enable the heatmap after replacing demo surfaces', async ({ page }) => {
  await mockApi(page);
  await seedNonDemoSession(page);
  await page.evaluate(async () => {
    const { useSession } = await import('/conciliacion-geo-v02/src/stores/session.ts');
    useSession.setState({ demoMode: true });
  });
  const toggle = page.getByTestId('horizontal-deviation-toggle');
  await expect(toggle).toBeEnabled();
  await toggle.check();
  await expect(page.locator('[data-slot="horizontal-deviation-legend"]')).toBeVisible();
});

test('profile shows measured h-from-toe samples at equal elevation and keeps B2 inspector selection', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  const intercepted = await mockApi(page);
  await seedNonDemoSession(page);
  await page.getByRole('button', { name: 'Perfiles', exact: true }).click();
  await page.getByRole('button', { name: 'Detalle', exact: true }).click();
  await page.locator('#profile-section-select').selectOption('sec-1');

  const chart = page.locator('[data-slot="profile-chart"] .js-plotly-plot');
  await expect(chart).toBeVisible();
  const profileState = await chart.evaluate((element) => {
    const plot = element as HTMLElement & {
      _fullData: Array<{ meta?: { horizontalDeviation?: boolean; profileViewRole?: string }; x: number[]; y: number[] }>;
      _fullLayout: { xaxis: { _m: number }; yaxis: { _m: number }; annotations: Array<{ text?: string }> };
    };
    const deviation = plot._fullData.filter((trace) => trace.meta?.horizontalDeviation);
    const sample = plot._fullData.find((trace) => trace.meta?.profileViewRole === 'horizontal-deviation-sample');
    return {
      hasDeviationTrace: deviation.length > 0,
      scaleError: Math.abs(Math.abs(plot._fullLayout.yaxis._m / plot._fullLayout.xaxis._m) - 1),
      sampleHeights: plot._fullLayout.annotations?.map((annotation) => annotation.text ?? '').filter((text) => text.includes('h desde pata')) ?? [],
      connectorY: sample?.y ?? [],
    };
  });
  expect(profileState.hasDeviationTrace).toBe(true);
  expect(profileState.scaleError).toBeLessThan(0.001);

  const plotted = await chart.evaluate((element) => {
    const plot = element as HTMLElement & {
      _fullData: Array<{ meta?: { profileViewRole?: string }; x: number[]; y: number[] }>;
      _fullLayout: { xaxis: { _m: number }; yaxis: { _m: number }; annotations: Array<{ text?: string }> };
    };
    const samples = plot._fullData.filter((trace) => trace.meta?.profileViewRole === 'horizontal-deviation-sample');
    return {
      connectorY: samples.flatMap((sample) => sample.y),
      annotations: plot._fullLayout.annotations?.map((annotation) => annotation.text ?? '') ?? [],
    };
  });
  expect(plotted.connectorY).toEqual([88, 88, 92.5, 92.5, 97, 97]);
  expect(plotted.annotations.join(' ')).toContain('h 3.0 m');
  expect(plotted.annotations.join(' ')).toContain('h 7.5 m');
  expect(plotted.annotations.join(' ')).toContain('h 12.0 m');
  await expect.poll(() => intercepted.some((request) => request.endsWith('/process/profiles/sec-1'))).toBe(true);
  await chart.screenshot({ path: '../docs/design/horizontal-deviation-profile.png' });

  const markerTrace = chart.locator('.scatterlayer g.trace').last();
  const b2Marker = markerTrace.locator('.points path.point').nth(1);
  await expect(b2Marker).toBeVisible();
  await b2Marker.click({ force: true });
  await expect(page.locator('[data-slot="bench-inspector"]')).toContainText('Banco 02');
  await page.locator('[data-slot="bench-inspector"]').screenshot({ path: '../docs/design/horizontal-deviation-b2-inspector.png' });
});
