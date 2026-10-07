import { test, expect } from '@playwright/test';

test('bench selection recalculates the whole summary and the plan scores', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.route('**/demo/precomputed.json', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    for (const row of data.comparisons) {
      row.section_score = 50;
      row.bench_score = row.bench_num === 1 ? 100 : 0;
      row.height_status = row.angle_status = row.berm_status = row.bench_num === 1 ? 'CUMPLE' : 'NO CUMPLE';
      row.height_dev = row.bench_num;
      if (row.section === 'DEMO-S05' && row.bench_num === 1) row.bench_num = 9;
    }
    await route.fulfill({ json: data });
  });
  await page.route('**/meshes/__demo_design__/breaklines', (route) => route.fulfill({ json: { lines: [] } }));
  await page.goto('/conciliacion-geo-v02/');
  await page.getByRole('button', { name: /Probar con datos/i }).click();
  await page.getByRole('button', { name: 'Salir del demo' }).waitFor();
  await page.locator('canvas').waitFor();
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  const filter = page.locator('[data-slot="dashboard-bench-filter"]');
  const plan = page.locator('[data-slot="compliance-plan-view"]');
  await filter.locator('summary').click();
  await filter.getByRole('checkbox', { name: 'Banco 1', exact: true }).check();
  await expect(page.locator('dl').filter({ hasText: 'Score Ponderado Global' }).locator('dd').first()).toHaveText('100.0');
  await expect(plan.locator('polyline')).toHaveCount(4);
  await expect(plan.locator('[data-section-name="DEMO-S01"]')).toHaveAttribute('data-score', '100');
  await expect(plan.locator('[data-section-name="DEMO-S01"]')).toHaveAttribute('data-status', 'cumple');
  await expect.poll(() => page.locator('.js-plotly-plot').first().evaluate((element) => (element as HTMLElement & { _fullData?: { y: number[] }[] })._fullData?.[0]?.y)).toEqual([4, 4, 4]);
  await filter.getByRole('checkbox', { name: 'Banco 2', exact: true }).check();
  await expect(page.locator('dl').filter({ hasText: 'Score Ponderado Global' }).locator('dd').first()).toHaveText('40.0');
  await expect(plan.locator('polyline')).toHaveCount(5);
  await expect(plan.locator('[data-section-name="DEMO-S05"]')).toHaveAttribute('data-score', '0');
  await expect(plan.locator('[data-section-name="DEMO-S01"]')).toHaveAttribute('data-score', '50');
  await filter.getByRole('button', { name: 'Restablecer', exact: true }).click();
  await expect(filter.locator('summary')).toContainText('Todos los bancos');
  await expect(plan.locator('[data-section-name="DEMO-S05"]')).toHaveAttribute('data-score', '50');
  await page.setViewportSize({ width: 390, height: 844 });
  await filter.scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('blast CSV chooser works before confirmation and submits only explicit confirmed geometry', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    const headers = { 'x-session-id': 'review-blast-session' };
    let json: unknown = {};
    if (url.pathname.endsWith('/settings')) json = { process: { resolution: 0.1, face_threshold: 40, berm_threshold: 20 }, tolerances: { bench_height: { neg: 1, pos: 1.5 }, face_angle: { neg: 5, pos: 5 }, berm_width: { min: 6 }, inter_ramp_angle: { neg: 3, pos: 2 }, overall_angle: { neg: 2, pos: 2 } } };
    if (url.pathname.endsWith('/sections')) json = [{ id: 'review-section', name: 'S-01', origin: [0, 0], azimuth: 0, length: 100, sector: 'Principal' }];
    if (url.pathname.endsWith('/process/status')) json = { status: 'complete', progress: 100 };
    if (url.pathname.endsWith('/vertices')) json = { x: [0, 100, 0], y: [0, 0, 100], z: [0, 0, 0], faces: [[0, 1, 2]] };
    if (url.pathname.endsWith('/breaklines')) json = { lines: [] };
    if (url.pathname.endsWith('/info')) json = { filename: 'review.stl', bounds: { min_x: 0, max_x: 100, min_y: 0, max_y: 100, min_z: 0, max_z: 0 }, n_vertices: 3, n_faces: 1 };
    if (url.pathname.endsWith('/blast-correlation')) json = { rows: [], carga: [], descarga: [] };
    if (url.pathname.endsWith('/holes')) json = { session_id: 'review-blast-session', holes: [] };
    if (url.pathname.endsWith('/blast/upload')) json = { n_holes: 1, n_rows_skipped: 0, blocking_errors: [], rejected_rows: [], event_warnings: [] };
    await route.fulfill({ json, headers });
  });
  await page.goto('/conciliacion-geo-v02/');
  await page.evaluate(async () => {
    const { useSession } = await import('/conciliacion-geo-v02/src/stores/session.ts');
    useSession.setState({ designMeshId: 'review-design', topoMeshId: 'review-topo', activeWorkspaceView: 'blast' });
  });
  await page.getByRole('button', { name: 'Tronadura', exact: true }).click();
  const uploader = page.getByTestId('blast-uploader');
  const chooser = page.waitForEvent('filechooser');
  await page.getByTestId('blast-file-picker').focus();
  await page.keyboard.press('Enter');
  await (await chooser).setFiles({ name: 'pozos.csv', mimeType: 'text/csv', buffer: Buffer.from('Latitud_Geo,Longitud_Geo,Inclinacion_real,Azimuth_real\n700000,7200000,0,0') });
  await expect(page.getByTestId('geometry-contract-form')).toHaveAttribute('open');
  await expect(page.getByTestId('blast-upload-submit')).toBeDisabled();
  await expect(uploader).toContainText('pozos.csv');
  await page.getByTestId('incl-source-column').fill('Inclinacion_real');
  await page.getByTestId('az-source-column').fill('Azimuth_real');
  await page.getByTestId('incl-convention').selectOption('FROM_VERTICAL');
  await page.getByTestId('incl-sign').selectOption('ABSOLUTE_VALUE');
  await page.getByTestId('incl-unit').selectOption('DEGREES');
  await page.getByTestId('az-convention').selectOption('CLOCKWISE_FROM_NORTH');
  await page.getByTestId('az-unit').selectOption('RADIANS');
  await expect(page.getByTestId('blast-upload-submit')).toBeDisabled();
  await page.getByTestId('geometry-confirmed').check();
  await expect(page.getByTestId('blast-upload-submit')).toBeEnabled();
  const request = page.waitForRequest((request) => request.url().endsWith('/blast/upload') && request.method() === 'POST');
  await page.getByTestId('blast-upload-submit').click();
  const body = (await request).postData()!;
  for (const [key, value] of Object.entries({ session_id: 'review-blast-session', geometry_configuration_version: '2.0', geometry_user_confirmed: 'true', inclination_source_column: 'Inclinacion_real', azimuth_source_column: 'Azimuth_real', inclination_convention: 'FROM_VERTICAL', inclination_sign_convention: 'ABSOLUTE_VALUE', inclination_unit: 'DEGREES', azimuth_convention: 'CLOCKWISE_FROM_NORTH', azimuth_unit: 'RADIANS' })) {
    expect(body).toContain(`name="${key}"\r\n\r\n${value}`);
  }
  expect(body).not.toContain('name="bench_height_m"');
  await expect(page.getByTestId('blast-upload-summary')).toBeVisible();
  const again = page.waitForEvent('filechooser');
  await page.getByTestId('blast-file-picker').click();
  await (await again).setFiles({ name: 'pozos.csv', mimeType: 'text/csv', buffer: Buffer.from('Latitud_Geo,Longitud_Geo\n700000,7200000') });
  await expect(page.getByTestId('geometry-confirmed')).not.toBeChecked();
  await expect(page.getByTestId('blast-upload-submit')).toBeDisabled();
});
