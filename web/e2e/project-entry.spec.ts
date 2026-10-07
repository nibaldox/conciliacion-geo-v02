import { test, expect, type Page } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const demo = JSON.parse(fs.readFileSync(path.resolve('public/demo/precomputed.json'), 'utf8'));
const section = { id: 'review-section', name: 'S-01', origin: [700000, 7200000], azimuth: 0, length: 200, length_up: 100, length_down: 100, sector: 'Norte' };
const initialSettings = { process: { resolution: 0.1, face_threshold: 40, berm_threshold: 20 }, tolerances: { bench_height: { neg: 1, pos: 1.5 }, face_angle: { neg: 5, pos: 5 }, berm_width: { min: 6 }, inter_ramp_angle: { neg: 3, pos: 2 }, overall_angle: { neg: 2, pos: 2 } } };

async function prepare(page: Page) {
  let settings = structuredClone(initialSettings);
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
    return route.fulfill({ json: {} });
  });
  await page.goto('/conciliacion-geo-v02/');
  await page.evaluate(async () => {
    const { useSession } = await import('/conciliacion-geo-v02/src/stores/session.ts');
    useSession.setState({ designMeshId: 'review-design', topoMeshId: 'review-topo', sidebarCollapsed: false });
  });
  await page.locator('canvas').waitFor();
}

async function expectNoScroll(page: Page) {
  expect(await page.locator('[data-slot="project-controls"]').evaluate((element) => element.scrollHeight - element.clientHeight)).toBeLessThanOrEqual(1);
}

test('all entry stages fit compact windows and remain accessible in both themes', async ({ page }) => {
  await prepare(page);
  for (const size of [{ width: 1366, height: 768 }, { width: 1280, height: 720 }, { width: 1024, height: 640 }]) {
    await page.setViewportSize(size);
    for (const panel of ['mallas', 'secciones', 'tolerancias', 'procesamiento']) {
      const button = page.locator(`[aria-controls="project-panel-${panel}"]`);
      if (await button.getAttribute('aria-expanded') !== 'true') await button.click();
      if (panel === 'secciones') {
        for (const tab of ['Por curvas', 'Archivo']) {
          await page.getByRole('button', { name: tab, exact: true }).click();
          await expectNoScroll(page);
        }
      } else await expectNoScroll(page);
    }
  }
  await page.locator('[data-slot="theme-toggle"]').click();
  await page.locator('[aria-controls="project-panel-tolerancias"]').click();
  await expect(page.getByLabel('Paso (m)', { exact: true })).toBeVisible();
  await page.getByText('Ángulos globales', { exact: true }).click();
  await expect(page.getByLabel(/Tolerancia negativa: Ángulo inter-rampa/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('file selection by keyboard submits the complete section geometry and permits editing', async ({ page }) => {
  await prepare(page);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.locator('[aria-controls="project-panel-secciones"]').click();
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
  await page.locator('[aria-controls="project-panel-secciones"]').click();
  await page.evaluate(async () => {
    const { useSession } = await import('/conciliacion-geo-v02/src/stores/session.ts');
    const click = useSession.getState().mapClickHandler!;
    click(700000, 7200000, '0-0');
    click(700000, 7200000, '0-0', 0);
    click(700040, 7200020, '0-0', 2);
  });
  await expect(page.getByRole('button', { name: 'Generar perfiles', exact: true })).toBeEnabled();
  await expectNoScroll(page);
  await page.getByLabel('Superior (m)', { exact: true }).fill('70');
  await page.getByLabel('Inferior (m)', { exact: true }).fill('130');
  const generated = page.waitForRequest((request) => request.url().endsWith('/sections/curve') && request.method() === 'POST');
  await page.getByRole('button', { name: 'Generar perfiles', exact: true }).click();
  expect((await generated).postDataJSON()).toMatchObject({ points: [[700000, 7200000, 100], [700020, 7200010, 100], [700040, 7200020, 100]], spacing: 10, length: 200, length_up: 70, length_down: 130 });
  await page.locator('[aria-controls="project-panel-tolerancias"]').click();
  await page.getByLabel('Paso (m)', { exact: true }).fill('0.2');
  const saved = page.waitForRequest((request) => request.url().endsWith('/settings') && request.method() === 'PUT');
  await page.getByRole('button', { name: 'Guardar Parámetros', exact: true }).click();
  expect((await saved).postDataJSON()).toMatchObject({ process: { resolution: 0.2, face_threshold: 40, berm_threshold: 20 }, tolerances: initialSettings.tolerances });
  const tolerance = page.waitForRequest((request) => request.url().endsWith('/settings') && request.method() === 'PUT');
  await page.getByLabel('Tolerancia negativa: Altura de banco (m)', { exact: true }).fill('2');
  expect((await tolerance).postDataJSON()).toMatchObject({ tolerances: { bench_height: { neg: 2, pos: 1.5 }, berm_width: { min: 6 } } });
});
