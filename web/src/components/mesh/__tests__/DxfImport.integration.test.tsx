import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '../../../i18n';

vi.mock('../../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/client')>();
  return { ...actual, getSessionId: () => 'dxf-integration' };
});

const { default: client } = await import('../../../api/client');
const { DropZone } = await import('../MeshUpload');

const inspected = {
  upload_id: 'staged-dxf-1',
  filename: 'surface.dxf',
  type: 'design' as const,
  expires_at: 1791028800,
  declared_units: 0,
  layers: [
    { name: 'bench-a', n_faces: 2, n_vertices: 4, bounds: { xmin: 0, xmax: 1000, ymin: 0, ymax: 400, zmin: 100, zmax: 200 }, entity_counts: { '3DFACE': 2 } },
    { name: 'bench-b', n_faces: 3, n_vertices: 5, bounds: { xmin: 1000, xmax: 1800, ymin: 0, ymax: 400, zmin: 100, zmax: 200 }, entity_counts: { MESH: 1 } },
  ],
  entity_counts: { '3DFACE': 2, MESH: 1, LINE: 4 },
  warnings: ['UNITS_UNKNOWN'],
  importer_version: '1.0',
};

function renderDropZone(type: 'design' | 'topo' = 'design', compact = false) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const onSetMeshId = vi.fn();
  const view = render(<QueryClientProvider client={queryClient}><DropZone type={type} meshId="existing-mesh" onSetMeshId={onSetMeshId} compact={compact} /></QueryClientProvider>);
  return { ...view, onSetMeshId };
}

async function uploadDxf(user: ReturnType<typeof userEvent.setup>, type: 'design' | 'topo' = 'design') {
  await screen.findByText('existing.stl');
  await user.click(screen.getByRole('button', { name: 'Reemplazar' }));
  const input = document.querySelector<HTMLInputElement>('input[type="file"]');
  expect(input).not.toBeNull();
  await user.upload(input!, new File(['dxf'], 'surface.dxf', { type: 'application/dxf' }));
  await screen.findByRole('dialog', { name: `Revisar DXF para ${type === 'design' ? 'Diseño' : 'Topografía'}` });
}

