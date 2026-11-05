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

  test('side panel lists the workflow steps and keeps surfaces step expanded', async ({ page }) => {
    await page.goto('/');

    for (const step of ['surfaces', 'sections', 'parameters', 'process']) {
      await expect(page.locator(`#workflow-step-${step}`)).toBeVisible();
    }
    await expect(page.locator('#workflow-step-surfaces')).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByRole('heading', { name: 'Flujo de trabajo' })).toBeVisible();
    await expect(page.locator('[data-slot="left-sidebar"] [data-slot="views-toolbar"]')).toHaveCount(0);

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
