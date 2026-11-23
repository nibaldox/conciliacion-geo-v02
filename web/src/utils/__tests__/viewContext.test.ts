import { describe, expect, it } from 'vitest';
import { describeViewContext, type ViewContextInput } from '../viewContext';
import type { SectionRef } from '../workspaceTargets';

const SECTION: SectionRef = { id: 'id-37', name: 'S-37' };

function makeInput(overrides: Partial<ViewContextInput> = {}): ViewContextInput {
  return {
    view: 'dashboard',
    profilesMode: 'grid',
    section: null,
    bench: null,
    ...overrides,
  };
}

describe('describeViewContext', () => {
  it('describes the dashboard without a section', () => {
    expect(describeViewContext(makeInput({ view: 'dashboard' }))).toStrictEqual({ view: 'dashboard' });
  });

  it('adds the chosen section name to the dashboard', () => {
    expect(describeViewContext(makeInput({ view: 'dashboard', section: SECTION })))
      .toStrictEqual({ view: 'dashboard', sectionName: 'S-37' });
  });

  it('ignores a bench on the dashboard', () => {
    expect(describeViewContext(makeInput({
      view: 'dashboard',
      section: SECTION,
      bench: { designBench: 2 },
    }))).toStrictEqual({ view: 'dashboard', sectionName: 'S-37' });
  });

  it('describes profiles in grid mode without section details', () => {
    expect(describeViewContext(makeInput({ view: 'profiles', profilesMode: 'grid' })))
      .toStrictEqual({ view: 'profiles', mode: 'grid' });
  });

  it('omits sectionName and designBench in profiles grid even when they are provided', () => {
    expect(describeViewContext(makeInput({
      view: 'profiles',
      profilesMode: 'grid',
      section: SECTION,
      bench: { designBench: 1 },
    }))).toStrictEqual({ view: 'profiles', mode: 'grid' });
  });

  it('describes profiles in detail mode with section and bench', () => {
    expect(describeViewContext(makeInput({
      view: 'profiles',
      profilesMode: 'detail',
      section: SECTION,
      bench: { designBench: 1 },
    }))).toStrictEqual({ view: 'profiles', mode: 'detail', sectionName: 'S-37', designBench: 1 });
  });

  it('describes profiles in detail mode with a section and no bench', () => {
    expect(describeViewContext(makeInput({
      view: 'profiles',
      profilesMode: 'detail',
      section: SECTION,
    }))).toStrictEqual({ view: 'profiles', mode: 'detail', sectionName: 'S-37' });
  });

  it('describes profiles in detail mode without a section', () => {
    expect(describeViewContext(makeInput({ view: 'profiles', profilesMode: 'detail' })))
      .toStrictEqual({ view: 'profiles', mode: 'detail' });
  });

  it('ignores a bench when there is no section', () => {
    expect(describeViewContext(makeInput({
      view: 'profiles',
      profilesMode: 'detail',
      bench: { designBench: 1 },
    }))).toStrictEqual({ view: 'profiles', mode: 'detail' });
  });

  it.each(['3d', 'blast', 'export-ai'] as const)('returns only the view for %s', (view) => {
    expect(describeViewContext(makeInput({
      view,
      profilesMode: 'detail',
      section: SECTION,
      bench: { designBench: 1 },
    }))).toStrictEqual({ view });
  });
});
