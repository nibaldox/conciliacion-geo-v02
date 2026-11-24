import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatPanel } from '../ChatPanel';
import { historyToChatMessages, useAIChat, type ChatMessage } from '../../../stores/aiChat';
import { useSession } from '../../../stores/session';
import { renderWithProviders, initChatI18n } from './chatTestUtils';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { I18nextProvider } from 'react-i18next';
import { useWorkspaceMode } from '../../../stores/workspaceMode';
import { useBenchFocus } from '../../../stores/benchFocus';
const guidanceMocks = vi.hoisted(() => ({
  sections: [] as Array<{ id: string; name: string }>,
  workflow: {
    hasDesign: false,
    hasTopo: false,
    surfacesDone: false,
    sectionCount: 0,
    sectionsDone: false,
    isProcessing: false,
    isComplete: false,
    steps: { surfaces: 'current', sections: 'locked', parameters: 'locked', process: 'locked' },
    projectStatus: 'empty',
    nextStep: 'surfaces',
  },
}));

vi.mock('../../../hooks/useWorkflowStatus', () => ({
  useWorkflowStatus: () => guidanceMocks.workflow,
}));
vi.mock('../../../api/hooks', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/hooks')>();
  return {
    ...actual,
    useSections: () => ({ data: guidanceMocks.sections, isLoading: false }),
  };
});
vi.mock('../../../api/client', () => ({ default: { get: vi.fn(async () => ({ data: {} })), post: vi.fn(), defaults: { baseURL: '/api/v1' } }, getSessionId: () => 'test' }));

const tool = (id: string, status: 'ok' | 'error' | 'running' = 'ok'): ChatMessage => ({ kind: 'tool', id, invocationId: id, name: 'query_results', status, summary: 'Detalle', error: status === 'error' ? 'Fallo específico' : null });
beforeEach(() => {
  useAIChat.getState().reset();
  useSession.getState().reset();
  guidanceMocks.sections = [];
  guidanceMocks.workflow = {
    hasDesign: false,
    hasTopo: false,
    surfacesDone: false,
    sectionCount: 0,
    sectionsDone: false,
    isProcessing: false,
    isComplete: false,
    steps: { surfaces: 'current', sections: 'locked', parameters: 'locked', process: 'locked' },
    projectStatus: 'empty',
    nextStep: 'surfaces',
  };
  vi.spyOn(useAIChat.getState(), 'init').mockResolvedValue();
});

it('agrupa herramientas consecutivas sin ocultar confirmaciones ni respuestas y mantiene el control explícito', async () => {
  const messages: ChatMessage[] = [tool('a'), tool('b', 'error'), { kind: 'confirmation', id: 'c', invocationId: 'c', name: 'x', argsSummary: 'Confirmación visible', resolution: 'pending' }, tool('d', 'running'), { kind: 'agent', id: 'e', text: 'Respuesta visible' }];
  useAIChat.setState({ messages });
  renderWithProviders(<ChatPanel presentation="embedded" />);
  const groups = screen.getAllByRole('button', { name: /Actividad del agente/ });
  expect(groups).toHaveLength(2);
  expect(groups[0]).toHaveAttribute('aria-expanded', 'true');
  expect(groups[0]).toHaveTextContent('2');
  expect(groups[0]).toHaveTextContent(/error/i);
  const steps = screen.getAllByRole('button', { name: /Consultar resultados/ });
  expect(steps).toHaveLength(3);
  expect(steps[1]).toHaveTextContent('Error');
  expect(screen.getByText('Confirmación visible')).toBeVisible();
  expect(screen.getByText('Respuesta visible')).toBeVisible();
  await userEvent.click(steps[1]);
  expect(screen.getByText('Fallo específico')).toBeVisible();
  await userEvent.click(groups[0]);
  expect(groups[0]).toHaveAttribute('aria-expanded', 'false');
  expect(steps[0]).not.toBeVisible();
  expect(screen.getByText('Confirmación visible')).toBeVisible();
  expect(screen.getByText('Respuesta visible')).toBeVisible();
  act(() => useAIChat.setState({ messages: [...messages, { kind: 'agent', id: 'f', text: 'continuación' }] }));
  expect(groups[0]).toHaveAttribute('aria-expanded', 'false');
  groups[0].focus();
  await userEvent.keyboard('{Enter}');
  expect(groups[0]).toHaveAttribute('aria-expanded', 'true');
  expect(steps[0]).toBeVisible();
  expect(screen.getByText('Fallo específico')).toBeVisible();
});

