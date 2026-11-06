import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';
import { installFontFixtures } from './fixtures/fontFixtures.ts';

const demo = JSON.parse(fs.readFileSync(path.resolve('public/demo/precomputed.json'), 'utf8'));
const section = { id: 'review-section', name: 'S-01', origin: [700000, 7200000], azimuth: 0, length: 200, length_up: 100, length_down: 100, sector: 'Norte' };
const initialSettings = { process: { resolution: 0.1, face_threshold: 40, berm_threshold: 20 }, tolerances: { bench_height: { neg: 1, pos: 1.5 }, face_angle: { neg: 5, pos: 5 }, berm_width: { min: 6 }, inter_ramp_angle: { neg: 3, pos: 2 }, overall_angle: { neg: 2, pos: 2 } } };

async function prepare(page: Page) {
  let settings = structuredClone(initialSettings);
  await installFontFixtures(page);
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/settings')) {
      if (route.request().method() === 'PUT') settings = route.request().postDataJSON();
      return route.fulfill({ json: settings });
    }
    if (url.pathname.endsWith('/sections')) return route.fulfill({ json: [section] });
    if (url.pathname.endsWith('/status')) return route.fulfill({ json: { status: 'idle' } });
    if (url.pathname.endsWith('/info')) return route.fulfill({ json: { id: 'review-design', type: 'design', n_vertices: 3080, n_faces: 6000, bounds: {}, filename: 'review.stl', uploaded_at: '2026-09-30' } });
    if (url.pathname.endsWith('/vertices')) return route.fulfill({ json: demo.vertices.topo });
    if (url.pathname.endsWith('/breaklines')) return route.fulfill({ json: { lines: [{ elevation: 100, segments: [[[700000, 7200000, 100], [700020, 7200010, 100], [700040, 7200020, 100]]] }] } });
    if (url.pathname.endsWith('/process/results')) return route.fulfill({ json: [] });
    return route.fulfill({ json: {} });
  });
  await page.goto('/conciliacion-geo-v02/');
  await page.evaluate(async () => {
    const { useSession } = await import('/conciliacion-geo-v02/src/stores/session.ts');
    useSession.setState({ designMeshId: 'review-design', topoMeshId: 'review-topo', sidebarCollapsed: false });
  });
  await page.locator('canvas').waitFor();
}

async function openStep(page: Page, step: 'surfaces' | 'sections' | 'parameters' | 'process') {
  const button = page.locator(`#workflow-step-${step}`);
  if (await button.getAttribute('aria-expanded') !== 'true') await button.click();
  await expect(button).toHaveAttribute('aria-expanded', 'true');
}

async function expectNoScroll(page: Page) {
  expect(await page.locator('[data-slot="project-controls"]').evaluate((element) => element.scrollHeight - element.clientHeight)).toBeLessThanOrEqual(1);
}

