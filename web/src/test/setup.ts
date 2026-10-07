import '@testing-library/jest-dom/vitest';

// Silence noisy console errors from React 19 act() warnings during
// component tests. The tests are still asserting correctly via
// toBeInTheDocument, but React 19 emits a warning for state updates
// outside of act() in some async flows that we don't care about here.
const originalError = console.error;
beforeAll(() => {
  console.error = (...args: unknown[]) => {
    const msg = String(args[0] ?? '');
    if (msg.includes('not wrapped in act')) return;
    originalError(...args);
  };
});
afterAll(() => {
  console.error = originalError;
});

const webStorageNames = ['localStorage', 'sessionStorage'] as const;

interface JsdomHost {
  readonly jsdom?: {
    readonly window?: Partial<Record<(typeof webStorageNames)[number], unknown>>;
  };
}

function isStorage(value: unknown): value is Storage {
  if (typeof value !== 'object' || value === null) return false;
  const candidate = value as Record<string, unknown>;
  return ['getItem', 'setItem', 'removeItem', 'clear'].every(
    (method) => typeof candidate[method] === 'function',
  );
}

function exposeJsdomWebStorage(): void {
  const storageWindow = (globalThis as typeof globalThis & JsdomHost).jsdom?.window;
  if (!storageWindow) return;
  for (const name of webStorageNames) {
    const candidate = storageWindow[name];
    if (!isStorage(candidate)) continue;
    if (globalThis[name] === candidate) continue;
    Object.defineProperty(globalThis, name, { value: candidate, configurable: true, writable: true });
  }
}

exposeJsdomWebStorage();