it('identifica Diseño como siguiente paso sin duplicar controles de carga', () => {
  renderWithProviders(<ChatPanel presentation="embedded" />);
  expect(screen.getByTestId('ai-chat-guidance')).toHaveTextContent(/Falta la superficie de Diseño/);
  expect(screen.queryByRole('button', { name: 'Cargar diseño' })).toBeNull();
  expect(screen.getByRole('button', { name: /Superficies/ })).toBeVisible();
});

it('ofrece un borrador sin enviar ni sobrescribir lo escrito', async () => {
  const send = vi.fn();
  useAIChat.setState({ providerStateLoaded: true, send });
  renderWithProviders(<ChatPanel presentation="embedded" layout="protagonist" />);
  const starter = screen.getByRole('button', { name: 'Guiarme para conciliar' });
  const input = screen.getByTestId('ai-chat-input');
  await userEvent.type(input, 'Mi borrador');
  await userEvent.click(starter);
  expect(input).toHaveValue('Mi borrador');
  await userEvent.clear(input);
  await userEvent.click(starter);
  expect((input as HTMLInputElement).value).toMatch(/un archivo a la vez.*si faltan ambas.*Diseño.*si falta una.*No generes secciones ni ejecutes el análisis/i);
  expect(send).not.toHaveBeenCalled();
  expect(within(screen.getByTestId('ai-chat-panel')).getByRole('button', { name: /Superficies/ })).toBeVisible();
});


it('muestra la descarga al abrir el paso y conserva foco y posición de lectura', async () => {
  useAIChat.setState({ messages: [{ kind: 'tool', id: 'export', invocationId: 'export', name: 'export_report', status: 'ok', summary: null, error: null, download: { format: 'excel', query: { filters: '{"sector":["Norte"]}' } } }] });
  renderWithProviders(<ChatPanel presentation="embedded" />);
  const group = screen.getByRole('button', { name: /Actividad del agente/ });
  const list = screen.getByTestId('ai-chat-messages').parentElement!;
  Object.defineProperties(list, { scrollHeight: { configurable: true, value: 1000 }, clientHeight: { configurable: true, value: 200 } });
  list.scrollTop = 100;
  fireEvent.scroll(list);
  expect(group).toHaveAttribute('aria-expanded', 'true');
  const step = screen.getByRole('button', { name: /Exportar informe/ });
  expect(step).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByTestId('ai-chat-tool-download')).not.toBeVisible();
  step.focus();
  await userEvent.keyboard(' ');
  expect(step).toHaveFocus();
  expect(screen.getByTestId('ai-chat-tool-download')).toBeVisible();
  expect(group).not.toContainElement(screen.getByTestId('ai-chat-tool-download'));
  act(() => useAIChat.setState({ messages: [...useAIChat.getState().messages, { kind: 'agent', id: 'reply', text: 'texto nuevo' }] }));
  expect(list.scrollTop).toBe(100);
  expect(step).toHaveFocus();
});


it('distingue historial sin estado inequívoco de errores vivos y con código', async () => {
  const restored = historyToChatMessages([
    { role: 'assistant', content: '', tools: ['get_workflow_state', 'list_meshes', 'export_report', 'get_profile'] },
    { role: 'tool', ok: false, summary: '', error: null },
    { role: 'tool', ok: false, summary: 'datos', error: null },
    { role: 'tool', ok: false, summary: '', error: 'failure_code' },
    { role: 'tool', ok: true, summary: 'Listo', error: null },
  ]);
  const live: ChatMessage = { kind: 'tool', id: 'live', invocationId: 'inv_live', name: 'query_results', status: 'error', summary: null, error: null };
  useAIChat.setState({ messages: [...restored, live] });
  renderWithProviders(<ChatPanel presentation="embedded" />);
  const group = screen.getByRole('button', { name: /Actividad del agente/ });
  expect(group).toHaveTextContent('Error');
  expect(group).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getAllByText(/Sin estado registrado/)).toHaveLength(2);
  expect(screen.getByRole('button', { name: /Consultar resultados/ }).textContent).toMatch(/Consultar resultados.*Error/);
  const exportStep = screen.getByRole('button', { name: /Exportar informe/ });
  expect(exportStep.textContent).toMatch(/Exportar informe.*Error/);
  expect(screen.getByRole('button', { name: /Consultar perfil/ }).textContent).toMatch(/Consultar perfil.*Completado/);
  await userEvent.click(exportStep);
  expect(screen.getByText('failure_code')).toBeVisible();
  expect(screen.queryByTestId('ai-chat-tool-download')).toBeNull();
});

