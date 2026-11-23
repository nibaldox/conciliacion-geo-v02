import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MarkdownMessage } from '../MarkdownMessage';
import { useSession } from '../../../stores/session';
import { useBenchFocus } from '../../../stores/benchFocus';
import { initChatI18n, renderWithProviders } from './chatTestUtils';

vi.mock('../../../api/hooks', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../../api/hooks')>(),
  useSections: () => ({ data: [{ id: '0', name: 'S-37' }] }),
}));

describe('agent chips', () => {
  it('links sections and benches across emphasis, not code, links or headings', async () => {
    initChatI18n();
    useSession.setState({ selectedSection: null, demoMode: true });
    const { container } = renderWithProviders(<MarkdownMessage chips content={'# S-37\n\n**S-37** · el banco 2; `S-37` [S-37](https://example.com) <img src=x onerror=alert(1)> [bad](javascript:alert(1))'} />);
    expect(screen.getAllByTestId('ai-chat-chip-section')).toHaveLength(1);
    expect(screen.getAllByTestId('ai-chat-chip-bench')).toHaveLength(1);
    expect(container.querySelector('img, [onerror], a[href^="javascript:"]')).toBeNull();
    await userEvent.click(screen.getByTestId('ai-chat-chip-bench'));
    expect(useSession.getState()).toMatchObject({ selectedSection: '0', profilesMode: 'detail', activeWorkspaceView: 'profiles' });
    expect(useBenchFocus.getState().request).toMatchObject({ sectionId: '0', designBench: 2 });
  });
  it('does not link without chips enabled', () => {
    const { container } = renderWithProviders(<MarkdownMessage content="S-37 banco 2" />);
    expect(container.querySelector('button')).toBeNull();
  });
});

describe('section navigation', () => {
  it.each([true, false])('opens section by ID with demoMode=%s', async (demoMode) => {
    initChatI18n();
    useSession.setState({ selectedSection: null, demoMode });
    renderWithProviders(<MarkdownMessage chips content="S-37" />);
    await userEvent.click(screen.getByTestId('ai-chat-chip-section'));
    expect(useSession.getState()).toMatchObject({ selectedSection: '0', profilesMode: 'detail', activeWorkspaceView: 'profiles' });
  });
});
