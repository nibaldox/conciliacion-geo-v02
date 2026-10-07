export function readThemeColor(token: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback;
  return getComputedStyle(document.documentElement).getPropertyValue(token).trim() || fallback;
}

export function applyTheme(isDark: boolean): void {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.classList.toggle('dark', isDark);
  root.classList.toggle('light', !isDark);
  root.style.colorScheme = isDark ? 'dark' : 'light';
  document.querySelector('meta[name="color-scheme"]')?.setAttribute('content', isDark ? 'dark' : 'light');
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', readThemeColor('--color-surface', root.style.colorScheme === 'dark' ? '#111820' : '#f1f5f9'));
}

export function resolveThemeVariables(value: unknown): unknown {
  if (typeof value === 'string') {
    const match = /^var\((--[\w-]+)(?:,\s*([^)]*))?\)$/.exec(value);
    return match ? readThemeColor(match[1]!, match[2] ?? value) : value;
  }
  if (Array.isArray(value)) return value.map(resolveThemeVariables);
  if (value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype) {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, resolveThemeVariables(item)]));
  }
  return value;
}
