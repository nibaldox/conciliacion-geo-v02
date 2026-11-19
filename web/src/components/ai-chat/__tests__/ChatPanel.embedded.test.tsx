import { beforeEach, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChatPanel } from '../ChatPanel';
import { historyToChatMessages, useAIChat, type ChatMessage } from '../../../stores/aiChat';
import { useSession } from '../../../stores/session';
import { renderWithProviders } from './chatTestUtils';
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
  expect(groups[0]).toHaveAttribute('aria-expanded', 'false');
  expect(groups[0]).toHaveTextContent('2');
  expect(groups[0]).toHaveTextContent(/error/i);
  expect(screen.getByText('Confirmación visible')).toBeVisible();
  expect(screen.getByText('Respuesta visible')).toBeVisible();
  await userEvent.click(groups[0]);
  expect(groups[0]).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getByText('Fallo específico')).toBeVisible();
  act(() => useAIChat.setState({ messages: [...messages, { kind: 'agent', id: 'f', text: 'continuación' }] }));
  expect(groups[0]).toHaveAttribute('aria-expanded', 'true');
  groups[0].focus();
  await userEvent.keyboard('{Enter}');
  expect(groups[0]).toHaveAttribute('aria-expanded', 'false');
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
  renderWithProviders(<ChatPanel presentation="embedded" />);
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


it('muestra la descarga directamente al abrir el grupo y conserva foco y posición de lectura', async () => {
  useAIChat.setState({ messages: [{ kind: 'tool', id: 'export', invocationId: 'export', name: 'export_report', status: 'ok', summary: null, error: null, download: { format: 'excel', query: { filters: '{"sector":["Norte"]}' } } }] });
  renderWithProviders(<ChatPanel presentation="embedded" />);
  const group = screen.getByRole('button', { name: /Actividad del agente/ });
  const list = screen.getByTestId('ai-chat-messages').parentElement!;
  Object.defineProperties(list, { scrollHeight: { configurable: true, value: 1000 }, clientHeight: { configurable: true, value: 200 } });
  list.scrollTop = 100;
  fireEvent.scroll(list);
  group.focus();
  await userEvent.keyboard(' ');
  expect(group).toHaveFocus();
  expect(screen.getByTestId('ai-chat-tool-download')).toBeVisible();
  expect(group).not.toContainElement(screen.getByTestId('ai-chat-tool-download'));
  act(() => useAIChat.setState({ messages: [...useAIChat.getState().messages, { kind: 'agent', id: 'reply', text: 'texto nuevo' }] }));
  expect(list.scrollTop).toBe(100);
  expect(group).toHaveFocus();
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
  await userEvent.click(group);
  expect(screen.getAllByText(/Sin estado registrado/)).toHaveLength(2);
  expect(screen.getByText(/Consultar resultados · Error/)).toBeVisible();
  expect(screen.getByText(/Exportar informe · Error/)).toBeVisible();
  expect(screen.getByText(/Consultar perfil · Completado/)).toBeVisible();
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
