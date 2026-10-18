import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SectionCurveForm } from '../SectionCurveForm';
import { useSession } from '../../../stores/session';
import i18n from '../../../i18n';
import { createCurveAnchor } from '../curveAnchorGeometry';
import { getCurveGeometrySnapshot } from '../curveGeometryAdapter';
import type { CurveAnchor, CurveSelectionState } from '../curveSelectionState';
import type { ContourData } from '../../../api/types';

type RegisteredHandler = ((anchor: CurveAnchor) => void) | null;

const mocks = vi.hoisted(() => ({
  breaklines: { current: null as unknown },
  mutation: {
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    isSuccess: false,
    error: null as unknown,
  },
}));

vi.mock('../../../api/hooks', () => ({
  useMeshBreaklines: () => ({
    data: mocks.breaklines.current as ContourData | undefined,
    isLoading: false,
  }),
  useCurveSection: () => mocks.mutation,
}));

function buildContourData(): ContourData {
  return {
    bounds: { min_east: 0, max_east: 100 },
    elevation_min: 1200,
    elevation_max: 1200,
    interval: 5,
    lines: [
      { elevation: 1200, type: 'crest', segments: [[[0, 0], [100, 0]]] },
    ],
  };
}

function buildTwoCurveContourData(): ContourData {
  return {
    bounds: { min_east: 0, max_east: 100 },
    elevation_min: 1200,
    elevation_max: 1200,
    interval: 5,
    lines: [
      { elevation: 1200, type: 'crest', segments: [[[0, 0], [100, 0]]] },
      { elevation: 1200, type: 'crest', segments: [[[0, 0], [100, 0]]] },
    ],
  };
}

function currentSnapshot() {
  return getCurveGeometrySnapshot('mesh-A', mocks.breaklines.current as ContourData);
}

function anchorForCurve(curveId: string, t: number, snapshot = currentSnapshot()): CurveAnchor {
  const curve = snapshot?.curves.get(curveId);
  if (!snapshot || !curve) {
    throw new Error('fixture curve missing');
  }
  return createCurveAnchor({
    context: snapshot.context,
    curveId,
    points: curve.points,
    segmentIndex: 0,
    t,
  })!;
}

function anchorAt(t: number, snapshot = currentSnapshot()): CurveAnchor {
  return anchorForCurve('0-0', t, snapshot);
}

let registered: RegisteredHandler = null;

function mounted() {
  const utils = render(
    <SectionCurveForm
      onRegisterClickHandler={(handler) => {
        registered = handler;
      }}
    />,
  );
  expect(registered).not.toBeNull();
  return utils;
}

function clickAnchor(anchor: CurveAnchor): void {
  const click = registered as (anchor: CurveAnchor) => void;
  act(() => {
    click(anchor);
  });
}

function summaryElement(slot: string): HTMLElement {
  const element = document.querySelector(`[data-slot="${slot}"]`);
  if (!element) {
    throw new Error(`missing [data-slot="${slot}"]`);
  }
  return element as HTMLElement;
}

function selectionStatus(): string {
  return summaryElement('curve-selection-status').textContent ?? '';
}

function helpSummary(): HTMLElement {
  return screen.getByText('Cómo definir el tramo');
}

function injectSelection(start: CurveAnchor, curveId = '0-0'): void {
  const snapshot = currentSnapshot();
  if (!snapshot) {
    throw new Error('snapshot missing');
  }
  const next: CurveSelectionState = {
    context: snapshot.context,
    curveId,
    start,
    end: null,
    rejection: null,
  };
  act(() => {
    useSession.setState({ curveSelection: next });
  });
}

beforeEach(async () => {
  useSession.getState().reset();
  useSession.getState().setDesignMeshId('mesh-A');
  mocks.mutation.mutate.mockClear();
  mocks.mutation.isPending = false;
  mocks.mutation.isError = false;
  mocks.mutation.isSuccess = false;
  localStorage.removeItem('conciliacion.lang');
  await act(async () => {
    await i18n.changeLanguage('es');
  });
});

