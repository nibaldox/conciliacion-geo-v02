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
    expect(profiles).toHaveAttribute('aria-current', 'page');
    expect(onNavigate).toHaveBeenCalledOnce();
  });

  it('shows translated view names when the sidebar is expanded', () => {
    render(<I18nextProvider i18n={i18n}><ViewsToolbar /></I18nextProvider>);
    expect(screen.getByText('Perfiles')).toBeVisible();
    expect(screen.getByText('Vista 3D')).toBeVisible();
    expect(screen.getByText('Resumen')).toBeVisible();
    expect(screen.getByText('Tronadura')).toBeVisible();
    expect(screen.getByText('Exportar')).toBeVisible();
  });

  it('keeps every view accessible when the sidebar is collapsed', async () => {
    const user = userEvent.setup();
    render(<I18nextProvider i18n={i18n}><ViewsToolbar compact /></I18nextProvider>);
    expect(screen.getAllByRole('button')).toHaveLength(5);
    const dashboard = screen.getByRole('button', { name: 'Dashboard' });
    expect(dashboard).toHaveAttribute('title', 'Resumen');
    expect(dashboard).toHaveClass('focus-visible:ring-2');
    await user.click(dashboard);
    expect(useSession.getState().activeWorkspaceView).toBe('dashboard');
    expect(dashboard).toHaveAttribute('aria-current', 'page');
  });
});
