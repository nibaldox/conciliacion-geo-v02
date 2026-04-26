import { test, expect } from '@playwright/test';

test.describe('API Endpoints', () => {
  test('health check', async ({ request }) => {
    const response = await request.get('http://localhost:8000/api/v1/health');
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('status', 'ok');
    expect(data).toHaveProperty('version', '2.0.0');
  });

  test('settings endpoint returns defaults', async ({ request }) => {
    const response = await request.get('http://localhost:8000/api/v1/settings');
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(data).toHaveProperty('process');
    expect(data).toHaveProperty('tolerances');
  });

  test('sections endpoint returns empty list', async ({ request }) => {
    const response = await request.get('http://localhost:8000/api/v1/sections');
    expect(response.ok()).toBeTruthy();
    const data = await response.json();
    expect(Array.isArray(data)).toBeTruthy();
  });

  test('process status returns idle', async ({ request }) => {
    const response = await request.get('http://localhost:8000/api/v1/process/status');
    expect(response.ok()).toBeTruthy();
  });
});
