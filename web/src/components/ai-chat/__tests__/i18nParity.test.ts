import { describe, expect, it } from 'vitest';
import es from '../../../locales/es.json';
import en from '../../../locales/en.json';

type LocaleNode = Record<string, unknown>;

function collectKeyPaths(node: LocaleNode, prefix = ''): string[] {
  return Object.entries(node).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
      return collectKeyPaths(value as LocaleNode, path);
    }
    return [path];
  });
}

describe('aiChat i18n parity', () => {
  it('es and en define the exact same aiChat.* key set', () => {
    const esKeys = collectKeyPaths(es.aiChat as LocaleNode).sort();
    const enKeys = collectKeyPaths(en.aiChat as LocaleNode).sort();
    expect(enKeys).toEqual(esKeys);
    expect(esKeys.length).toBeGreaterThan(40);
  });

  it('no aiChat value is empty in either locale', () => {
    for (const [locale, node] of [
      ['es', es.aiChat],
      ['en', en.aiChat],
    ] as const) {
      for (const key of collectKeyPaths(node as LocaleNode)) {
        const value = key
          .split('.')
          .reduce<unknown>(
            (acc, part) =>
              typeof acc === 'object' && acc !== null
                ? (acc as LocaleNode)[part]
                : undefined,
            node,
          );
        expect(`${locale}:${key}`, `${locale}:${key} is empty`).toBeTruthy();
        expect(typeof value === 'string' && value.trim().length > 0).toBe(true);
      }
    }
  });

  it('the reports local-only notice exists in both locales', () => {
    const esNotice = (es.ai_reporter as LocaleNode).local_only_notice;
    const enNotice = (en.ai_reporter as LocaleNode).local_only_notice;
    expect(esNotice).toContain('IA solo local');
    expect(enNotice).toContain('local AI only');
  });
});
