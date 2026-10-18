import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useSession } from '../session';

beforeEach(() => {
  useSession.getState().reset();
});

describe('curve selection store no-ops', () => {
  it('preserves the root and does not notify for an unchanged context', () => {
    const state = useSession.getState();
    const listener = vi.fn();
    const unsubscribe = useSession.subscribe(listener);

    try {
      state.dispatchCurveSelection({ type: 'context', context: null });
      expect(useSession.getState()).toBe(state);
      expect(listener).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });

  it('preserves the root and does not notify for an unchanged design mesh', () => {
    useSession.getState().setDesignMeshId('design-1');
    const state = useSession.getState();
    const listener = vi.fn();
    const unsubscribe = useSession.subscribe(listener);

    try {
      state.setDesignMeshId('design-1');
      expect(useSession.getState()).toBe(state);
      expect(listener).not.toHaveBeenCalled();
    } finally {
      unsubscribe();
    }
  });
});