describe('DXF surface import flow', () => {
  beforeAll(async () => i18n.changeLanguage('es'));

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'get').mockResolvedValue({ data: { id: 'existing-mesh', type: 'design', n_vertices: 9, n_faces: 3, bounds: { xmin: 0, xmax: 3, ymin: 0, ymax: 3 }, filename: 'existing.stl', uploaded_at: 'now' } });
    vi.spyOn(client, 'post').mockImplementation(async (url) => {
      if (url === '/meshes/dxf/inspect') return { data: inspected };
      if (url === '/meshes/dxf/confirm') return { data: { mesh_id: 'new-mesh', n_vertices: 9, n_faces: 5, bounds: {}, import_report: { selected_layers: ['bench-a'], declared_units: 0, confirmed_units: 6, scale_factor: 1, importer_version: '1.0', entity_counts: {}, warnings: [], discarded_faces: 0 } } };
      return { data: {} };
    });
    vi.spyOn(client, 'delete').mockResolvedValue({ data: {} });
  });

  it.each(['design', 'topo'] as const)('requires a layer and explicit units for unknown-unit %s DXF, then confirms', async (type) => {
    const user = userEvent.setup();
    const { onSetMeshId } = renderDropZone(type);
    await uploadDxf(user, type);
    const dialog = screen.getByRole('dialog');
    const layerBoxes = within(dialog).getAllByRole('checkbox');
    expect(layerBoxes).toHaveLength(2);
    expect(layerBoxes[0]).not.toBeChecked();
    const confirm = within(dialog).getByRole('button', { name: 'Confirmar importación' });
    expect(confirm).toBeDisabled();
    await user.click(layerBoxes[0]);
    expect(confirm).toBeDisabled();
    await user.selectOptions(within(dialog).getByLabelText('Unidades del archivo'), '6');
    expect(within(dialog).getByText(/X 0\.000 – 1000\.000 m/)).toBeInTheDocument();
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() => expect(onSetMeshId).toHaveBeenCalledWith('new-mesh'));
    const inspectCall = vi.mocked(client.post).mock.calls.find(([url]) => url === '/meshes/dxf/inspect');
    expect(inspectCall?.[1]).toBeInstanceOf(FormData);
    expect((inspectCall?.[1] as FormData).get('type')).toBe(type);
    const confirmCall = vi.mocked(client.post).mock.calls.find(([url]) => url === '/meshes/dxf/confirm');
    expect(confirmCall?.[1]).toEqual({ upload_id: 'staged-dxf-1', layers: ['bench-a'], units: 6 });
  });

  it('cancel and confirm errors keep the previous mesh assigned', async () => {
    const user = userEvent.setup();
    const { onSetMeshId } = renderDropZone();
    await uploadDxf(user);
    await user.click(screen.getAllByRole('button', { name: 'Cancelar' })[0]);
    await waitFor(() => expect(client.delete).toHaveBeenCalledWith('/meshes/dxf/staged-dxf-1'));
    expect(onSetMeshId).not.toHaveBeenCalled();

    await uploadDxf(user);
    const dialog = screen.getByRole('dialog');
    await user.click(within(dialog).getAllByRole('checkbox')[0]);
    await user.selectOptions(within(dialog).getByLabelText('Unidades del archivo'), '6');
    vi.mocked(client.post).mockImplementation(async (url) => {
      if (url === '/meshes/dxf/inspect') return { data: inspected };
      if (url === '/meshes/dxf/confirm') throw { response: { data: { detail: 'La capa contiene geometría inválida.' } } };
      return { data: {} };
    });
    await user.click(within(dialog).getByRole('button', { name: 'Confirmar importación' }));
    expect(await within(dialog).findByRole('alert')).toHaveTextContent('La capa contiene geometría inválida.');
    expect(onSetMeshId).not.toHaveBeenCalled();
    expect(screen.getByText('existing.stl')).toBeInTheDocument();
  });

  it('shows an inspect error while retaining the existing mesh', async () => {
    const user = userEvent.setup();
    const { onSetMeshId } = renderDropZone();
    await screen.findByText('existing.stl');
    vi.mocked(client.post).mockRejectedValue({ response: { data: { detail: 'DXF ilegible: archivo incompleto.' } } });
    await user.click(screen.getByRole('button', { name: 'Reemplazar' }));
    await user.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!, new File(['bad'], 'broken.dxf'));
    expect(await screen.findByText('DXF ilegible: archivo incompleto.')).toBeInTheDocument();
    expect(screen.getByText('existing.stl')).toBeInTheDocument();
    expect(onSetMeshId).not.toHaveBeenCalled();
  });

  it.each([false, true])('shows the STL rejection reason and retains the previous mesh (compact=%s)', async (compact) => {
    const user = userEvent.setup();
    const { onSetMeshId } = renderDropZone('design', compact);
    await screen.findByText('existing.stl');
    const detail = 'Archivo demasiado grande: 260.0 MiB (máximo permitido: 250 MiB).';
    vi.mocked(client.post).mockRejectedValue({ response: { data: { detail } } });
    await user.click(screen.getByRole('button', { name: 'Reemplazar' }));
    await user.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!, new File(['stl'], 'large.stl'));
    expect(await screen.findByRole('alert')).toHaveTextContent(detail);
    expect(screen.getByText('existing.stl')).toBeInTheDocument();
    expect(onSetMeshId).not.toHaveBeenCalled();
  });

  it('ignores a late DXF inspection after a newer STL selection', async () => {
    const user = userEvent.setup();
    const { onSetMeshId } = renderDropZone();
    await screen.findByText('existing.stl');
    let finishInspect!: (value: { data: typeof inspected }) => void;
    vi.mocked(client.post).mockImplementation((url) => {
      if (url === '/meshes/dxf/inspect') return new Promise((resolve) => { finishInspect = resolve; });
      if (url === '/meshes/upload') return Promise.resolve({ data: { mesh_id: 'new-stl', n_vertices: 3, n_faces: 1, bounds: {} } });
      return Promise.resolve({ data: {} });
    });
    const input = document.querySelector<HTMLInputElement>('input[type="file"]')!;
    await user.upload(input, new File(['dxf'], 'pending.dxf'));
    await user.upload(input, new File(['stl'], 'replacement.stl'));
    await waitFor(() => expect(onSetMeshId).toHaveBeenCalledWith('new-stl'));
    finishInspect({ data: inspected });
    await waitFor(() => expect(client.delete).toHaveBeenCalledWith('/meshes/dxf/staged-dxf-1'));
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});
