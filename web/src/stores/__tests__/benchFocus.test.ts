import { beforeEach, describe, expect, it } from 'vitest';
import { useBenchFocus } from '../benchFocus';

describe('benchFocus', () => {
  beforeEach(() => useBenchFocus.setState({ request: null, current: null }));

  it('generates increasing nonces and ignores stale consumption', () => {
    useBenchFocus.getState().requestBench('a', 1);
    const first = useBenchFocus.getState().request!;
    useBenchFocus.getState().requestBench('a', 2);
    const second = useBenchFocus.getState().request!;
    expect(second.nonce).toBeGreaterThan(first.nonce);
    useBenchFocus.getState().consumeRequest(first.nonce);
    expect(useBenchFocus.getState().request).toEqual(second);
    useBenchFocus.getState().consumeRequest(second.nonce);
    expect(useBenchFocus.getState().request).toBeNull();
  });

  it('publishes and clears the current bench', () => {
    const current = { sectionId: 'a', benchNumber: 4, designBenchNumber: null };
    useBenchFocus.getState().publishCurrent(current);
    expect(useBenchFocus.getState().current).toEqual(current);
    useBenchFocus.getState().publishCurrent(null);
    expect(useBenchFocus.getState().current).toBeNull();
  });
});
