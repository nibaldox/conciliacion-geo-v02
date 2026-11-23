import { describe, expect, it } from 'vitest';
import { findAgentChips, type AgentChip } from '../agentChips';
import type { SectionRef } from '../workspaceTargets';

function buildSections(count: number): SectionRef[] {
  return Array.from({ length: count }, (_, index) => {
    const number = String(index + 1).padStart(2, '0');
    return { id: `id-${number}`, name: `S-${number}` };
  });
}

const SECTIONS = buildSections(92);

function buildLongText(): string {
  return Array.from({ length: 92 }, (_, index) => {
    const number = String(index + 1).padStart(2, '0');
    return `Revisar S-${number}, banco ${(index % 3) + 1}; `;
  }).join('');
}

describe('findAgentChips', () => {
  it('finds a section chip with exact offsets', () => {
    expect(findAgentChips('La peor es S-37', SECTIONS)).toStrictEqual<AgentChip[]>([
      { kind: 'section', sectionId: 'id-37', name: 'S-37', start: 11, end: 15 },
    ]);
  });

  it('does not chip S-3 inside S-37 when both names exist', () => {
    const sections = [...SECTIONS, { id: 'id-3', name: 'S-3' }];

    expect(findAgentChips('S-37', sections)).toStrictEqual<AgentChip[]>([
      { kind: 'section', sectionId: 'id-37', name: 'S-37', start: 0, end: 4 },
    ]);
  });

  it('still chips S-3 when it appears as a whole word', () => {
    const sections = [...SECTIONS, { id: 'id-3', name: 'S-3' }];

    expect(findAgentChips('S-3 y S-37', sections)).toStrictEqual<AgentChip[]>([
      { kind: 'section', sectionId: 'id-3', name: 'S-3', start: 0, end: 3 },
      { kind: 'section', sectionId: 'id-37', name: 'S-37', start: 6, end: 10 },
    ]);
  });

  it('finds two section chips', () => {
    expect(findAgentChips('S-37 y S-38', SECTIONS)).toStrictEqual<AgentChip[]>([
      { kind: 'section', sectionId: 'id-37', name: 'S-37', start: 0, end: 4 },
      { kind: 'section', sectionId: 'id-38', name: 'S-38', start: 7, end: 11 },
    ]);
  });

  it.each([
    ['S-37.', 0, 4],
    ['(S-37)', 1, 5],
    ['S-37,', 0, 4],
  ])('chips a section next to punctuation: %s', (text, start, end) => {
    expect(findAgentChips(text, SECTIONS)).toStrictEqual<AgentChip[]>([
      { kind: 'section', sectionId: 'id-37', name: 'S-37', start, end },
    ]);
  });

  it.each(['XS-37', 'S-370', 'S-37_', 'S-37a', 'ÑS-37'])('does not chip %s', (text) => {
    expect(findAgentChips(text, SECTIONS)).toStrictEqual([]);
  });

  it('does not chip a duplicated section name', () => {
    const sections: SectionRef[] = [
      { id: 'a', name: 'S-37' },
      { id: 'b', name: 'S-37' },
    ];

    expect(findAgentChips('La peor es S-37', sections)).toStrictEqual([]);
  });

  it('lets a duplicated longer name block a shorter name it contains', () => {
    const sections: SectionRef[] = [
      { id: 'a', name: 'Norte Sur' },
      { id: 'b', name: 'Norte Sur' },
      { id: 'c', name: 'Norte' },
    ];

    expect(findAgentChips('Norte Sur', sections)).toStrictEqual([]);
  });

  it('keeps chips for unique names next to a duplicated one', () => {
    const sections: SectionRef[] = [
      { id: 'a', name: 'S-37' },
      { id: 'b', name: 'S-37' },
      { id: 'c', name: 'S-38' },
    ];

    expect(findAgentChips('S-37 y S-38', sections)).toStrictEqual<AgentChip[]>([
      { kind: 'section', sectionId: 'c', name: 'S-38', start: 7, end: 11 },
    ]);
  });

  it('prefers the longest section name when names overlap', () => {
    const sections: SectionRef[] = [
      { id: 'n', name: 'Norte' },
      { id: 'ns', name: 'Norte Sur' },
    ];

    expect(findAgentChips('Zona Norte Sur', sections)).toStrictEqual<AgentChip[]>([
      { kind: 'section', sectionId: 'ns', name: 'Norte Sur', start: 5, end: 14 },
    ]);
  });

  it('escapes regular-expression characters in section names', () => {
    const sections: SectionRef[] = [{ id: 'dot', name: 'T.1 (a)' }];

    expect(findAgentChips('ver T.1 (a) hoy', sections)).toStrictEqual<AgentChip[]>([
      { kind: 'section', sectionId: 'dot', name: 'T.1 (a)', start: 4, end: 11 },
    ]);
    expect(findAgentChips('ver TX1 (a) hoy', sections)).toStrictEqual([]);
  });

  it('ignores an empty section name', () => {
    expect(findAgentChips('hola mundo', [{ id: 'e', name: '' }])).toStrictEqual([]);
  });

  it('adds a bench chip that uses the section mentioned before it', () => {
    expect(findAgentChips('En S-37 el Banco 2 no cumple', SECTIONS)).toStrictEqual<AgentChip[]>([
      { kind: 'section', sectionId: 'id-37', name: 'S-37', start: 3, end: 7 },
      {
        kind: 'bench',
        sectionId: 'id-37',
        sectionName: 'S-37',
        designBench: 2,
        label: 'Banco 2',
        start: 11,
        end: 18,
      },
    ]);
  });

  it('uses contextSectionId for a bench with no section mention', () => {
    expect(findAgentChips('banco 1', SECTIONS, 'id-37')).toStrictEqual<AgentChip[]>([
      {
        kind: 'bench',
        sectionId: 'id-37',
        sectionName: 'S-37',
        designBench: 1,
        label: 'banco 1',
        start: 0,
        end: 7,
      },
    ]);
  });

  it('returns no bench chip without a section mention or context', () => {
    expect(findAgentChips('banco 1', SECTIONS)).toStrictEqual([]);
    expect(findAgentChips('banco 1', SECTIONS, null)).toStrictEqual([]);
  });

  it('returns no bench chip when contextSectionId is not in sections', () => {
    expect(findAgentChips('banco 1', SECTIONS, 'id-999')).toStrictEqual([]);
  });

  it('uses the closest previous section mention for a bench', () => {
    const text = 'S-37 ... S-38 ... banco 3';

    expect(findAgentChips(text, SECTIONS, 'id-01')).toStrictEqual<AgentChip[]>([
      { kind: 'section', sectionId: 'id-37', name: 'S-37', start: 0, end: 4 },
      { kind: 'section', sectionId: 'id-38', name: 'S-38', start: 9, end: 13 },
      {
        kind: 'bench',
        sectionId: 'id-38',
        sectionName: 'S-38',
        designBench: 3,
        label: 'banco 3',
        start: 18,
        end: 25,
      },
    ]);
  });

  it('prefers a previous section mention over contextSectionId', () => {
    expect(findAgentChips('S-38 banco 3', SECTIONS, 'id-37')).toStrictEqual<AgentChip[]>([
      { kind: 'section', sectionId: 'id-38', name: 'S-38', start: 0, end: 4 },
      {
        kind: 'bench',
        sectionId: 'id-38',
        sectionName: 'S-38',
        designBench: 3,
        label: 'banco 3',
        start: 5,
        end: 12,
      },
    ]);
  });

  it('gives no bench chip when the closest section mention is duplicated', () => {
    const sections: SectionRef[] = [
      { id: 'a', name: 'S-37' },
      { id: 'b', name: 'S-37' },
    ];

    expect(findAgentChips('S-37 banco 2', sections, 'id-01')).toStrictEqual([]);
  });

  it.each(['banco 1234', 'banco \u0662'])('ignores the bench mention %s', (text) => {
    expect(findAgentChips(text, SECTIONS, 'id-37')).toStrictEqual([]);
  });

  it('returns chips sorted by start without overlaps', () => {
    const text = 'banco 2 y S-37 y banco 3 y S-38';

    expect(findAgentChips(text, SECTIONS, 'id-01')).toStrictEqual<AgentChip[]>([
      {
        kind: 'bench',
        sectionId: 'id-01',
        sectionName: 'S-01',
        designBench: 2,
        label: 'banco 2',
        start: 0,
        end: 7,
      },
      { kind: 'section', sectionId: 'id-37', name: 'S-37', start: 10, end: 14 },
      {
        kind: 'bench',
        sectionId: 'id-37',
        sectionName: 'S-37',
        designBench: 3,
        label: 'banco 3',
        start: 17,
        end: 24,
      },
      { kind: 'section', sectionId: 'id-38', name: 'S-38', start: 27, end: 31 },
    ]);
  });

  it('returns an empty list when nothing matches', () => {
    expect(findAgentChips('Sin coincidencias aquí', SECTIONS)).toStrictEqual([]);
    expect(findAgentChips('', SECTIONS)).toStrictEqual([]);
  });

  it('scans a 4,000-character text with 92 sections in under 50 ms', () => {
    const text = buildLongText().repeat(2);
    expect(text.length).toBeGreaterThanOrEqual(4000);

    const started = performance.now();
    const chips = findAgentChips(text, SECTIONS, 'id-01');
    const elapsed = performance.now() - started;

    expect(chips.length).toBeGreaterThan(0);
    expect(chips.every((chip, index) => index === 0 || chip.start >= chips[index - 1].end)).toBe(true);
    expect(elapsed).toBeLessThan(50);
  });
});
