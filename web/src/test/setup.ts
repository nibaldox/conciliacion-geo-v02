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
