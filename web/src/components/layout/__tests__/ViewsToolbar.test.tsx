import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../locales/es.json';
import { useSession } from '../../../stores/session';

const apiState = vi.hoisted(() => ({
  sections: [] as { id: string }[],
  status: undefined as { status: string } | undefined,
}));

vi.mock('../../../api/hooks', () => ({
  useSections: () => ({ data: apiState.sections }),
  useProcessStatus: () => ({ data: apiState.status }),
}));

import { ViewsToolbar } from '../ViewsToolbar';

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

function renderToolbar(onNavigate?: () => void) {
  return render(<I18nextProvider i18n={i18n}><ViewsToolbar onNavigate={onNavigate} /></I18nextProvider>);
}

beforeEach(() => {
  useSession.getState().reset();
  apiState.sections = [];
  apiState.status = undefined;
});

describe('ViewsToolbar', () => {
  it('renders the views as tabs in workflow order with hotkey badges', () => {
    renderToolbar();
    expect(screen.getByRole('navigation', { name: 'Vistas de análisis' })).toHaveAttribute('data-slot', 'views-toolbar');
    const tabs = screen.getAllByRole('tab');
    expect(tabs.map((tab) => tab.getAttribute('aria-label'))).toEqual(['Dashboard', 'Perfiles', 'Vista 3D', 'Tronadura', 'Exportar']);
    expect(tabs.map((tab) => tab.querySelector('kbd')?.textContent)).toEqual(['1', '2', '3', '4', '5']);
    expect(tabs[1].querySelector('kbd')).toHaveAttribute('title', 'Atajo: 2');
  });

  it('changes the workspace with a keyboard action and reports the active view', async () => {
    const user = userEvent.setup();
    const onNavigate = vi.fn();
    renderToolbar(onNavigate);
    const profiles = screen.getByRole('tab', { name: 'Perfiles' });
    profiles.focus();
    await user.keyboard('{Enter}');
    expect(useSession.getState().activeWorkspaceView).toBe('profiles');
    expect(profiles).toHaveAttribute('aria-selected', 'true');
    expect(profiles).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('tab', { name: 'Vista 3D' })).toHaveAttribute('aria-selected', 'false');
    expect(onNavigate).toHaveBeenCalledOnce();
  });

  it('moves between tabs with the arrow keys', async () => {
    const user = userEvent.setup();
    renderToolbar();
    screen.getByRole('tab', { name: 'Vista 3D' }).focus();
    await user.keyboard('{ArrowLeft}');
    expect(useSession.getState().activeWorkspaceView).toBe('profiles');
    expect(screen.getByRole('tab', { name: 'Perfiles' })).toHaveFocus();
    await user.keyboard('{Home}');
    expect(useSession.getState().activeWorkspaceView).toBe('dashboard');
    await user.keyboard('{End}');
    expect(useSession.getState().activeWorkspaceView).toBe('export-ai');
  });

  it('marks analysis views as locked until processing is complete but keeps them clickable', async () => {
    const user = userEvent.setup();
    renderToolbar();
    expect(screen.getByRole('tab', { name: 'Vista 3D' })).not.toHaveAttribute('data-locked');
    for (const name of ['Perfiles', 'Dashboard', 'Tronadura', 'Exportar']) {
      const tab = screen.getByRole('tab', { name });
      expect(tab).toHaveAttribute('data-locked', 'true');
      expect(tab).toHaveAttribute('title', 'Requiere completar el flujo');
    }
    await user.click(screen.getByRole('tab', { name: 'Dashboard' }));
    expect(useSession.getState().activeWorkspaceView).toBe('dashboard');
  });

  it('shows the active styling on a tab that is both active and locked', async () => {
    const user = userEvent.setup();
    renderToolbar();
    const profiles = screen.getByRole('tab', { name: 'Perfiles' });
    await user.click(profiles);
    expect(profiles).toHaveAttribute('data-locked', 'true');
    expect(profiles).toHaveAttribute('data-active', 'true');
    expect(profiles).toHaveAttribute('aria-selected', 'true');
    expect(profiles).toHaveClass('border-accent-bright', 'text-accent-bright');
    expect(profiles).not.toHaveClass('opacity-60');
    expect(profiles.querySelector('[data-slot="view-lock"]')).not.toBeNull();
    const view3d = screen.getByRole('tab', { name: 'Vista 3D' });
    expect(view3d).not.toHaveAttribute('data-active');
    expect(view3d).not.toHaveClass('border-accent-bright');
    expect(screen.getByRole('tab', { name: 'Dashboard' })).toHaveClass('opacity-60');
  });

  it('unlocks every view once the analysis is complete', () => {
    useSession.setState({ designMeshId: 'design', topoMeshId: 'topo' });
    apiState.sections = [{ id: 'section-1' }];
    apiState.status = { status: 'complete' };
    renderToolbar();
    for (const tab of screen.getAllByRole('tab')) {
      expect(tab).not.toHaveAttribute('data-locked');
    }
    expect(screen.getByRole('tab', { name: 'Dashboard' })).toHaveAttribute('title', 'Dashboard');
  });
});
