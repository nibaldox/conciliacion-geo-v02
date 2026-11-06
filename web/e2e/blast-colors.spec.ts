import { expect, test, type Page } from '@playwright/test';

const HARNESS = '/conciliacion-geo-v02/e2e/fixtures/blast-colors-harness.html';
const RED_CENTER = { x: 120, y: 200 };
const GREEN_CENTER = { x: 280, y: 200 };
const NEUTRAL_CENTER = { x: 200, y: 120 };

async function openHarness(page: Page) {
  await page.goto(HARNESS);
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 30_000 });
  await page.waitForTimeout(300);
}

async function readPixel(page: Page, point: { x: number; y: number }) {
  return page.evaluate(({ x, y }) => {
    const gl = window.__gl;
    if (!gl) throw new Error('WebGL context not exposed by harness');
    const canvas = gl.canvas as HTMLCanvasElement;
    const scaleX = canvas.width / 400;
    const scaleY = canvas.height / 400;
    const px = new Uint8Array(4);
    gl.readPixels(Math.round(x * scaleX), Math.round((400 - y) * scaleY), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    return [px[0], px[1], px[2], px[3]];
  }, point);
}

type Hue = 'red' | 'green' | 'blue';

function expectHue(actual: number[], hue: Hue, label: string) {
  const [r, g, b] = actual.map((value) => value ?? 0);
  const dominant = hue === 'red' ? r : hue === 'green' ? g : b;
  const others = [r, g, b].filter((_, index) => index !== (hue === 'red' ? 0 : hue === 'green' ? 1 : 2));
  expect(dominant, `${label} dominant channel actual=${actual.join(',')}`).toBeGreaterThan(180);
  for (const other of others) {
    expect(other, `${label} secondary channel actual=${actual.join(',')}`).toBeLessThan(dominant - 80);
  }
}

async function countHaloPixels(page: Page, center: { x: number; y: number }, innerPx: number, outerPx: number) {
  return page.evaluate(({ x, y, innerPx, outerPx }) => {
    const gl = window.__gl;
    if (!gl) throw new Error('WebGL context not exposed by harness');
    const canvas = gl.canvas as HTMLCanvasElement;
    const scaleX = canvas.width / 400;
    const scaleY = canvas.height / 400;
    const size = Math.ceil(outerPx * 2 * scaleX) + 2;
    const cx = Math.round(x * scaleX);
    const cy = Math.round((400 - y) * scaleY);
    const left = cx - Math.floor(size / 2);
    const bottom = cy - Math.floor(size / 2);
    const px = new Uint8Array(size * size * 4);
    gl.readPixels(left, bottom, size, size, gl.RGBA, gl.UNSIGNED_BYTE, px);
    let yellow = 0;
    for (let row = 0; row < size; row += 1) {
      for (let col = 0; col < size; col += 1) {
        const dx = (left + col) - cx;
        const dy = (bottom + row) - cy;
        const dist = Math.hypot(dx, dy);
        if (dist < innerPx * scaleX || dist > outerPx * scaleX) continue;
        const i = (row * size + col) * 4;
        if (px[i] > 200 && px[i + 1] > 180 && px[i + 2] < 140) yellow += 1;
      }
    }
    return yellow;
  }, { ...center, innerPx, outerPx });
}

async function frame(page: Page) {
  await page.evaluate(() => new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
}

test.describe('BlastHolesLayer collar material (real R3F + WebGL)', () => {
  test('GPU gate: WebGL2 is available in this browser', async ({ page }) => {
    await page.goto(HARNESS);
    const hasWebGL2 = await page.evaluate(() => {
      const canvas = document.createElement('canvas');
      return Boolean(canvas.getContext('webgl2'));
    });
    expect(hasWebGL2, 'WebGL2 required: run with BLAST_COLORS_CHROME_PATH and swiftshader flags').toBe(true);
  });

  test('collars keep their red and green attribute colors, then follow a change to blue', async ({ page }) => {
    await openHarness(page);

    const redBefore = await readPixel(page, RED_CENTER);
    const greenBefore = await readPixel(page, GREEN_CENTER);
    expectHue(redBefore.slice(0, 3), 'red', 'red collar pixel');
    expectHue(greenBefore.slice(0, 3), 'green', 'green collar pixel');

    await page.evaluate(() => window.__setColors?.('#0000ff', '#00ff00'));
    await frame(page);
    await frame(page);

    const blueAfter = await readPixel(page, RED_CENTER);
    const greenAfter = await readPixel(page, GREEN_CENTER);
    expectHue(blueAfter.slice(0, 3), 'blue', 'first collar after change to blue');
    expectHue(greenAfter.slice(0, 3), 'green', 'second collar stays green');
  });
  test('colorCollars=false paints the collar neutral while a default collar keeps its red data color', async ({ page }) => {
    await openHarness(page);

    const defaultRed = await readPixel(page, RED_CENTER);
    expectHue(defaultRed.slice(0, 3), 'red', 'default collar keeps data color');

    const neutral = await readPixel(page, NEUTRAL_CENTER);
    const [r, g, b] = neutral.slice(0, 3);
    expect(r, `neutral collar must not be red actual=${neutral.join(',')}`).toBeLessThan(120);
    expect(b, `neutral collar uses the collar-only default actual=${neutral.join(',')}`).toBeGreaterThan(200);
  });

  test('selection adds a separate halo and keeps the red data color of the collar', async ({ page }) => {
    await openHarness(page);

    const redBefore = await readPixel(page, RED_CENTER);
    expectHue(redBefore.slice(0, 3), 'red', 'red collar before selection');
    expect(await countHaloPixels(page, RED_CENTER, 45, 70), 'no halo before selection').toBe(0);

    await page.evaluate(() => window.__setSelected?.('red'));
    await frame(page);
    await frame(page);

    const redSelected = await readPixel(page, RED_CENTER);
    expectHue(redSelected.slice(0, 3), 'red', 'red collar pixel while selected');
    const haloCount = await countHaloPixels(page, RED_CENTER, 45, 70);
    expect(haloCount, 'visible yellow halo ring around selected collar').toBeGreaterThan(200);

    const greenSelected = await readPixel(page, GREEN_CENTER);
    expectHue(greenSelected.slice(0, 3), 'green', 'unselected green collar stays green');

    await page.evaluate(() => window.__setSelected?.(null));
    await frame(page);
    await frame(page);

    const redDeselected = await readPixel(page, RED_CENTER);
    expectHue(redDeselected.slice(0, 3), 'red', 'red collar after deselect');
    expect(await countHaloPixels(page, RED_CENTER, 45, 70), 'halo removed on deselect').toBe(0);
  });
});
