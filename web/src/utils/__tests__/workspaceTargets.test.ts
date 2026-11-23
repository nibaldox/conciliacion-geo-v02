import { describe, expect, it } from 'vitest';
import { resolveSectionByName, type SectionRef } from '../workspaceTargets';

const SECTIONS: SectionRef[] = [
  { id: 'id-01', name: 'S-01' },
  { id: 'id-37', name: 'S-37' },
  { id: 'id-38', name: 'S-38' },
];

describe('resolveSectionByName', () => {
  it('returns the section with an exact name match', () => {
    expect(resolveSectionByName('S-37', SECTIONS)).toStrictEqual({ id: 'id-37', name: 'S-37' });
  });

  it('returns null when the name does not exist', () => {
    expect(resolveSectionByName('S-99', SECTIONS)).toBeNull();
  });

  it('returns null when the requested name is duplicated', () => {
    const sections: SectionRef[] = [
      { id: 'a', name: 'S-37' },
      { id: 'b', name: 'S-37' },
    ];

    expect(resolveSectionByName('S-37', sections)).toBeNull();
  });

  it('only blocks the duplicated name, not other unique names', () => {
    const sections: SectionRef[] = [
      { id: 'a', name: 'S-37' },
      { id: 'b', name: 'S-37' },
      { id: 'c', name: 'S-38' },
    ];

    expect(resolveSectionByName('S-38', sections)).toStrictEqual({ id: 'c', name: 'S-38' });
  });

  it('is exact about letter case', () => {
    expect(resolveSectionByName('s-37', SECTIONS)).toBeNull();
  });

  it('is exact about surrounding spaces', () => {
    expect(resolveSectionByName(' S-37', SECTIONS)).toBeNull();
    expect(resolveSectionByName('S-37 ', SECTIONS)).toBeNull();
  });

  it('returns null for an empty list', () => {
    expect(resolveSectionByName('S-37', [])).toBeNull();
  });
});
