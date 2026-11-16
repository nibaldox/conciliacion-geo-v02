import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../api/client', () => ({
  default: {
    get: vi.fn(),
    delete: vi.fn(),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => 'sess-panel-scroll',
}));

import { useAIChat } from '../aiChat';

beforeEach(() => {
  window.localStorage.clear();
  useAIChat.getState().reset();
});

describe('aiChat panel scroll memory', () => {
  it('starts empty and keeps the last panel position in memory', () => {
    expect(useAIChat.getState().panelScroll).toBeNull();
    useAIChat.getState().setPanelScroll({ top: 120, atBottom: false });
    expect(useAIChat.getState().panelScroll).toEqual({ top: 120, atBottom: false });
  });

  it('reset drops the saved position', () => {
    useAIChat.getState().setPanelScroll({ top: 120, atBottom: false });
    useAIChat.getState().reset();
    expect(useAIChat.getState().panelScroll).toBeNull();
  });

  it('clearing the conversation drops the saved position', async () => {
    useAIChat.getState().setPanelScroll({ top: 120, atBottom: false });
    await useAIChat.getState().clearConversation();
    expect(useAIChat.getState().panelScroll).toBeNull();
  });
});
