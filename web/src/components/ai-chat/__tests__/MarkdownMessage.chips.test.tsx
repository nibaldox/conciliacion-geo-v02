import { describe, expect, it, vi } from 'vitest';
import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MarkdownMessage } from '../MarkdownMessage';
import { useWorkspaceMode } from '../../../stores/workspaceMode';
import { useSession } from '../../../stores/session';
import { useBenchFocus } from '../../../stores/benchFocus';
import { initChatI18n, renderWithProviders } from './chatTestUtils';

vi.mock('../../../api/hooks', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../../api/hooks')>(),
  useSections: () => ({ data: [{ id: '0', name: 'S-37' }, { id: '1', name: 'S-12' }, { id: '2', name: 'S-1' }, { id: '3', name: 'S-1' }] }),
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

describe('visible message attribution', () => {
  it.each(['`S-12`', '[S-12](https://example.com)', '**S-12**'])('uses preceding mention %s', async (mention) => {
    initChatI18n();
    useWorkspaceMode.setState({ mode: 'copilot' });
    useSession.setState({ selectedSection: '0', activeWorkspaceView: 'profiles', profilesMode: 'detail' });
    renderWithProviders(<MarkdownMessage chips content={`${mention} banco 2`} />);
    await userEvent.click(screen.getByTestId('ai-chat-chip-bench'));
    expect(useBenchFocus.getState().request?.sectionId).toBe('1');
  });
  it.each(['**S-1**', '`S-1`', '[S-1](https://example.com)'])('blocks ambiguous mention %s', (mention) => {
    useWorkspaceMode.setState({ mode: 'copilot' });
    useSession.setState({ selectedSection: '0', activeWorkspaceView: 'profiles', profilesMode: 'detail' });
    renderWithProviders(<MarkdownMessage chips content={`${mention} banco 2`} />);
    expect(screen.queryByTestId('ai-chat-chip-bench')).toBeNull();
  });
  it('freezes context after first resolution', async () => {
    useWorkspaceMode.setState({ mode: 'copilot' });
    useSession.setState({ selectedSection: '0', activeWorkspaceView: 'profiles', profilesMode: 'detail' });
    renderWithProviders(<MarkdownMessage chips content="banco 2" />);
    act(() => useSession.setState({ selectedSection: '1' }));
    await userEvent.click(screen.getByTestId('ai-chat-chip-bench'));
    expect(useBenchFocus.getState().request?.sectionId).toBe('0');
  });
  it('does not chip table headers', () => {
    renderWithProviders(<MarkdownMessage chips content={'| S-12 banco 2 |\n| --- |\n| S-37 |'} />);
    expect(document.querySelector('th button')).toBeNull();
  });
});
