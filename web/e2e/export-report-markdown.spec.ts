import { test, expect } from '@playwright/test';

const report = [
  '# Informe de conciliación',
  '',
  'Resumen de revisión para el sector Norte.',
  '',
  '| Banco | Estado | Desviación |',
  '| --- | --- | ---: |',
  '| 2 | CUMPLE | 0.4 m |',
  '| 3 | FUERA DE TOLERANCIA | 2.1 m |',
  '',
  '- Revisar el banco 3.',
  '- Mantener seguimiento semanal.',
  '',
  '```text',
  'S-01: control geotécnico',
  '```',
].join('\n');

test('export view renders a full-width Markdown report with export actions first', async ({ page }) => {
  await page.setViewportSize({ width: 1600, height: 1400 });
  await page.route('**/api/v1/ai/health', (route) => route.fulfill({ json: { status: 'ok' } }));
  await page.route('**/api/v1/ai/providers', (route) => route.fulfill({ json: { providers: ['openai'] } }));
  await page.route('**/api/v1/ai/generate', (route) => route.fulfill({ json: {
    content: report,
    finish_reason: 'stop',
    usage: { prompt_tokens: 120, completion_tokens: 90, total_tokens: 210, is_synthetic: false },
    cached: false,
    chunk_index: 0,
  } }));

  await page.goto('/');
  await page.getByRole('button', { name: 'Probar con datos de ejemplo' }).click();
  await page.locator('[data-slot="views-toolbar"] button[aria-label="Exportar"]').click();
  await expect(page.getByTestId('ai-reporter-form')).toBeVisible();
  await page.getByRole('button', { name: /Generar informe/i }).click();
  await expect(page.getByTestId('ai-reporter-result')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Informe de conciliación', level: 1 })).toBeVisible();
  await expect(page.getByRole('table')).toBeVisible();
  await expect(page.getByRole('listitem').first()).toContainText('Revisar el banco 3.');
  await expect(page.getByText('S-01: control geotécnico')).toBeVisible();
  await expect(page.getByRole('columnheader', { name: 'Desviación' })).toHaveCSS('text-align', 'right');

  const actionsBeforeProjectInfo = await page.evaluate(() => {
    const actions = document.querySelector('[data-testid="export-actions"]');
    const projectInfo = document.querySelector('[data-slot="export-panel"] h4');
    return !!actions && !!projectInfo && Boolean(actions.compareDocumentPosition(projectInfo) & Node.DOCUMENT_POSITION_FOLLOWING);
  });
  expect(actionsBeforeProjectInfo).toBe(true);

  const widths = await page.evaluate(() => ({
    workspace: document.querySelector('[data-slot="export-workspace"]')?.getBoundingClientRect().width ?? 0,
    report: document.querySelector('[data-slot="ai-reporter"]')?.getBoundingClientRect().width ?? 0,
  }));
  expect(Math.abs(widths.workspace - widths.report)).toBeLessThan(1);
  await expect(page.locator('[data-slot="theme-toggle"]')).toHaveAttribute('data-theme', 'dark');
  await page.screenshot({ path: '../docs/design/export-after-dark.png', fullPage: true });

  await page.getByRole('button', { name: 'Cambiar a modo claro' }).click();
  await expect(page.locator('[data-slot="theme-toggle"]')).toHaveAttribute('data-theme', 'light');
  await page.screenshot({ path: '../docs/design/export-after.png', fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  const navigationToggle = page.getByRole('button', { name: 'Abrir o cerrar navegación' });
  await navigationToggle.click();
  await expect(navigationToggle).toHaveAttribute('aria-expanded', 'false');
  const mobileLayout = await page.evaluate(() => {
    const workspace = document.querySelector('[data-slot="export-workspace"]');
    const report = document.querySelector('[data-slot="ai-reporter"]');
    const actions = document.querySelector('[data-testid="export-actions"]');
    const projectInfo = document.querySelector('[data-slot="export-panel"] h4');
    const table = document.querySelector('[data-testid="ai-reporter-content"] table');
    const tableScroller = table?.parentElement;
    if (!workspace || !report || !actions || !projectInfo || !tableScroller) return null;
    const workspaceBox = workspace.getBoundingClientRect();
    const reportBox = report.getBoundingClientRect();
    const actionsBox = actions.getBoundingClientRect();
    const projectBox = projectInfo.getBoundingClientRect();
    return {
      workspaceWithinViewport: workspaceBox.left >= 0 && workspaceBox.right <= window.innerWidth,
      reportWithinViewport: reportBox.left >= 0 && reportBox.right <= window.innerWidth,
      reportMatchesWorkspace: Math.abs(reportBox.width - workspaceBox.width) < 1,
      actionsAboveProjectInfo: actionsBox.top < projectBox.top,
      tableScrollsWithinReport: tableScroller.scrollWidth > tableScroller.clientWidth && getComputedStyle(tableScroller).overflowX === 'auto',
      documentWithinViewport: document.documentElement.scrollWidth <= window.innerWidth,
    };
  });
  expect(mobileLayout).toEqual({
    workspaceWithinViewport: true,
    reportWithinViewport: true,
    reportMatchesWorkspace: true,
    actionsAboveProjectInfo: true,
    tableScrollsWithinReport: true,
    documentWithinViewport: true,
  });
  await expect(page.getByRole('table')).toBeVisible();
  await page.screenshot({ path: '../docs/design/export-after-mobile.png', fullPage: true });
  await page.getByTestId('ai-reporter-result').screenshot({ path: '../docs/design/export-after-mobile-report.png' });
});