it('resume de forma neutral un grupo restaurado ambiguo', async () => {
  useAIChat.setState({ messages: historyToChatMessages([{ role: 'assistant', content: '', tools: ['get_workflow_state', 'list_meshes'] }, { role: 'tool', ok: false, summary: '', error: null }, { role: 'tool', ok: false, summary: '', error: null }]) });
  renderWithProviders(<ChatPanel presentation="embedded" />);
  const group = screen.getByRole('button', { name: /Actividad del agente/ });
  expect(group).toHaveTextContent('Sin estado registrado');
  expect(group).not.toHaveTextContent(/Error|Completado/);
});


it('mantiene el modelo largo accesible bajo un control compacto en embedded', async () => {
  const model = 'modelo-tecnico-con-un-identificador-muy-largo-de-mas-de-45-caracteres';
  useAIChat.setState({ providerStateLoaded: true, providerState: { providers: ['lmstudio'], supports_tool_calls: { lmstudio: true }, chat_enabled: true, chat_provider: 'lmstudio', chat_local_only: true, chat_model: model } });
  renderWithProviders(<ChatPanel presentation="embedded" />);
  const control = screen.getByText('Modelo', { selector: 'summary' });
  expect(control.closest('details')).not.toHaveAttribute('open');
  await userEvent.click(control);
  expect(screen.getByTestId('ai-chat-model-chip')).toHaveTextContent(model);
  expect(screen.getByTestId('ai-chat-model-chip')).toBeVisible();
  expect(screen.getByTestId('ai-chat-status')).toHaveTextContent('CONFIGURADO');
});


it('presenta bienvenida protagonista y conserva el textarea, caret y log al cambiar de layout', async () => {
  useAIChat.setState({ providerStateLoaded: true });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = (layout: 'protagonist' | 'copilot') => <QueryClientProvider client={client}><I18nextProvider i18n={initChatI18n()}><ChatPanel presentation="embedded" layout={layout} /></I18nextProvider></QueryClientProvider>;
  const { rerender } = render(wrap('protagonist'));
  expect(screen.getByText('Hola, comencemos.')).toBeVisible();
  expect(screen.getByTestId('ai-chat-guidance')).toBeVisible();
  const input = screen.getByTestId('ai-chat-input') as HTMLTextAreaElement;
  expect(input.rows).toBeGreaterThanOrEqual(3);
  await userEvent.type(input, 'borrador');
  input.setSelectionRange(2, 4);
  const log = screen.getByRole('log');
  rerender(wrap('copilot'));
  expect(screen.getByTestId('ai-chat-input')).toBe(input);
  expect(input).toHaveValue('borrador');
  expect(input.selectionStart).toBe(2);
  expect(input.selectionEnd).toBe(4);
  expect(screen.getByRole('log')).toBe(log);
  expect(screen.getByText('Agente · Sesión nueva')).toBeVisible();
});

it('prioriza aprobación sobre herramienta y permite enfocar la conversación', async () => {
  useAIChat.setState({ messages: [tool('running', 'running')], pendingConfirmation: { invocationId: 'x', name: 'x', argsSummary: 'test' } });
  useWorkspaceMode.getState().enterCopilot('manualView');
  renderWithProviders(<ChatPanel presentation="embedded" layout="copilot" />);
  expect(screen.getByText(/Esperando tu aprobación/)).toBeVisible();
  act(() => useAIChat.setState({ pendingConfirmation: null }));
  expect(screen.getByText(/Usando herramientas…/)).toBeVisible();
  await userEvent.click(screen.getByTestId('ai-chat-focus-conversation'));
  expect(useWorkspaceMode.getState().mode).toBe('protagonist');
});

it('muestra el contexto de dashboard, grilla y perfil con banco seleccionado', () => {
  guidanceMocks.sections = [{ id: '37', name: 'S-37' }];
  useSession.setState({ activeWorkspaceView: 'dashboard', selectedSection: '37', selectedByUser: true });
  renderWithProviders(<ChatPanel presentation="embedded" layout="copilot" />);
  expect(screen.getByTestId('ai-chat-context-chip')).toHaveTextContent(/Dashboard · S-37/);
  act(() => useSession.setState({ activeWorkspaceView: 'profiles', profilesMode: 'grid' }));
  expect(screen.getByTestId('ai-chat-context-chip')).toHaveTextContent(/Perfiles · grilla/);
  act(() => { useSession.setState({ profilesMode: 'detail' }); useBenchFocus.getState().publishCurrent({ sectionId: '37', benchNumber: 1, designBenchNumber: 2 }); });
  expect(screen.getByTestId('ai-chat-context-chip')).toHaveTextContent(/Perfil S-37 · Banco 2/);
});


