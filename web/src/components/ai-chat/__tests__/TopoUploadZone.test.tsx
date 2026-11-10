import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const { mockGet, mockPost, mockDelete, mockGetSessionId } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDelete: vi.fn(),
  mockGetSessionId: vi.fn(() => 'sess-upload'),
}));

vi.mock('../../../api/client', () => ({
  default: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    defaults: { baseURL: '/api/v1' },
  },
  getSessionId: () => mockGetSessionId(),
}));

import { TopoUploadZone } from '../TopoUploadZone';
import { useAIChat } from '../../../stores/aiChat';
import { useSession } from '../../../stores/session';
import { initChatI18n, renderWithProviders } from './chatTestUtils';

const EXISTING_INFO = {
  id: 'mesh-existing',
  type: 'topo',
  n_vertices: 10,
  n_faces: 12,
  bounds: { xmin: 0, xmax: 100, ymin: 0, ymax: 200, zmin: 1000, zmax: 1050 },
  filename: 'topo_anterior.stl',
  uploaded_at: '2026-11-09T00:00:00Z',
};

const UPLOAD_RESULT = {
  mesh_id: 'mesh-new',
  n_vertices: 1000,
  n_faces: 1996,
  bounds: { xmin: 0, xmax: 200, ymin: 0, ymax: 200, zmin: 995, zmax: 1060 },
};

function selectFile(name: string, content = 'mesh-bytes'): File {
  const file = new File([content], name, { type: 'application/octet-stream' });
  const input = document.querySelector(
    '[data-slot="ai-chat-upload-zone"] input[type="file"]',
  ) as HTMLInputElement;
  Object.defineProperty(input, 'files', { value: [file] });
  input.dispatchEvent(new Event('change', { bubbles: true }));
  return file;
}

beforeEach(() => {
  window.localStorage.clear();
  mockGet.mockReset();
  mockPost.mockReset();
  mockDelete.mockReset();
  initChatI18n();
  useAIChat.getState().reset();
  useSession.getState().reset();
  useSession.setState({ designMeshId: null, topoMeshId: null });
});

describe('TopoUploadZone — same-role replacement warning', () => {
  it('warns inline and requires an explicit confirmation BEFORE uploading over a same-role mesh', async () => {
    useSession.setState({ topoMeshId: 'mesh-existing' });
    mockGet.mockResolvedValue({ data: EXISTING_INFO });
    renderWithProviders(<TopoUploadZone />);

    selectFile('nueva_topo.stl');

    const warning = await screen.findByTestId('ai-chat-replace-warning');
    expect(warning).toHaveTextContent('reemplazará la malla de Topografía');
    await waitFor(() => expect(warning).toHaveTextContent('topo_anterior.stl'));
    expect(mockPost).not.toHaveBeenCalled();

    mockPost.mockResolvedValueOnce({ data: UPLOAD_RESULT });
    await userEvent.click(screen.getByTestId('ai-chat-replace-confirm'));

    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
    const [url] = mockPost.mock.calls[0] as unknown as [string];
    expect(url).toBe('/meshes/upload');

    await waitFor(() =>
      expect(useSession.getState().topoMeshId).toBe('mesh-new'),
    );
    const observation = useAIChat
      .getState()
      .messages.find((m) => m.kind === 'observation');
    expect(observation).toMatchObject({ kind: 'observation' });
    expect(observation?.kind === 'observation' && observation.text).toContain('mesh_id=mesh-new');
    expect(observation?.kind === 'observation' && observation.text).toContain('1.000');
    expect(observation?.kind === 'observation' && observation.text).toContain('1.996');
    expect(observation?.kind === 'observation' && observation.text).toContain('995.0–1060.0 m');
  });

  it('cancel keeps the pending file un-submitted', async () => {
    useSession.setState({ topoMeshId: 'mesh-existing' });
    mockGet.mockResolvedValue({ data: EXISTING_INFO });
    renderWithProviders(<TopoUploadZone />);
    selectFile('nueva_topo.stl');
    await screen.findByTestId('ai-chat-replace-warning');
    await userEvent.click(screen.getByTestId('ai-chat-replace-cancel'));
    expect(mockPost).not.toHaveBeenCalled();
    expect(screen.queryByTestId('ai-chat-replace-warning')).toBeNull();
  });

  it('uploads directly when the role is empty (no warning)', async () => {
    mockPost.mockResolvedValueOnce({ data: UPLOAD_RESULT });
    renderWithProviders(<TopoUploadZone />);
    selectFile('topo_fresca.stl');
    await waitFor(() => expect(mockPost).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId('ai-chat-replace-warning')).toBeNull();
    await waitFor(() =>
      expect(useSession.getState().topoMeshId).toBe('mesh-new'),
    );
  });

  it('rejects unsupported extensions before any request', async () => {
    renderWithProviders(<TopoUploadZone />);
    selectFile('informe.pdf');
    expect(await screen.findByRole('alert')).toHaveTextContent('Formato no soportado');
    expect(mockPost).not.toHaveBeenCalled();
  });
});

describe('TopoUploadZone — DXF flow and data hygiene', () => {
  it('routes DXF through inspect + dialog + confirm and injects the observation', async () => {
    mockPost
      .mockResolvedValueOnce({
        data: {
          upload_id: 'upl_1',
          filename: 'plano.dxf',
          declared_units: 6,
          layers: [
            { name: '3DFACES', n_faces: 5, n_vertices: 20, bounds: { xmin: 0, xmax: 10, ymin: 0, ymax: 10, zmin: 1000, zmax: 1010 } },
          ],
          entity_counts: { LINE: 4 },
          warnings: [],
        },
      })
      .mockResolvedValueOnce({
        data: { ...UPLOAD_RESULT, import_report: { selected_layers: ['3DFACES'], scale_factor: 1, warnings: [] } },
      });
    renderWithProviders(<TopoUploadZone />);
    selectFile('plano.dxf');
    await waitFor(() =>
      expect(mockPost.mock.calls[0]?.[0]).toBe('/meshes/dxf/inspect'),
    );
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('plano.dxf');
    const confirmButton = await waitFor(() => {
      const button = screen.getByText('Confirmar importación') as HTMLButtonElement;
      if (button.disabled) throw new Error('confirm still disabled');
      return button;
    });
    await userEvent.click(confirmButton);
    await waitFor(() =>
      expect(mockPost.mock.calls[1]?.[0]).toBe('/meshes/dxf/confirm'),
    );
    await waitFor(() =>
      expect(useSession.getState().topoMeshId).toBe('mesh-new'),
    );
    const observation = useAIChat
      .getState()
      .messages.find((m) => m.kind === 'observation');
    expect(observation?.kind === 'observation' && observation.text).toContain('mesh_id=mesh-new');
  });

  it('never persists the file blob or its content (localStorage stays empty of payload)', async () => {
    mockPost.mockResolvedValueOnce({ data: UPLOAD_RESULT });
    renderWithProviders(<TopoUploadZone />);
    const payload = 'TOPO-SECRET-BYTES-41MB';
    selectFile('topo_grande.stl', payload);
    await waitFor(() =>
      expect(useSession.getState().topoMeshId).toBe('mesh-new'),
    );
    const stored = JSON.stringify({ ...window.localStorage });
    expect(stored).not.toContain(payload);
    expect(stored).not.toContain('topo_grande');
    const storeJson = JSON.stringify(useAIChat.getState().messages);
    expect(storeJson).not.toContain(payload);
    expect(screen.queryByTestId('ai-chat-replace-warning')).toBeNull();
  });
});
