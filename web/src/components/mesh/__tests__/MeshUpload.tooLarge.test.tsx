import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import i18n from '../../../i18n';

vi.mock('../../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/client')>();
  return { ...actual, getSessionId: () => 'too-large' };
});

const { default: client } = await import('../../../api/client');
const { DropZone } = await import('../MeshUpload');

function renderDropZone() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const onSetMeshId = vi.fn();
  render(<QueryClientProvider client={queryClient}><DropZone type="topo" meshId="existing-mesh" onSetMeshId={onSetMeshId} /></QueryClientProvider>);
  return { onSetMeshId };
}

async function uploadStl(user: ReturnType<typeof userEvent.setup>) {
  await screen.findByText('existing.stl');
  await user.click(screen.getByRole('button', { name: 'Reemplazar' }));
  await user.upload(document.querySelector<HTMLInputElement>('input[type="file"]')!, new File(['stl'], 'huge.stl'));
}

describe('DropZone upload-too-large messaging', () => {
  beforeAll(async () => i18n.changeLanguage('es'));

  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'get').mockResolvedValue({ data: { id: 'existing-mesh', type: 'topo', n_vertices: 9, n_faces: 3, bounds: { xmin: 0, xmax: 3, ymin: 0, ymax: 3 }, filename: 'existing.stl', uploaded_at: 'now' } });
    vi.spyOn(client, 'delete').mockResolvedValue({ data: {} });
  });

  it('a 413 with the API limit figure shows the localized message with that figure', async () => {
    const user = userEvent.setup();
    const { onSetMeshId } = renderDropZone();
    vi.spyOn(client, 'post').mockRejectedValue({ response: { status: 413, data: { detail: 'Payload too large: 16.2 MB exceeds limit of 16 MB' } } });
    await uploadStl(user);
    expect(await screen.findByRole('alert')).toHaveTextContent('supera el límite de la demo pública (16 MB)');
    expect(screen.queryByText('Payload too large: 16.2 MB exceeds limit of 16 MB')).not.toBeInTheDocument();
    expect(onSetMeshId).not.toHaveBeenCalled();
    expect(screen.getByText('existing.stl')).toBeInTheDocument();
  });

  it('a 413 whose detail lacks the figure falls back to the generic demo message', async () => {
    const user = userEvent.setup();
    renderDropZone();
    vi.spyOn(client, 'post').mockRejectedValue({ response: { status: 413, data: { detail: 'Payload too large' } } });
    await uploadStl(user);
    expect(await screen.findByRole('alert')).toHaveTextContent('supera el límite de carga de la demo pública');
    expect(screen.queryByText(/16 MB/)).not.toBeInTheDocument();
  });

  it('a 413 without a detail falls back to the generic demo message', async () => {
    const user = userEvent.setup();
    renderDropZone();
    vi.spyOn(client, 'post').mockRejectedValue({ response: { status: 413, data: {} } });
    await uploadStl(user);
    expect(await screen.findByRole('alert')).toHaveTextContent('supera el límite de carga de la demo pública');
  });

  it('another error keeps the generic upload-failed message', async () => {
    const user = userEvent.setup();
    renderDropZone();
    vi.spyOn(client, 'post').mockRejectedValue({ response: { status: 500, data: {} } });
    await uploadStl(user);
    expect(await screen.findByRole('alert')).toHaveTextContent('Error al subir el archivo. Intente nuevamente.');
  });

  it('a successful upload shows no banner', async () => {
    const user = userEvent.setup();
    const { onSetMeshId } = renderDropZone();
    vi.spyOn(client, 'post').mockResolvedValue({ data: { mesh_id: 'new-mesh', n_vertices: 3, n_faces: 1, bounds: {} } });
    await uploadStl(user);
    await waitFor(() => expect(onSetMeshId).toHaveBeenCalledWith('new-mesh'));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
});