it('ubica la sugerencia después del compositor solo en protagonista y no en la guía', () => {
  useAIChat.setState({ providerStateLoaded: true });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = (layout: 'protagonist' | 'copilot') => <QueryClientProvider client={client}><I18nextProvider i18n={initChatI18n()}><ChatPanel presentation="embedded" layout={layout} /></I18nextProvider></QueryClientProvider>;
  const { rerender } = render(wrap('protagonist'));
  const starter = screen.getByRole('button', { name: 'Guiarme para conciliar' });
  expect(screen.getAllByRole('button', { name: 'Guiarme para conciliar' })).toHaveLength(1);
  expect(screen.getByTestId('ai-chat-guidance')).not.toContainElement(starter);
  expect(screen.getByTestId('ai-chat-composer').compareDocumentPosition(starter) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  rerender(wrap('copilot'));
  expect(screen.queryByRole('button', { name: 'Guiarme para conciliar' })).toBeNull();
});

it('conserva la posición de lectura al cambiar de layout en ambos sentidos', () => {
  useAIChat.setState({ messages: [{ kind: 'user', id: 'scroll', text: 'Texto de lectura' }] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrap = (layout: 'protagonist' | 'copilot') => <QueryClientProvider client={client}><I18nextProvider i18n={initChatI18n()}><ChatPanel presentation="embedded" layout={layout} /></I18nextProvider></QueryClientProvider>;
  const { rerender } = render(wrap('protagonist'));
  const list = screen.getByRole('log').parentElement!;
  Object.defineProperties(list, { scrollHeight: { configurable: true, value: 1000 }, clientHeight: { configurable: true, value: 200 } });
  list.scrollTop = 123;
  fireEvent.scroll(list);
  rerender(wrap('copilot'));
  expect(screen.getByRole('log').parentElement).toBe(list);
  expect(list.scrollTop).toBe(123);
  rerender(wrap('protagonist'));
  expect(list.scrollTop).toBe(123);
});

it('resuelve la sección por id o nombre único y rechaza nombres duplicados', () => {
  guidanceMocks.sections = [{ id: '0', name: 'S-37' }, { id: '1', name: 'S-38' }];
  useSession.setState({ activeWorkspaceView: 'profiles', profilesMode: 'detail', selectedSection: '0', selectedByUser: true });
  useBenchFocus.getState().publishCurrent({ sectionId: '0', benchNumber: 1, designBenchNumber: 2 });
  renderWithProviders(<ChatPanel presentation="embedded" layout="copilot" />);
  expect(screen.getByTestId('ai-chat-context-chip')).toHaveTextContent('Perfil S-37 · Banco 2');
  act(() => useSession.setState({ selectedSection: 'S-37' }));
  expect(screen.getByTestId('ai-chat-context-chip')).toHaveTextContent('Perfil S-37 · Banco 2');
  guidanceMocks.sections = [{ id: '0', name: 'S-37' }, { id: '1', name: 'S-37' }];
  act(() => useSession.setState({ profilesMode: 'grid' }));
  act(() => useSession.setState({ profilesMode: 'detail' }));
  expect(screen.getByTestId('ai-chat-context-chip')).not.toHaveTextContent(/S-37|Banco 2/);
});

it('renderiza chips reales solo en el mensaje del agente embebido', () => {
  guidanceMocks.sections = [{ id: '37', name: 'S-37' }];
  useAIChat.setState({ messages: [{ kind: 'agent', id: 'agent-chip', text: 'S-37 presenta banco 2' }, { kind: 'user', id: 'user-chip', text: 'S-37 presenta banco 2' }] });
  renderWithProviders(<ChatPanel presentation="embedded" />);
  const agent = document.querySelector('[data-slot="ai-chat-message"][data-kind="agent"]') as HTMLElement;
  const user = document.querySelector('[data-slot="ai-chat-message"][data-kind="user"]') as HTMLElement;
  expect(within(agent).getByTestId('ai-chat-chip-section')).toBeVisible();
  expect(within(agent).getByRole('button', { name: /banco 2/i })).toBeVisible();
  expect(within(user).queryAllByRole('button')).toHaveLength(0);
  expect(user).toHaveTextContent('S-37 presenta banco 2');
});
