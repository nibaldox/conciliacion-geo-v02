import { beforeEach, describe, expect, it } from 'vitest';

describe('test environment web storage', () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
  });

  it('exposes a jsdom Storage-compatible localStorage', () => {
    expect(localStorage).toBeInstanceOf(Storage);
    expect(localStorage.length).toBe(0);
    localStorage.setItem('conciliacion.test', 'value');
    expect(localStorage.length).toBe(1);
    expect(localStorage.getItem('conciliacion.test')).toBe('value');
    localStorage.removeItem('conciliacion.test');
    expect(localStorage.getItem('conciliacion.test')).toBeNull();
  });

  it('exposes a jsdom Storage-compatible sessionStorage', () => {
    expect(sessionStorage).toBeInstanceOf(Storage);
    expect(sessionStorage.length).toBe(0);
    sessionStorage.setItem('conciliacion.test', 'value');
    expect(sessionStorage.length).toBe(1);
    expect(sessionStorage.getItem('conciliacion.test')).toBe('value');
    sessionStorage.removeItem('conciliacion.test');
    expect(sessionStorage.getItem('conciliacion.test')).toBeNull();
  });

  it('keeps localStorage and sessionStorage isolated', () => {
    localStorage.setItem('shared-key', 'local');
    sessionStorage.setItem('shared-key', 'session');
    expect(localStorage.getItem('shared-key')).toBe('local');
    expect(sessionStorage.getItem('shared-key')).toBe('session');
  });
});
