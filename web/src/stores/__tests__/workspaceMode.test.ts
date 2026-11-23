import { beforeEach, describe, expect, it } from 'vitest';
import { useWorkspaceMode } from '../workspaceMode';

describe('workspace mode', () => {
  beforeEach(() => {
    useWorkspaceMode.setState({ mode: 'protagonist', lastReason: 'initial' });
  });

  it('starts in protagonist mode', () => {
    expect(useWorkspaceMode.getState()).toMatchObject({ mode: 'protagonist', lastReason: 'initial' });
  });

  it('enters copilot idempotently while updating the reason', () => {
    useWorkspaceMode.getState().enterCopilot('meshesReady');
    useWorkspaceMode.getState().enterCopilot('manualView');
    expect(useWorkspaceMode.getState()).toMatchObject({ mode: 'copilot', lastReason: 'manualView' });
  });

  it('focuses the conversation', () => {
    useWorkspaceMode.getState().enterCopilot('demo');
    useWorkspaceMode.getState().focusConversation();
    expect(useWorkspaceMode.getState()).toMatchObject({ mode: 'protagonist', lastReason: 'focusConversation' });
  });

  it('resets for a session', () => {
    useWorkspaceMode.getState().resetForSession('copilot', 'resultsRestored');
    expect(useWorkspaceMode.getState()).toMatchObject({ mode: 'copilot', lastReason: 'resultsRestored' });
    useWorkspaceMode.getState().resetForSession('protagonist', 'newSession');
    expect(useWorkspaceMode.getState()).toMatchObject({ mode: 'protagonist', lastReason: 'newSession' });
  });
});