describe('SectionCurveForm continuous feedback (T10a)', () => {
  it('shows exact continuous summaries (XY to 3 decimals, chainage, range length) with phase status and generate enabled', () => {
    mocks.breaklines.current = buildContourData();
    mounted();

    expect(selectionStatus()).toBe('Elige una línea para comenzar.');

    clickAnchor(anchorAt(0));
    expect(selectionStatus()).toBe('Marca el punto inicial.');

    clickAnchor(anchorAt(0.2));
    expect(selectionStatus()).toBe('Marca el punto final.');

    clickAnchor(anchorAt(0.8));
    expect(selectionStatus()).toBe('Tramo listo: puedes generar los perfiles.');

    const start = summaryElement('curve-start-summary');
    expect(start.textContent).toContain('20.000, 0.000');
    expect(start.textContent).toContain('Cadenamiento 20.000 m');
    expect(start.querySelector('p[title]')?.getAttribute('title')).toBe('20, 0');

    const end = summaryElement('curve-end-summary');
    expect(end.textContent).toContain('80.000, 0.000');
    expect(end.textContent).toContain('Cadenamiento 80.000 m');
    expect(end.querySelector('p[title]')?.getAttribute('title')).toBe('80, 0');

    expect(summaryElement('curve-range-length').textContent).toContain('60.000');

    const statusElement = screen.getByRole('status');
    expect(statusElement).toHaveAttribute('aria-live', 'polite');
    expect(statusElement).toHaveAttribute('data-slot', 'curve-selection-status');

    expect(screen.getByRole('button', { name: 'Generar perfiles' })).toBeEnabled();
  });

  it('hides a foreign-curve start anchor sharing the snapshot geometry and rejects tampered positions', () => {
    mocks.breaklines.current = buildTwoCurveContourData();
    mounted();
    const snapshot = currentSnapshot();
    if (!snapshot) {
      throw new Error('snapshot missing');
    }

    const foreignStart = anchorForCurve('1-0', 0.2);
    expect(foreignStart.position[0]).toBeCloseTo(20);
    injectSelection(foreignStart);
    expect(summaryElement('curve-start-summary').textContent).not.toContain('20.000');
    expect(summaryElement('curve-start-summary').textContent).toContain('Esperando clic');
    expect(selectionStatus()).toBe('Marca el punto inicial.');

    injectSelection(anchorForCurve('0-0', 0.2));
    expect(summaryElement('curve-start-summary').textContent).toContain('20.000, 0.000');
    expect(summaryElement('curve-start-summary').textContent).toContain('Cadenamiento 20.000 m');
    expect(selectionStatus()).toBe('Marca el punto final.');

    const ownStart = anchorForCurve('0-0', 0.2);
    const tampered: CurveAnchor = { ...ownStart, position: [99, 99, 1200] };
    injectSelection(tampered);
    expect(summaryElement('curve-start-summary').textContent).not.toContain('99.000');
    expect(summaryElement('curve-start-summary').textContent).toContain('Esperando clic');
  });

  it('keeps focus in a field when Escape fires with no active curve', async () => {
    await act(async () => {
      await i18n.changeLanguage('en');
    });
    mocks.breaklines.current = buildContourData();
    mounted();
    const sectorInput = screen.getByLabelText('Sector');
    act(() => {
      sectorInput.focus();
    });
    expect(selectionStatus()).toBe('Pick a line to begin.');

    fireEvent.keyDown(sectorInput, { key: 'Escape' });

    expect(document.activeElement).toBe(sectorInput);
    expect(selectionStatus()).toBe('Pick a line to begin.');
  });

  it('clears an active selection on Escape, preserving context and typed fields, and focuses the help summary', () => {
    mocks.breaklines.current = buildContourData();
    mounted();
    fireEvent.change(screen.getByLabelText('Sector'), { target: { value: 'Norte' } });
    fireEvent.change(screen.getByLabelText('Espaciamiento (m)'), { target: { value: '25' } });
    fireEvent.change(screen.getByLabelText('Superior (m)'), { target: { value: '150' } });
    clickAnchor(anchorAt(0));
    clickAnchor(anchorAt(0.2));
    clickAnchor(anchorAt(0.8));
    expect(selectionStatus()).toBe('Tramo listo: puedes generar los perfiles.');
    const contextBefore = useSession.getState().curveSelection.context;

    fireEvent.keyDown(document.body, { key: 'Escape' });

    const after = useSession.getState().curveSelection;
    expect(after.curveId).toBeNull();
    expect(after.start).toBeNull();
    expect(after.end).toBeNull();
    expect(after.context).toBe(contextBefore);
    expect((screen.getByLabelText('Sector') as HTMLInputElement).value).toBe('Norte');
    expect((screen.getByLabelText('Espaciamiento (m)') as HTMLInputElement).value).toBe('25');
    expect((screen.getByLabelText('Superior (m)') as HTMLInputElement).value).toBe('150');
    expect(document.activeElement).toBe(helpSummary());
    expect(selectionStatus()).toBe('Elige una línea para comenzar.');
  });

  it('ignores a default-prevented Escape while a selection is active', () => {
    mocks.breaklines.current = buildContourData();
    mounted();
    clickAnchor(anchorAt(0));
    clickAnchor(anchorAt(0.2));
    const before = useSession.getState().curveSelection;
    expect(before.start).not.toBeNull();

    const prevented = new KeyboardEvent('keydown', {
      key: 'Escape',
      bubbles: true,
      cancelable: true,
    });
    prevented.preventDefault();
    act(() => {
      document.body.dispatchEvent(prevented);
    });

    const after = useSession.getState().curveSelection;
    expect(after.curveId).toBe(before.curveId);
    expect(after.start).toBe(before.start);
    expect(document.activeElement).toBe(document.body);
  });

  it('clears the selection and focuses the help summary when the reset button is clicked', () => {
    mocks.breaklines.current = buildContourData();
    mounted();
    clickAnchor(anchorAt(0));
    clickAnchor(anchorAt(0.2));
    const contextBefore = useSession.getState().curveSelection.context;
    expect(useSession.getState().curveSelection.start).not.toBeNull();

    fireEvent.click(screen.getByRole('button', { name: 'RESTABLECER SELECCIÓN' }));

    const after = useSession.getState().curveSelection;
    expect(after.curveId).toBeNull();
    expect(after.start).toBeNull();
    expect(after.end).toBeNull();
    expect(after.context).toBe(contextBefore);
    expect(document.activeElement).toBe(helpSummary());
    expect(selectionStatus()).toBe('Elige una línea para comenzar.');
  });

  it('renders a zero-chainage start as a valid 0.000 summary and shows waiting without fake zeros when absent', () => {
    mocks.breaklines.current = buildContourData();
    mounted();

    clickAnchor(anchorAt(0));
    expect(summaryElement('curve-start-summary').textContent).toContain('Esperando clic');
    expect(summaryElement('curve-end-summary').textContent).toContain('Esperando clic');
    expect(summaryElement('curve-start-summary').textContent).not.toContain('0.000');
    expect(summaryElement('curve-end-summary').textContent).not.toContain('0.000');
    expect(selectionStatus()).toBe('Marca el punto inicial.');

    clickAnchor(anchorAt(0));
    clickAnchor(anchorAt(0.2));
    expect(summaryElement('curve-start-summary').textContent).toContain('0.000, 0.000');
    expect(summaryElement('curve-start-summary').textContent).toContain('Cadenamiento 0.000 m');
    expect(summaryElement('curve-range-length').textContent).toContain('20.000');
    expect(selectionStatus()).toBe('Tramo listo: puedes generar los perfiles.');
  });

  it('keeps the validated summaries stable while editing fields after the range is ready', () => {
    mocks.breaklines.current = buildContourData();
    mounted();
    clickAnchor(anchorAt(0));
    clickAnchor(anchorAt(0.2));
    clickAnchor(anchorAt(0.8));
    expect(selectionStatus()).toBe('Tramo listo: puedes generar los perfiles.');

    fireEvent.change(screen.getByLabelText('Espaciamiento (m)'), { target: { value: '40' } });
    fireEvent.change(screen.getByLabelText('Sector'), { target: { value: 'Sur' } });

    expect(summaryElement('curve-start-summary').textContent).toContain('20.000, 0.000');
    expect(summaryElement('curve-end-summary').textContent).toContain('80.000, 0.000');
    expect(summaryElement('curve-range-length').textContent).toContain('60.000');
    expect(selectionStatus()).toBe('Tramo listo: puedes generar los perfiles.');
    const after = useSession.getState().curveSelection;
    expect(after.start?.position[0]).toBe(20);
    expect(after.end?.position[0]).toBe(80);
  });
});

