import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSession, type DemoData } from '../session';

const demoPayload = { sections: [{ section_name: 'S-01' }] } as unknown as DemoData;

beforeEach(() => {
  useSession.getState().reset();
});

afterEach(() => {
  useSession.getState().reset();
  vi.unstubAllGlobals();
});

describe('session store selectedByUser flag', () => {
  it('starts false and is false again after reset', () => {
    expect(useSession.getState().selectedByUser).toBe(false);
    useSession.getState().setSelectedSection('S-03');
    useSession.getState().reset();
    expect(useSession.getState().selectedByUser).toBe(false);
  });

  it('becomes true when the user picks a section', () => {
    useSession.getState().setSelectedSection('S-03');
    expect(useSession.getState().selectedSection).toBe('S-03');
    expect(useSession.getState().selectedByUser).toBe(true);
  });

  it('clearing the selection with null drops the flag', () => {
    useSession.getState().setSelectedSection('S-03');
    useSession.getState().setSelectedSection(null);
    expect(useSession.getState().selectedSection).toBeNull();
    expect(useSession.getState().selectedByUser).toBe(false);
  });

  it('a demo reload that reuses cached data auto-selects the first section without user intent', async () => {
    useSession.setState({ demoData: demoPayload });
    useSession.getState().setSelectedSection('S-02');
    await useSession.getState().loadDemo();
    expect(useSession.getState().selectedSection).toBe('S-01');
    expect(useSession.getState().selectedByUser).toBe(false);
  });

  it('a first demo load auto-selects the first section without user intent', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(demoPayload), { status: 200 })),
    );
    useSession.getState().setSelectedSection('S-02');
    await useSession.getState().loadDemo();
    expect(useSession.getState().selectedSection).toBe('S-01');
    expect(useSession.getState().selectedByUser).toBe(false);
  });

  it('exitDemo clears both the section and the flag', async () => {
    useSession.setState({ demoData: demoPayload });
    await useSession.getState().loadDemo();
    useSession.getState().setSelectedSection('S-03');
    useSession.getState().exitDemo();
    expect(useSession.getState().selectedSection).toBeNull();
    expect(useSession.getState().selectedByUser).toBe(false);
  });
});
