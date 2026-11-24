import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AppLayout } from '../AppLayout';
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock('../Header', () => ({ Header: () => <header /> }));
vi.mock('../LeftSidebar', () => ({ LeftSidebar: () => <aside /> }));
vi.mock('../ViewsToolbar', () => ({ ViewsToolbar: () => <nav data-slot="views-toolbar" /> }));
vi.mock('../../demo/DemoBanner', () => ({ DemoBanner: () => null }));
vi.mock('../../ai-chat/AgentWorkspaceShell', () => ({ AgentWorkspaceShell: ({ children, canvasHeader }: { children: React.ReactNode; canvasHeader: React.ReactNode }) => <div data-testid="shell">{canvasHeader}{children}</div> }));
describe('AppLayout canvas header', () => {
  it('places title and toolbar inside the assistant shell', () => {
    const { container } = render(<AppLayout assistant><div>view</div></AppLayout>);
    const shell = screen.getByTestId('shell');
    expect(shell.querySelector('[data-slot="step-title-bar"]')).toBeTruthy();
    expect(shell.querySelector('[data-slot="views-toolbar"]')).toBeTruthy();
    expect(container.querySelectorAll('#main-content')).toHaveLength(1);
  });
  it('retains the title and toolbar without assistant', () => {
    const { container } = render(<AppLayout><div>view</div></AppLayout>);
    expect(screen.queryByTestId('shell')).toBeNull();
    expect(container.querySelectorAll('[data-slot="step-title-bar"]')).toHaveLength(1);
    expect(container.querySelectorAll('[data-slot="views-toolbar"]')).toHaveLength(1);
  });
});
