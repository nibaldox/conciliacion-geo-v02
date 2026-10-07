import { test, expect } from '@playwright/test';

const inspect = {
  upload_id: 'e2e-dxf-stage',
  filename: 'bench-surface.dxf',
  type: 'design',
  expires_at: 1791028800,
  declared_units: 6,
  layers: [{ name: 'BENCHES', n_faces: 4, n_vertices: 8, bounds: { xmin: 0, xmax: 100, ymin: 0, ymax: 80, zmin: 10, zmax: 40 }, entity_counts: { '3DFACE': 4 } }],
  entity_counts: { '3DFACE': 4 },
  warnings: ['SURFACES_NO_XY_OVERLAP'],
  importer_version: '1.0',
};

test('DXF upload reviews units and layers, then shows the import report', async ({ page }) => {
  await page.route('**/api/v1/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/settings')) return route.fulfill({ json: { process: { resolution: 0.1, face_threshold: 40, berm_threshold: 20 }, tolerances: {} } });
    if (url.pathname.endsWith('/dxf/inspect')) return route.fulfill({ json: inspect });
    if (url.pathname.endsWith('/dxf/confirm')) return route.fulfill({ json: {
      mesh_id: 'dxf-design', n_vertices: 8, n_faces: 4, bounds: {},
      import_report: { selected_layers: ['BENCHES'], declared_units: 6, confirmed_units: 6, scale_factor: 1, importer_version: '1.0', entity_counts: { '3DFACE': 4 }, warnings: ['SURFACES_NO_XY_OVERLAP'], discarded_faces: 0 },
    } });
    if (url.pathname.endsWith('/dxf-design/info')) return route.fulfill({ json: { id: 'dxf-design', type: 'design', n_vertices: 8, n_faces: 4, bounds: { xmin: 0, xmax: 100, ymin: 0, ymax: 80 }, filename: 'bench-surface.dxf', uploaded_at: '2026-10-03' } });
    if (route.request().method() === 'DELETE') return route.fulfill({ json: { message: 'cancelled' } });
    return route.fulfill({ json: {} });
  });

  await page.goto('/conciliacion-geo-v02/');
  const designZone = page.locator('[data-slot="mesh-upload-zone"]').first();
  await designZone.locator('input[type="file"]').setInputFiles({ name: 'bench-surface.dxf', mimeType: 'application/dxf', buffer: Buffer.from('0') });
  const dialog = page.getByRole('dialog', { name: 'Revisar DXF para Diseño' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/Factor de conversión a metros: 1/)).toBeVisible();
  await expect(dialog.getByRole('checkbox', { name: /BENCHES/ })).toBeChecked();
  await expect(dialog.getByText(/La extensión horizontal de esta superficie/)).toBeVisible();
  const confirmRequest = page.waitForRequest((request) => request.url().endsWith('/meshes/dxf/confirm') && request.method() === 'POST');
  await dialog.getByRole('button', { name: 'Confirmar importación' }).click();
  expect((await confirmRequest).postDataJSON()).toEqual({ upload_id: 'e2e-dxf-stage', layers: ['BENCHES'], units: 6 });
  await expect(page.getByText('bench-surface.dxf')).toBeVisible();
  await expect(page.getByText('Capas importadas: BENCHES')).toBeVisible();
  await expect(page.getByText(/no se cruza con la otra superficie/)).toBeVisible();
});