test('all entry stages fit compact windows and remain accessible in both themes', async ({ page }) => {
  await prepare(page);
  for (const size of [{ width: 1366, height: 768 }, { width: 1280, height: 720 }, { width: 1024, height: 640 }]) {
    await page.setViewportSize(size);
    for (const panel of ['surfaces', 'sections', 'parameters', 'process'] as const) {
      await openStep(page, panel);
      if (panel === 'sections') {
        for (const tab of ['Por curvas', 'Archivo']) {
          await page.getByRole('button', { name: tab, exact: true }).click();
          await expectNoScroll(page);
        }
      } else await expectNoScroll(page);
    }
  }
  await page.locator('[data-slot="theme-toggle"]').click();
  await openStep(page, 'parameters');
  await expect(page.getByLabel('Paso (m)', { exact: true })).toBeVisible();
  await page.getByText('Ángulos globales', { exact: true }).click();
  await expect(page.getByLabel(/Tolerancia negativa: Ángulo inter-rampa/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('file selection by keyboard submits the complete section geometry and permits editing', async ({ page }) => {
  await prepare(page);
  await page.setViewportSize({ width: 1280, height: 720 });
  await openStep(page, 'sections');
  await page.getByRole('button', { name: 'Archivo', exact: true }).click();
  const chooser = page.waitForEvent('filechooser');
  await page.getByRole('button', { name: 'Seleccionar archivo', exact: true }).focus();
  await page.keyboard.press('Enter');
  await (await chooser).setFiles({ name: 'crest.csv', mimeType: 'text/csv', buffer: Buffer.from('x,y,z\n700000,7200000,100\n700020,7200010,100') });
  await page.getByLabel('Sector', { exact: true }).fill('Zona Este');
  await page.getByLabel('Espaciamiento (m)', { exact: true }).fill('12');
  await page.getByLabel('Superior (m)', { exact: true }).fill('80');
  await page.getByLabel('Inferior (m)', { exact: true }).fill('120');
  await page.getByLabel('Método de Azimuth').selectOption('local_slope');
  await expectNoScroll(page);
  const request = page.waitForRequest((request) => request.url().endsWith('/sections/from-file') && request.method() === 'POST');
  await page.getByRole('button', { name: 'Generar desde Archivo', exact: true }).click();
  const body = (await request).postData()!;
  for (const [key, value] of Object.entries({ spacing: '12', length: '200', length_up: '80', length_down: '120', sector: 'Zona Este', az_mode: 'local_slope' })) {
    expect(body).toContain(`name="${key}"\r\n\r\n${value}`);
  }
  await page.getByText('Secciones existentes', { exact: true }).click();
  await page.getByRole('button', { name: 'Editar', exact: true }).click();
  await page.getByLabel('Superior (m)', { exact: true }).last().fill('90');
  const edited = page.waitForRequest((request) => request.url().endsWith('/sections/review-section') && request.method() === 'PUT');
  await page.getByRole('button', { name: 'Guardar', exact: true }).click();
  expect((await edited).postDataJSON()).toMatchObject({ name: 'S-01', origin: [700000, 7200000], azimuth: 0, length_up: 90, length_down: 100, length: 190, sector: 'Norte' });
});

test('curve selection and settings preserve geometry and tolerance values', async ({ page }) => {
  await prepare(page);
  await page.setViewportSize({ width: 1280, height: 720 });
  await openStep(page, 'sections');
  const anchors = await page.evaluate(async () => {
    const { useSession } = await import('/conciliacion-geo-v02/src/stores/session.ts');
    const { createCurveAnchor } = await import('/conciliacion-geo-v02/src/components/sections/curveAnchorGeometry.ts');
    const deadline = Date.now() + 10000;
    while (Date.now() < deadline) {
      const current = useSession.getState();
      if (current.curveSelection.context && current.mapClickHandler) break;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    const state = useSession.getState();
    const context = state.curveSelection.context;
    if (!context) throw new Error('state.curveSelection.context missing (SectionCurveForm snapshot not dispatched)');
    const click = state.mapClickHandler;
    if (!click) throw new Error('state.mapClickHandler missing (SectionCurveForm not mounted)');
    const points = [[700000, 7200000, 100], [700020, 7200010, 100], [700040, 7200020, 100]];
    const start = createCurveAnchor({ context, curveId: '0-0', points, segmentIndex: 0, t: 0 });
    const end = createCurveAnchor({ context, curveId: '0-0', points, segmentIndex: 1, t: 1 });
    if (!start || !end) throw new Error('createCurveAnchor returned null for start/end');
    click(start);
    click(start);
    click(end);
    const after = useSession.getState().curveSelection;
    return {
      start: { segmentIndex: start.segmentIndex, t: start.t, position: start.position, chainage: start.chainage },
      end: { segmentIndex: end.segmentIndex, t: end.t, position: end.position, chainage: end.chainage },
      selection: {
        curveId: after.curveId,
        rejection: after.rejection,
        start: after.start ? { segmentIndex: after.start.segmentIndex, t: after.start.t, position: after.start.position, chainage: after.start.chainage } : null,
        end: after.end ? { segmentIndex: after.end.segmentIndex, t: after.end.t, position: after.end.position, chainage: after.end.chainage } : null,
      },
    };
  });
  expect(anchors.selection.curveId).toBe('0-0');
  expect(anchors.selection.rejection).toBeNull();
  expect(anchors.selection.start?.position).toEqual([700000, 7200000, 100]);
  expect(anchors.selection.end?.position).toEqual([700040, 7200020, 100]);
  await expect(page.getByRole('button', { name: 'Generar perfiles', exact: true })).toBeEnabled();
  await expectNoScroll(page);
  const controlsBox = await page.locator('[data-slot="project-controls"]').boundingBox();
  const generate = page.getByRole('button', { name: 'Generar perfiles', exact: true });
  const reset = page.getByRole('button', { name: 'RESTABLECER SELECCIÓN', exact: true });
  for (const size of [{ width: 1280, height: 640 }, { width: 1280, height: 719 }, { width: 1280, height: 720 }, { width: 1280, height: 721 }, { width: 1280, height: 768 }, { width: 1280, height: 769 }, { width: 1280, height: 800 }, { width: 1280, height: 801 }, { width: 1280, height: 850 }, { width: 1280, height: 851 }, { width: 1280, height: 900 }, { width: 1280, height: 1000 }, { width: 1280, height: 1001 }]) {
    await page.setViewportSize(size);
    await expectNoScroll(page);
    await expect(generate).toBeEnabled();
    await expect(reset).toBeVisible();
    const toggleHeights = await page.locator('[data-slot="project-controls"] button[aria-controls^="workflow-step-"]').evaluateAll((elements) => elements.map((element) => element.getBoundingClientRect().height));
    for (const toggleHeight of toggleHeights) {
      expect(toggleHeight, `step toggle height at ${size.width}x${size.height}`).toBeGreaterThanOrEqual(28);
    }
    for (const action of [generate, reset]) {
      expect(await action.boundingBox(), `generate/reset box present at ${size.width}x${size.height}`).not.toBeNull();
      const box = await action.evaluate((element) => {
        const { top, bottom, left, right, height } = element.getBoundingClientRect();
        const controls = element.closest('[data-slot="project-controls"]')!;
        const panel = element.closest('[role="region"][id^="workflow-step-"]');
        const clip = controls.getBoundingClientRect();
        const panelClip = panel ? panel.getBoundingClientRect() : clip;
        return {
          top, bottom, left, right, height,
          clipTop: Math.max(clip.top, panelClip.top),
          clipBottom: Math.min(clip.bottom, panelClip.bottom),
          clipLeft: Math.max(clip.left, panelClip.left),
          clipRight: Math.min(clip.right, panelClip.right),
          textClipX: element.scrollWidth - element.clientWidth,
          textClipY: element.scrollHeight - element.clientHeight,
        };
      });
      expect(box.height, `generate/reset touch height at ${size.width}x${size.height}`).toBeGreaterThanOrEqual(28);
      expect(box.top, `generate/reset unclipped top at ${size.width}x${size.height}`).toBeGreaterThanOrEqual(box.clipTop);
      expect(box.bottom, `generate/reset unclipped bottom at ${size.width}x${size.height}`).toBeLessThanOrEqual(box.clipBottom);
      expect(box.left, `generate/reset unclipped left at ${size.width}x${size.height}`).toBeGreaterThanOrEqual(box.clipLeft);
      expect(box.right, `generate/reset unclipped right at ${size.width}x${size.height}`).toBeLessThanOrEqual(box.clipRight);
      expect(box.textClipX, `generate/reset label clipped horizontally at ${size.width}x${size.height}`).toBeLessThanOrEqual(1);
      expect(box.textClipY, `generate/reset label clipped vertically at ${size.width}x${size.height}`).toBeLessThanOrEqual(1);
    }
    expect(controlsBox && controlsBox.width, 'controls width stays positive').toBeGreaterThan(0);
  }
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.getByLabel('Superior (m)', { exact: true }).fill('70');
  await page.getByLabel('Inferior (m)', { exact: true }).fill('130');
  const generated = page.waitForRequest((request) => request.url().endsWith('/sections/curve') && request.method() === 'POST');
  await page.getByRole('button', { name: 'Generar perfiles', exact: true }).click();
  const generatedBody: { points: number[][] } = (await generated).postDataJSON();
  expect(generatedBody.points).toHaveLength(3);
  for (const point of generatedBody.points) expect(point).toHaveLength(2);
  expect(generatedBody).toMatchObject({ points: [[700000, 7200000], [700020, 7200010], [700040, 7200020]], spacing: 10, length: 200, length_up: 70, length_down: 130 });
  await openStep(page, 'parameters');
  await page.getByLabel('Paso (m)', { exact: true }).fill('0.2');
  const saved = page.waitForRequest((request) => request.url().endsWith('/settings') && request.method() === 'PUT');
  await page.getByRole('button', { name: 'Guardar Parámetros', exact: true }).click();
  expect((await saved).postDataJSON()).toMatchObject({ process: { resolution: 0.2, face_threshold: 40, berm_threshold: 20 }, tolerances: initialSettings.tolerances });
  const tolerance = page.waitForRequest((request) => request.url().endsWith('/settings') && request.method() === 'PUT');
  await page.getByLabel('Tolerancia negativa: Altura de banco (m)', { exact: true }).fill('2');
  expect((await tolerance).postDataJSON()).toMatchObject({ tolerances: { bench_height: { neg: 2, pos: 1.5 }, berm_width: { min: 6 } } });
});
