import { test, expect } from '@playwright/test';

test.describe('Conciliación Geotécnica App', () => {
  test('loads the app shell with brand header and 3D empty state', async ({ page }) => {
    await page.goto('/');

    await expect(page).toHaveTitle(/Conciliación/);

    await expect(page.getByRole('heading', { name: 'Conciliación Geotécnica', level: 1 })).toBeVisible();
    await expect(page.getByText('Diseño vs As-Built', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Nueva Sesión' })).toBeVisible();

    await expect(page.getByRole('heading', { name: 'Vista 3D', level: 2, exact: true })).toBeVisible();
    await expect(page.getByText('Cargue superficies para ver la vista 3D', { exact: true })).toBeVisible();
  });

  test('side panel lists current navigation and keeps surfaces section expanded', async ({ page }) => {
    await page.goto('/');

    const navLabels = [
      'Cargar Superficies',
      'Definir Secciones',
      'Parámetros de Procesamiento',
      'Análisis',
    ];
    for (const label of navLabels) {
      await expect(page.getByRole('button', { name: label })).toBeVisible();
    }

    const uploadZones = page.getByRole('button', { name: 'Cargar archivo' });
    await expect(uploadZones).toHaveCount(2);
    await expect(uploadZones.first()).toBeVisible();
    await expect(uploadZones.nth(1)).toBeVisible();
  });

  test('design and topography upload zones are accessible', async ({ page }) => {
    await page.goto('/');

    const uploadZones = page.getByRole('button', { name: 'Cargar archivo' });

    await expect(uploadZones.filter({ hasText: 'Diseño' })).toBeVisible();
    await expect(uploadZones.filter({ hasText: 'Topografía' })).toBeVisible();
  });

  test('API health endpoint responds', async ({ request }) => {
    const response = await request.get('http://localhost:8000/api/v1/health');
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.status).toBe('ok');
  });
});