describe('SectionCurveForm generation preconditions (T10b)', () => {
  it('keeps generation disabled with hidden summaries when only the selection context no longer matches the snapshot', () => {
    mocks.breaklines.current = buildContourData();
    mounted();
    clickAnchor(anchorAt(0));
    clickAnchor(anchorAt(0.2));
    clickAnchor(anchorAt(0.8));
    expect(selectionStatus()).toBe('Tramo listo: puedes generar los perfiles.');
    const generate = screen.getByRole('button', { name: 'Generar perfiles' });
    expect(generate).toBeEnabled();
    const ready = useSession.getState().curveSelection;
    const snapshot = currentSnapshot();
    if (!snapshot) {
      throw new Error('snapshot missing');
    }
    const foreignContext = {
      designMeshId: snapshot.context.designMeshId,
      geometryKey: 'foreign-geometry-key',
    };

    act(() => {
      useSession.setState({ curveSelection: { ...ready, context: foreignContext } });
    });

    expect(summaryElement('curve-start-summary').textContent).toContain('Esperando clic');
    expect(summaryElement('curve-end-summary').textContent).toContain('Esperando clic');
    expect(document.querySelector('[data-slot="curve-range-length"]')).toBeNull();
    expect(generate).toBeDisabled();
    fireEvent.click(generate);
    expect(mocks.mutation.mutate).not.toHaveBeenCalled();
    expect(selectionStatus()).not.toBe('Tramo listo: puedes generar los perfiles.');
  });

  it('keeps a cleared spacing draft empty, flags the field and blocks generation instead of sending 0', () => {
    mocks.breaklines.current = buildContourData();
    mounted();
    clickAnchor(anchorAt(0));
    clickAnchor(anchorAt(0.2));
    clickAnchor(anchorAt(0.8));
    expect(selectionStatus()).toBe('Tramo listo: puedes generar los perfiles.');
    const spacingInput = screen.getByLabelText('Espaciamiento (m)') as HTMLInputElement;

    fireEvent.change(spacingInput, { target: { value: '' } });

    expect(spacingInput.value).toBe('');
    expect(spacingInput).toHaveAttribute('aria-invalid', 'true');
    const error = document.getElementById('curve-params-error');
    expect(error).not.toBeNull();
    expect(error?.textContent).toBe('Parámetros no válidos: espaciamiento entre 1 y 100 m; longitudes entre 1 y 1000 m.');
    expect(spacingInput.getAttribute('aria-describedby')).toBe('curve-params-error');
    expect(summaryElement('curve-start-summary').textContent).toContain('20.000, 0.000');
    expect(summaryElement('curve-end-summary').textContent).toContain('80.000, 0.000');
    const generate = screen.getByRole('button', { name: 'Generar perfiles' });
    expect(generate).toBeDisabled();
    fireEvent.click(generate);
    expect(mocks.mutation.mutate).not.toHaveBeenCalled();
    expect(selectionStatus()).toBe('Parámetros no válidos: espaciamiento entre 1 y 100 m; longitudes entre 1 y 1000 m.');
  });

  it('restores the ready phase and enables generation once an invalid draft becomes valid again', () => {
    mocks.breaklines.current = buildContourData();
    mounted();
    clickAnchor(anchorAt(0));
    clickAnchor(anchorAt(0.2));
    clickAnchor(anchorAt(0.8));
    const spacingInput = screen.getByLabelText('Espaciamiento (m)') as HTMLInputElement;
    fireEvent.change(spacingInput, { target: { value: '' } });
    expect(screen.getByRole('button', { name: 'Generar perfiles' })).toBeDisabled();

    fireEvent.change(spacingInput, { target: { value: '40' } });

    expect(spacingInput.value).toBe('40');
    expect(spacingInput).toHaveAttribute('aria-invalid', 'false');
    expect(spacingInput.getAttribute('aria-describedby')).toBeNull();
    expect(document.getElementById('curve-params-error')).toBeNull();
    expect(selectionStatus()).toBe('Tramo listo: puedes generar los perfiles.');
    expect(screen.getByRole('button', { name: 'Generar perfiles' })).toBeEnabled();
  });

  it('blocks zero, out-of-range and non-finite parameter drafts without mutating', () => {
    mocks.breaklines.current = buildContourData();
    mounted();
    clickAnchor(anchorAt(0));
    clickAnchor(anchorAt(0.2));
    clickAnchor(anchorAt(0.8));
    const spacingInput = screen.getByLabelText('Espaciamiento (m)') as HTMLInputElement;
    const upInput = screen.getByLabelText('Superior (m)') as HTMLInputElement;
    const generate = screen.getByRole('button', { name: 'Generar perfiles' });

    fireEvent.change(spacingInput, { target: { value: '0' } });
    expect(generate).toBeDisabled();

    fireEvent.change(spacingInput, { target: { value: '150' } });
    expect(generate).toBeDisabled();

    fireEvent.change(upInput, { target: { value: '-5' } });
    expect(generate).toBeDisabled();

    fireEvent.change(upInput, { target: { value: '1e999' } });
    expect(generate).toBeDisabled();

    fireEvent.click(generate);
    expect(mocks.mutation.mutate).not.toHaveBeenCalled();
    expect(summaryElement('curve-range-length').textContent).toContain('60.000');
  });

  it('sends the exact typed fractional spacing and asymmetric lengths with the sector verbatim', () => {
    mocks.breaklines.current = buildContourData();
    mounted();
    fireEvent.change(screen.getByLabelText('Sector'), { target: { value: 'Sur' } });
    fireEvent.change(screen.getByLabelText('Espaciamiento (m)'), { target: { value: '12.5' } });
    fireEvent.change(screen.getByLabelText('Superior (m)'), { target: { value: '150' } });
    fireEvent.change(screen.getByLabelText('Inferior (m)'), { target: { value: '75' } });
    clickAnchor(anchorAt(0));
    clickAnchor(anchorAt(0.2));
    clickAnchor(anchorAt(0.8));

    expect((screen.getByLabelText('Espaciamiento (m)') as HTMLInputElement).value).toBe('12.5');
    fireEvent.click(screen.getByRole('button', { name: 'Generar perfiles' }));
    expect(mocks.mutation.mutate).toHaveBeenCalledTimes(1);
    expect(mocks.mutation.mutate.mock.calls[0][0]).toEqual({
      points: [[20, 0], [80, 0]],
      spacing: 12.5,
      length: 225,
      length_up: 150,
      length_down: 75,
      sector: 'Sur',
    });
  });

  it('preserves the typed drafts across the reset button without mutating', () => {
    mocks.breaklines.current = buildContourData();
    mounted();
    fireEvent.change(screen.getByLabelText('Espaciamiento (m)'), { target: { value: '12.5' } });
    fireEvent.change(screen.getByLabelText('Superior (m)'), { target: { value: '150' } });
    fireEvent.change(screen.getByLabelText('Inferior (m)'), { target: { value: '75' } });
    clickAnchor(anchorAt(0));
    clickAnchor(anchorAt(0.2));

    fireEvent.click(screen.getByRole('button', { name: 'RESTABLECER SELECCIÓN' }));

    expect((screen.getByLabelText('Espaciamiento (m)') as HTMLInputElement).value).toBe('12.5');
    expect((screen.getByLabelText('Superior (m)') as HTMLInputElement).value).toBe('150');
    expect((screen.getByLabelText('Inferior (m)') as HTMLInputElement).value).toBe('75');
    expect(mocks.mutation.mutate).not.toHaveBeenCalled();
  });
});
