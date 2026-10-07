import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../locales/es.json';
import { useSession } from '../../../stores/session';
import { ViewsToolbar } from '../ViewsToolbar';

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

beforeEach(() => useSession.getState().reset());

describe('ViewsToolbar', () => {
  it('changes the workspace with a keyboard action and reports the active view', async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    render(<I18nextProvider i18n={i18n}><ViewsToolbar onNavigate={onNavigate} /></I18nextProvider>);
    const profiles = screen.getByRole('button', { name: 'Perfiles' });
    profiles.focus();
    await user.keyboard('{Enter}');
    expect(useSession.getState().activeWorkspaceView).toBe('profiles');
    expect(profiles).toHaveAttribute('aria-pressed', 'true');
    expect(onNavigate).toHaveBeenCalledOnce();
  });

  it('keeps every view accessible when the sidebar is collapsed', async () => {
    const user = userEvent.setup();
    render(<I18nextProvider i18n={i18n}><ViewsToolbar compact /></I18nextProvider>);
    expect(screen.getAllByRole('button')).toHaveLength(5);
    await user.click(screen.getByRole('button', { name: 'Dashboard' }));
    expect(useSession.getState().activeWorkspaceView).toBe('dashboard');
  });
});
