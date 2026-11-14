import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useAIChat } from '../../../stores/aiChat';
import { derivePetState, usePetState, DONE_HOLD_MS } from '../petState';

const base = { streaming: false, sendInFlight: false, messages: [], pendingConfirmation: null, notice: null, providerStateLoaded: false, chatEnabled: false, supportsTools: true, unread: false, justFinished: false };

describe('derivePetState', () => {
  it('prioritizes confirmation over an active turn', () => {
    expect(derivePetState({ ...base, streaming: true, pendingConfirmation: { invocationId: '1', name: 'tool', argsSummary: '' } })).toBe('confirm');
  });
  it('returns thinking during a turn', () => {
    expect(derivePetState({ ...base, streaming: true })).toBe('thinking');
  });
  it('returns off only after provider state loads', () => {
    expect(derivePetState(base)).toBe('idle');
    expect(derivePetState({ ...base, providerStateLoaded: true })).toBe('off');
  });
});


describe('state priority and completion', () => {
  afterEach(() => { vi.useRealTimers(); useAIChat.getState().reset(); });
  it('orders tool, thinking, error, done, unread and off', () => {
    const tool = { kind: 'tool' as const, id: '1', invocationId: '1', name: 'x', status: 'running' as const, summary: null, error: null };
    const confirmation = { kind: 'confirmation' as const, id: '2', invocationId: '2', name: 'x', argsSummary: '', resolution: 'pending' as const };
    const all = { ...base, streaming: true, messages: [tool], notice: { severity: 'error' as const, key: 'x' }, justFinished: true, unread: true, providerStateLoaded: true };
    expect(derivePetState({ ...all, messages: [tool, confirmation] })).toBe('confirm');
    expect(derivePetState(all)).toBe('tool');
    expect(derivePetState({ ...all, messages: [] })).toBe('thinking');
    expect(derivePetState({ ...all, streaming: false })).toBe('error');
    expect(derivePetState({ ...all, streaming: false, notice: null })).toBe('done');
    expect(derivePetState({ ...all, streaming: false, notice: null, justFinished: false })).toBe('unread');
    expect(derivePetState({ ...all, streaming: false, notice: null, justFinished: false, unread: false })).toBe('off');
    expect(derivePetState({ ...base, sendInFlight: true, messages: [tool] })).toBe('tool');
    expect(derivePetState({ ...base, providerStateLoaded: true, chatEnabled: true, supportsTools: false })).toBe('off');
  });
  it('holds done for 2400ms and cancels it when a new turn starts', () => {
    vi.useFakeTimers();
    useAIChat.getState().reset();
    const { result, unmount } = renderHook(() => usePetState({ unread: false }));
    act(() => useAIChat.setState({ streaming: true }));
    expect(result.current).toBe('thinking');
    act(() => useAIChat.setState({ streaming: false }));
    expect(result.current).toBe('done');
    act(() => vi.advanceTimersByTime(DONE_HOLD_MS - 1));
    expect(result.current).toBe('done');
    act(() => vi.advanceTimersByTime(1));
    expect(result.current).toBe('idle');
    act(() => useAIChat.setState({ sendInFlight: true }));
    act(() => useAIChat.setState({ sendInFlight: false }));
    expect(result.current).toBe('done');
    act(() => useAIChat.setState({ sendInFlight: true }));
    expect(result.current).toBe('thinking');
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });
  it('does not report done after a turn ending with an error', () => {
    vi.useFakeTimers();
    useAIChat.getState().reset();
    const { result } = renderHook(() => usePetState({ unread: false }));
    act(() => useAIChat.setState({ streaming: true }));
    act(() => useAIChat.setState({ streaming: false, notice: { severity: 'error', key: 'x' } }));
    expect(result.current).toBe('error');
    expect(vi.getTimerCount()).toBe(0);
  });
});
