import { describe, expect, it, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MarkdownMessage } from '../MarkdownMessage';
import { normalizeContextSectionId } from '../useAgentChipActions';
import { useSession } from '../../../stores/session';
import { useBenchFocus } from '../../../stores/benchFocus';
import { initChatI18n, renderWithProviders } from './chatTestUtils';

vi.mock('../../../api/hooks', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../../api/hooks')>(),
  useSections: () => ({ data: [{ id: '0', name: 'S-37' }, { id: '1', name: 'S-38' }] }),
}));

const sections = [{ id: '0', name: 'S-37' }, { id: '1', name: 'S-38' }];

describe('normalizeContextSectionId', () => {
  it('uses a direct ID before a conflicting name', () => {
    expect(normalizeContextSectionId('0', [...sections, { id: '2', name: '0' }])).toBe('0');
  });

  it('resolves a unique demo name to its numeric ID', () => {
    expect(normalizeContextSectionId('S-37', sections)).toBe('0');
  });

  it('rejects duplicate names', () => {
    expect(normalizeContextSectionId('S-37', [...sections, { id: '2', name: 'S-37' }])).toBeNull();
  });

  it('rejects missing and null selections', () => {
    expect(normalizeContextSectionId('missing', sections)).toBeNull();
    expect(normalizeContextSectionId(null, sections)).toBeNull();
  });
});

describe('normalized context in MarkdownMessage', () => {
  it.each([true, false])('links a bench without a preceding mention with demoMode=%s', async (demoMode) => {
    initChatI18n();
    useSession.setState({ selectedSection: 'S-37', demoMode });
    renderWithProviders(<MarkdownMessage chips content="Revisa el banco 2" />);
    await userEvent.click(screen.getByTestId('ai-chat-chip-bench'));
    expect(useSession.getState().selectedSection).toBe('0');
    expect(useBenchFocus.getState().request).toMatchObject({ sectionId: '0', designBench: 2 });
  });
});
