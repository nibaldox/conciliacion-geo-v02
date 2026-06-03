import { test, expect } from '@playwright/test';

test.describe('Conciliación Geotécnica App', () => {
  test('loads the app and shows step wizard', async ({ page }) => {
    await page.goto('/');

    // Check title
    await expect(page).toHaveTitle(/Conciliación/);

    // Check header
    await expect(page.getByText('Conciliación Geotécnica')).toBeVisible();

    // Check step navigation
    await expect(page.getByText('Cargar Superficies')).toBeVisible();

    // Check current step is Step 1
    await expect(page.getByText('Paso 1:')).toBeVisible();
  });

  test('step navigation shows all 4 steps', async ({ page }) => {
    await page.goto('/');

    const steps = ['Cargar Superficies', 'Definir Secciones', 'Análisis', 'Resultados'];
    for (const step of steps) {
      await expect(page.getByText(step)).toBeVisible();
    }
  });

  test('upload zones are visible on step 1', async ({ page }) => {
    await page.goto('/');

    await expect(page.getByText('Diseño')).toBeVisible();
    await expect(page.getByText('Topografía')).toBeVisible();
  });

  test('API health endpoint responds', async ({ request }) => {
    const response = await request.get('http://localhost:8000/api/v1/health');
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data.status).toBe('ok');
  });
});
