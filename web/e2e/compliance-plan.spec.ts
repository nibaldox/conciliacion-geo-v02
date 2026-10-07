import { test, expect } from '@playwright/test';

test('summary plan shows topography and processed profiles with canonical compliance colors', async ({ page }) => {
  await page.route('**/demo/precomputed.json', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    for (const row of data.comparisons) {
      if (row.section === 'DEMO-S01') row.bench_score = 70;
      if (row.section === 'DEMO-S02') row.bench_score = 69.9;
      if (row.section === 'DEMO-S03') row.type = 'EXTRA';
    }
    await route.fulfill({ json: data });
  });
  await page.route('**/meshes/__demo_design__/breaklines', (route) => route.fulfill({ json: { lines: [] } }));
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto('/conciliacion-geo-v02/');
  await page.getByRole('button', { name: /Probar con datos/i }).click();
  await page.getByRole('button', { name: 'Salir del demo' }).waitFor();
  await page.locator('canvas').waitFor();
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  const plan = page.locator('[data-slot="compliance-plan-view"]');
  await expect(plan.locator('image')).toHaveAttribute('href', /^data:image\/png;base64,/);
  await expect(plan.locator('polyline')).toHaveCount(5);
  await expect(plan.locator('[data-section-name="DEMO-S01"]')).toHaveAttribute('data-status', 'cumple');
  await expect(plan.locator('[data-section-name="DEMO-S02"]')).toHaveAttribute('data-status', 'no_cumple');
  await expect(plan.locator('[data-section-name="DEMO-S03"]')).toHaveAttribute('data-status', 'unknown');
  const linePoints = await plan.locator('[data-section-name="DEMO-S01"] polyline').getAttribute('points');
  const points = linePoints!.split(' ').map((point) => point.split(',').map(Number));
  expect(points[0]![0]).toBeCloseTo(points.at(-1)![0]!);
  expect(points[0]![1]).toBeGreaterThan(points.at(-1)![1]!);
  await plan.scrollIntoViewIfNeeded();
  await page.locator('[data-slot="theme-toggle"]').click();
  await expect(plan.locator('polyline')).toHaveCount(5);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(plan.locator('svg')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('clustered profiles open at the evaluated area and keep their labels separate', async ({ page }) => {
  await page.route('**/demo/precomputed.json', async (route) => {
    const response = await route.fetch();
    const data = await response.json();
    const base = data.sections[0];
    data.sections = Array.from({ length: 32 }, (_, index) => ({ ...base, section_name: `SECTOR-${String(index + 1).padStart(2, '0')}`, origin: [240 + index / 2, 250], topo_profile: { distances: [-20, 0, 20], elevations: [100, 110, 120] } }));
    const comparison = data.comparisons.find((row: { type: string }) => row.type === 'MATCH');
    data.comparisons = data.sections.map((section: { section_name: string }) => ({ ...comparison, section: section.section_name, bench_score: 70, section_score: 70 }));
    await route.fulfill({ json: data });
  });
  await page.route('**/meshes/__demo_design__/breaklines', (route) => route.fulfill({ json: { lines: [] } }));
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.goto('/conciliacion-geo-v02/');
  await page.getByRole('button', { name: /Probar con datos/i }).click();
  await page.getByRole('button', { name: 'Salir del demo' }).waitFor();
  await page.locator('canvas').waitFor();
  await page.getByRole('button', { name: 'Dashboard', exact: true }).click();
  const plan = page.locator('[data-slot="compliance-plan-view"]');
  await expect(plan.locator('polyline')).toHaveCount(32);
  const focused = (await plan.getAttribute('data-extent'))!.split(',').map(Number);
  expect(focused[2]! - focused[0]!).toBeLessThan(100);
  expect(focused[3]! - focused[1]!).toBeLessThan(100);
  const labels = await plan.locator('[data-section-name] text').evaluateAll((elements) => elements.map((element) => {
    const rect = element.getBoundingClientRect();
    return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom };
  }));
  for (let i = 0; i < labels.length; i++) for (let j = i + 1; j < labels.length; j++) {
    const a = labels[i]!, b = labels[j]!;
    expect(a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top).toBe(true);
  }
  await plan.getByRole('button', { name: 'Superficie completa', exact: true }).click();
  const full = (await plan.getAttribute('data-extent'))!.split(',').map(Number);
  expect(full[2]! - full[0]!).toBeGreaterThan(400);
  await plan.getByRole('button', { name: 'Zona evaluada', exact: true }).click();
  expect(await plan.getAttribute('data-extent')).toBe(focused.join(','));
});

test('profile plan thumbnail follows the active profile without changing its selection', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.route('**/meshes/__demo_design__/breaklines', (route) => route.fulfill({ json: { lines: [] } }));
  await page.goto('/conciliacion-geo-v02/');
  await page.getByRole('button', { name: /Probar con datos/i }).click();
  await page.getByRole('button', { name: 'Salir del demo' }).waitFor();
  await page.locator('canvas').waitFor();
  await page.getByRole('button', { name: 'Perfiles', exact: true }).click();
  await page.locator('button').filter({ has: page.locator('.js-plotly-plot') }).first().click();
  const thumbnail = page.locator('[data-slot="profile-plan-thumbnail"]');
  await expect(thumbnail.locator('image')).toHaveAttribute('href', /^data:image\/png;base64,/);
  await expect(thumbnail.locator('polyline[data-active="true"]')).toHaveCount(1);
  const size = await thumbnail.locator('svg').boundingBox();
  expect(size!.width).toBeGreaterThan(350);
  expect(size!.height).toBeGreaterThan(300);
  const previous = await thumbnail.getAttribute('data-active-section');
  await page.getByTestId('nav-next').click();
  await expect(thumbnail).not.toHaveAttribute('data-active-section', previous!);
  const active = await thumbnail.getAttribute('data-active-section');
  await expect(thumbnail.locator('polyline[data-active="true"]')).toHaveAttribute('data-section-id', active!);
  await page.locator('[data-slot="theme-toggle"]').click();
  await expect(thumbnail).toHaveAttribute('data-active-section', active!);
  await page.setViewportSize({ width: 390, height: 844 });
  await thumbnail.scrollIntoViewIfNeeded();
  await expect(thumbnail.locator('svg')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
