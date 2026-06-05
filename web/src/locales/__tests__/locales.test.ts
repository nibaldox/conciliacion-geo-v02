/**
 * Locale structure test — guarantees the two locale files stay
 * in sync. If anyone adds a new key to one file but forgets the
 * other, this test fails with a clear list of missing keys.
 *
 * Also asserts that a small set of "mission-critical" keys (the
 * ones we just added for the Phase 4/5 redesign) are present
 * in both locales. Catches typos and missing keys early.
 */

import { describe, it, expect } from 'vitest';
import es from '../../locales/es.json';
import en from '../../locales/en.json';

function flattenKeys(obj: Record<string, unknown>, prefix = ''): Set<string> {
  const out = new Set<string>();
  for (const [k, v] of Object.entries(obj)) {
    const full = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      for (const sub of flattenKeys(v as Record<string, unknown>, full)) {
        out.add(sub);
      }
    } else {
      out.add(full);
    }
  }
  return out;
}

const esKeys = flattenKeys(es);
const enKeys = flattenKeys(en);

describe('Locale structure parity (es.json vs en.json)', () => {
  it('has the same number of keys', () => {
    expect(esKeys.size).toBe(enKeys.size);
  });

  it('has no keys missing in es.json', () => {
    const missing = [...enKeys].filter((k) => !esKeys.has(k));
    expect(missing, `Keys in en.json but missing in es.json: ${missing.join(', ')}`).toEqual([]);
  });

  it('has no keys missing in en.json', () => {
    const missing = [...esKeys].filter((k) => !enKeys.has(k));
    expect(missing, `Keys in es.json but missing in en.json: ${missing.join(', ')}`).toEqual([]);
  });

  it('parses as valid JSON objects (no broken structure)', () => {
    expect(typeof es).toBe('object');
    expect(typeof en).toBe('object');
  });
});

describe('Mission Control redesign i18n keys', () => {
  // Keys that the Phase 4/5 redesign relies on. If any of these
  // are missing, the UI shows the defaultValue string instead of
  // a proper translation — this test catches that early.
  const REQUIRED = [
    'app.mission',
    'app.mission_step',
    'wizard.step.step1',
    'wizard.step.step2',
    'wizard.step.step3',
    'wizard.step.step4',
    'step1.design_subtitle',
    'step1.topo_subtitle',
    'step1.terminal.ingest',
    'step1.terminal.both_loaded',
    'step1.terminal.waiting',
    'step1.terminal.coord',
    'step1.launch',
    'step1.launch_waiting',
    'step4.footer_status',
    'profileView.header.eyebrow',
    'profileView.header.last_run',
    'profileView.summary.title',
    'profileView.summary.aria',
    'profileView.summary.headline',
    'profileView.summary.no_benches',
    'profileView.summary.bar_aria',
  ];

  for (const key of REQUIRED) {
    it(`es.json has "${key}"`, () => {
      expect(esKeys.has(key), `Missing in es.json: ${key}`).toBe(true);
    });
    it(`en.json has "${key}"`, () => {
      expect(enKeys.has(key), `Missing in en.json: ${key}`).toBe(true);
    });
  }
});
