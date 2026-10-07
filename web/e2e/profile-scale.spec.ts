import { test, expect, type Locator } from '@playwright/test';

async function expectEqualScale(chart: Locator) {
  await expect.poll(() => chart.evaluate((element) => {
    const layout = (element as HTMLElement & {
      _fullLayout?: { xaxis: { _m: number }; yaxis: { _m: number } };
    })._fullLayout;
    if (!layout) return Infinity;
    return Math.abs(Math.abs(layout.yaxis._m / layout.xaxis._m) - 1);
  })).toBeLessThan(0.001);
}

test('profile retains equal distance and elevation scales through navigation, zoom and resizing', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1000 });
  await page.route('**/meshes/__demo_design__/breaklines', (route) => route.fulfill({ json: { lines: [] } }));
  await page.goto('/conciliacion-geo-v02/');
  await page.getByRole('button', { name: /Probar con datos/i }).click();
  await page.getByRole('button', { name: 'Salir del demo' }).waitFor();
  await page.locator('canvas').waitFor();
  await page.getByRole('button', { name: 'Perfiles', exact: true }).click();
  await page.locator('button').filter({ has: page.locator('.js-plotly-plot') }).first().click();
  const chart = page.locator('[data-slot="profile-chart"] .js-plotly-plot');
  await expectEqualScale(chart);
  await expect.poll(() => chart.evaluate((element) => {
    const plot = element as HTMLElement & {
      _fullData: { x: number[]; y: number[]; name: string }[];
      _fullLayout: { xaxis: { range: number[] }; yaxis: { range: number[] } };
    };
    const { xaxis, yaxis } = plot._fullLayout;
    return plot._fullData.filter((trace) => ['Diseño', 'Topografía'].includes(trace.name)).every((trace) =>
      trace.x.every((value) => value >= xaxis.range[0]! && value <= xaxis.range[1]!) &&
      trace.y.every((value) => value >= yaxis.range[0]! && value <= yaxis.range[1]!),
    );
  })).toBe(true);
  await chart.locator('[data-title="Ampliar"]').click();
  await expectEqualScale(chart);
  await chart.locator('[data-title="Reiniciar ejes"]').click();
  await expectEqualScale(chart);
  await page.getByTestId('nav-next').click();
  await expectEqualScale(chart);
  await page.locator('[data-slot="theme-toggle"]').click();
  await expectEqualScale(chart);
  await page.getByRole('button', { name: 'Contraer Panel' }).click();
  for (const width of [1024, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await expect.poll(() => chart.evaluate((element) => {
      const plot = element as HTMLElement & { _fullLayout: { width: number } };
      return Math.abs(plot._fullLayout.width - element.getBoundingClientRect().width);
    })).toBeLessThan(1);
    await expectEqualScale(chart);
  }
});
