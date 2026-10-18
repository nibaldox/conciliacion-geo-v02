import { act } from 'react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createInstance } from 'i18next';
import { I18nextProvider } from 'react-i18next';
import es from '../../../locales/es.json';
import type { Tolerances } from '../../../api/types';
import { LeftSidebar } from '../LeftSidebar';

const updateSpy = vi.hoisted(() => vi.fn());

vi.mock('../../../api/hooks', () => {
  const mutationStub = () => ({ mutate: vi.fn(), isPending: false });
  return {
    useSettings: () => ({ data: SETTINGS }),
    useProcessStatus: () => ({ data: undefined }),
    useUpdateSettings: () => ({ mutate: updateSpy, isPending: false }),
    useUploadMesh: mutationStub,
    useDeleteMesh: mutationStub,
    useMeshInfo: () => ({ data: undefined }),
    useInspectDxf: mutationStub,
    useConfirmDxf: mutationStub,
    useCancelDxf: mutationStub,
  };
});

vi.mock('../../mesh/MeshUpload', () => ({ DropZone: () => <div /> }));
vi.mock('../../demo/TryDemoButton', () => ({ TryDemoButton: () => <div /> }));
vi.mock('../../sections/SectionCurveForm', () => ({ SectionCurveForm: () => <div /> }));
vi.mock('../../sections/SectionFileUpload', () => ({ SectionFileUpload: () => <div /> }));
vi.mock('../../sections/SectionList', () => ({ SectionList: () => <div /> }));
vi.mock('../../analysis/ProcessButton', () => ({ ProcessButton: () => <div /> }));
vi.mock('../../analysis/ProcessProgress', () => ({ ProcessProgress: () => <div /> }));
vi.mock('../ViewsToolbar', () => ({ ViewsToolbar: () => <div /> }));
vi.mock('../LanguageToggle', () => ({ LanguageToggle: () => <div /> }));

const TOLERANCES: Tolerances = {
  bench_height: { neg: 1, pos: 1.5 },
  face_angle: { neg: 5, pos: 5 },
  berm_width: { min: 6 },
  inter_ramp_angle: { neg: 3, pos: 2 },
  overall_angle: { neg: 2, pos: 2 },
  crest_toe_deviation: { neg: 1, pos: 1 },
};

const SETTINGS = {
  process: { resolution: 0.1, face_threshold: 40, berm_threshold: 20 },
  tolerances: TOLERANCES,
};

const BENCH_NEG = 'Tolerancia negativa: Altura de banco (m)';
const BENCH_POS = 'Tolerancia positiva: Altura de banco (m)';

const i18n = createInstance();
void i18n.init({ lng: 'es', resources: { es: { translation: es } }, initAsync: false });

function getMutateCalls(): Array<{
  tolerances?: Tolerances;
  process?: { resolution: number };
}> {
  return updateSpy.mock.calls.map((c) => c[0] as { tolerances?: Tolerances; process?: { resolution: number } });
}

function renderSidebar() {
  return render(
    <I18nextProvider i18n={i18n}>
      <LeftSidebar />
    </I18nextProvider>,
  );
}

async function openTolerances(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: /Parámetros/ }));
  return {
    neg: screen.getByLabelText(BENCH_NEG) as HTMLInputElement,
    pos: screen.getByLabelText(BENCH_POS) as HTMLInputElement,
  };
}

describe('LeftSidebar — edición rápida de tolerancias (draft + debounce)', () => {
  beforeAll(() => {
    vi.stubGlobal(
      'matchMedia',
      (query: string) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: () => false,
      }),
    );
  });

  beforeEach(() => {
    updateSpy.mockClear();
  });

  it('mantiene ambos valores tecleados: dos ediciones antes del debounce preservan neg y pos', async () => {
    const user = userEvent.setup();
    renderSidebar();
    const { neg, pos } = await openTolerances(user);
    await user.clear(neg);
    await user.type(neg, '2.5');
    await user.clear(pos);
    await user.type(pos, '3');
    expect(neg.value).toBe('2.5');
    expect(pos.value).toBe('3');
    await waitForDebounce();
    const tolerancesCalls = getMutateCalls().filter((p) =>
      (p as { tolerances?: unknown }).tolerances !== undefined,
    );
    expect(tolerancesCalls.length).toBeGreaterThan(0);
    const last = tolerancesCalls[tolerancesCalls.length - 1] as {
      tolerances: Tolerances;
      process: { resolution: number };
    };
    expect(last.tolerances).toEqual({
      bench_height: { neg: 2.5, pos: 3 },
      face_angle: { neg: 5, pos: 5 },
      berm_width: { min: 6 },
      inter_ramp_angle: { neg: 3, pos: 2 },
      overall_angle: { neg: 2, pos: 2 },
      crest_toe_deviation: { neg: 1, pos: 1 },
    });
    expect(last.process.resolution).toBe(0.1);
  });

  it('la UI muestra el draft al instante (no revierte al valor del GET congelado)', async () => {
    const user = userEvent.setup();
    renderSidebar();
    const { neg } = await openTolerances(user);
    await user.clear(neg);
    await user.type(neg, '4');
    expect(neg.value).toBe('4');
    expect((screen.getByLabelText(BENCH_POS) as HTMLInputElement).value).toBe('1.5');
  });

  it('el botón guardar no pisa el borrador de tolerancias', async () => {
    const user = userEvent.setup();
    renderSidebar();
    await openTolerances(user);
    const neg = screen.getByLabelText(BENCH_NEG) as HTMLInputElement;
    await user.clear(neg);
    await user.type(neg, '2.5');
    await user.click(screen.getByRole('button', { name: /Guardar|guardar/i }));
    const saved = getMutateCalls().find((p) =>
      (p as { tolerances?: Tolerances }).tolerances?.bench_height?.neg === 2.5,
    );
    expect(saved).toBeDefined();
  });

  it('un re-render desde el GET viejo no deshace la edición pendiente', async () => {
    const user = userEvent.setup();
    const { rerender } = renderSidebar();
    const { neg } = await openTolerances(user);
    await user.clear(neg);
    await user.type(neg, '4');
    rerender(
      <I18nextProvider i18n={i18n}>
        <LeftSidebar />
      </I18nextProvider>,
    );
    expect((screen.getByLabelText(BENCH_NEG) as HTMLInputElement).value).toBe('4');
  });
});

async function waitForDebounce() {
  await act(async () => {
    await new Promise((r) => setTimeout(r, 560));
  });
}
