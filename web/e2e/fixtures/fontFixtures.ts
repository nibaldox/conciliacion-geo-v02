import { readFileSync } from 'node:fs';
import type { Page } from '@playwright/test';

type FontFixtureSpec = {
  family: string;
  file: string;
  weights: readonly number[];
  url: string;
};

const LATIN_UNICODE_RANGE =
  'U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD';

const BASE_FIXTURES: readonly FontFixtureSpec[] = [
  {
    family: 'Outfit',
    file: 'outfit-latin.woff2',
    weights: [400, 500, 600, 700],
    url: 'https://fonts.gstatic.com/s/outfit/v15/QGYvz_MVcBeNP4NJtEtq.woff2',
  },
  {
    family: 'JetBrains Mono',
    file: 'jetbrains-mono-latin.woff2',
    weights: [400, 500, 700],
    url: 'https://fonts.gstatic.com/s/jetbrainsmono/v24/tDbv2o-flEEny0FZhsfKu5WU4zr3E_BX0PnT8RD8yKwBNntkaToggR7BYRbKPxDcwg.woff2',
  },
];

const FONT_FIXTURES = BASE_FIXTURES.map((spec) => ({
  ...spec,
  bytes: readFileSync(new URL(`./fonts/${spec.file}`, import.meta.url)),
}));

const fixtureCss = FONT_FIXTURES.flatMap((spec) =>
  spec.weights.map((weight) =>
    [
      '@font-face {',
      `  font-family: '${spec.family}';`,
      '  font-style: normal;',
      `  font-weight: ${weight};`,
      '  font-display: swap;',
      `  src: url(${spec.url}) format('woff2');`,
      `  unicode-range: ${LATIN_UNICODE_RANGE};`,
      '}',
    ].join('\n'),
  ),
).join('\n');

const CSS_HEADERS = {
  'content-type': 'text/css; charset=utf-8',
  'access-control-allow-origin': '*',
};

const FONT_HEADERS = {
  'content-type': 'font/woff2',
  'access-control-allow-origin': '*',
};

export async function installFontFixtures(page: Page): Promise<void> {
  await page.route('https://fonts.googleapis.com/**', (route) => {
    const request = route.request();
    if (request.method() !== 'GET' || !new URL(request.url()).pathname.startsWith('/css')) {
      return route.continue();
    }
    return route.fulfill({ status: 200, headers: CSS_HEADERS, body: fixtureCss });
  });

  for (const spec of FONT_FIXTURES) {
    await page.route(spec.url, (route) => {
      if (route.request().method() !== 'GET') {
        return route.continue();
      }
      return route.fulfill({ status: 200, headers: FONT_HEADERS, body: spec.bytes });
    });
  }
}
