import { afterEach, expect, it, vi } from 'vitest';
import { useSession, type DemoData } from '../session';

afterEach(() => { useSession.getState().reset(); vi.unstubAllGlobals(); });

it('opens dashboard when reusing loaded demo data', async () => {
  useSession.setState({ demoData: { sections: [] } as unknown as DemoData });
  await useSession.getState().loadDemo();
  expect(useSession.getState().activeWorkspaceView).toBe('dashboard');
});

it('opens dashboard when fetching demo data for the first time', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ sections: [] }) }));
  await useSession.getState().loadDemo();
  expect(useSession.getState().activeWorkspaceView).toBe('dashboard');
});
