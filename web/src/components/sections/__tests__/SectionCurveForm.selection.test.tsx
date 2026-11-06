import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SectionCurveForm } from '../SectionCurveForm';
import { useSession } from '../../../stores/session';
import { createCurveAnchor } from '../curveAnchorGeometry';
import { getCurveGeometrySnapshot } from '../curveGeometryAdapter';
import type { CurveAnchor } from '../curveSelectionState';
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

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key: string) => key }),
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

function currentSnapshot() {
  return getCurveGeometrySnapshot('mesh-A', mocks.breaklines.current as ContourData);
}

function anchorAt(t: number, snapshot = currentSnapshot()): CurveAnchor {
  const curve = snapshot?.curves.get('0-0');
  if (!snapshot || !curve) {
    throw new Error('fixture curve missing');
  }
  return createCurveAnchor({
    context: snapshot.context,
    curveId: curve.id,
    points: curve.points,
    segmentIndex: 0,
    t,
  })!;
}

let registered: RegisteredHandler = null;

function registerCapture(): (cb: unknown) => void {
  return (cb: unknown) => {
    registered = (cb as RegisteredHandler | null) ?? null;
  };
}

function mounted() {
  const utils = render(<SectionCurveForm onRegisterClickHandler={registerCapture()} />);
  expect(registered).not.toBeNull();
  return {
    click: registered as (anchor: CurveAnchor) => void,
    rerender: utils.rerender,
  };
}

function clickAnchor(click: (anchor: CurveAnchor) => void, anchor: CurveAnchor): void {
  act(() => {
    click(anchor);
  });
}

function chooseAnchors(click: (anchor: CurveAnchor) => void): void {
  clickAnchor(click, anchorAt(0));
  clickAnchor(click, anchorAt(0.2));
  clickAnchor(click, anchorAt(0.8));
}

beforeEach(() => {
  useSession.getState().reset();
  useSession.getState().setDesignMeshId('mesh-A'); // matches the fixture snapshot
  mocks.mutation.mutate.mockClear();
  mocks.mutation.isPending = false;
  mocks.mutation.isError = false;
  mocks.mutation.isSuccess = false;
});

describe('SectionCurveForm curve selection integration', () => {
  it('keeps the confirmed range after generation and form unmount, until reset', () => {
    mocks.breaklines.current = buildContourData();
    const { click } = mounted();
    chooseAnchors(click);
    const guide = { id: '0-0', points: [[20, 0, 1200], [80, 0, 1200]] };
    expect(useSession.getState().guideCurve).toEqual(guide);
    fireEvent.click(screen.getByRole('button', { name: 'project_input.generate' }));
    act(() => (mocks.mutation.mutate.mock.calls[0][1] as { onSuccess: () => void }).onSuccess());
    expect(useSession.getState().guideCurve).toEqual(guide);
    cleanup();
    expect(useSession.getState().guideCurve).toEqual(guide);
    useSession.getState().reset();
    expect(useSession.getState().guideCurve).toBeNull();
  });

  it('removes the guide explicitly without restoring it from the transient selection', () => {
    mocks.breaklines.current = buildContourData();
    const { click } = mounted();
    chooseAnchors(click);
    fireEvent.click(screen.getByRole('button', { name: 'project_input.remove_guide' }));
    expect(useSession.getState().guideCurve).toBeNull();
    expect(useSession.getState().curveSelection.curveId).toBeNull();
  });

  it('clears the guide when loading an already-cached demo', async () => {
    useSession.getState().setGuideCurve({ id: 'old', points: [[0, 0, 0], [1, 1, 1]] });
    useSession.setState({ demoData: { sections: [] } as never });
    await act(() => useSession.getState().loadDemo());
    expect(useSession.getState().guideCurve).toBeNull();
  });

  it('copies guide coordinates rather than sharing the source array', () => {
    const points: [number, number, number][] = [[0, 0, 1], [1, 1, 1]];
    useSession.getState().setGuideCurve({ id: 'a', points });
    points[0][0] = 9;
    expect(useSession.getState().guideCurve?.points[0][0]).toBe(0);
  });

  it('enables generation from the registered callback and sends the exact XY payload', () => {
    mocks.breaklines.current = buildContourData();
    const { click } = mounted();
    chooseAnchors(click);

    const generate = screen.getByRole('button', { name: 'project_input.generate' });
    expect(generate).toBeEnabled();
    fireEvent.click(generate);
    expect(mocks.mutation.mutate).toHaveBeenCalledTimes(1);
    expect(mocks.mutation.mutate.mock.calls[0][0]).toEqual({
      points: [[20, 0], [80, 0]],
      spacing: 10,
      length: 200,
      length_up: 100,
      length_down: 100,
      sector: '',
    });
  });

  it('preserves the clicked anchor order when the range runs backwards', () => {
    mocks.breaklines.current = buildContourData();
    const { click } = mounted();
    clickAnchor(click, anchorAt(0));
    clickAnchor(click, anchorAt(0.8));
    clickAnchor(click, anchorAt(0.2));

    fireEvent.click(screen.getByRole('button', { name: 'project_input.generate' }));
    expect(mocks.mutation.mutate.mock.calls[0][0]).toMatchObject({
      points: [[80, 0], [20, 0]],
    });
  });

  it('supports the segment corner anchors (t=0 and t=1)', () => {
    mocks.breaklines.current = buildContourData();
    const { click } = mounted();
    clickAnchor(click, anchorAt(0));
    clickAnchor(click, anchorAt(0));
    clickAnchor(click, anchorAt(1));

    fireEvent.click(screen.getByRole('button', { name: 'project_input.generate' }));
    expect(mocks.mutation.mutate.mock.calls[0][0]).toMatchObject({
      points: [[0, 0], [100, 0]],
    });
  });

  it('clears the confirmed anchors after a successful generation', () => {
    mocks.breaklines.current = buildContourData();
    const { click } = mounted();
    chooseAnchors(click);
    fireEvent.click(screen.getByRole('button', { name: 'project_input.generate' }));
    expect(mocks.mutation.mutate).toHaveBeenCalledTimes(1);

    const afterOptions = mocks.mutation.mutate.mock.calls[0][1] as {
      onSuccess: () => void;
    };
    act(() => {
      afterOptions.onSuccess();
    });
    const selection = useSession.getState().curveSelection;
    expect(selection.curveId).toBeNull();
    expect(selection.start).toBeNull();
    expect(selection.end).toBeNull();
    expect(screen.getByRole('button', { name: 'project_input.generate' })).toBeDisabled();
  });

  it('replacing the breaklines data clears the anchors instead of carrying them over', () => {
    mocks.breaklines.current = buildContourData();
    const { click, rerender } = mounted();
    const oldSnapshot = currentSnapshot()!;
    const staleLineAnchor = anchorAt(0, oldSnapshot);
    const staleAnchor20 = anchorAt(0.2, oldSnapshot);
    clickAnchor(click, staleLineAnchor);
    clickAnchor(click, staleAnchor20);
    let selection = useSession.getState().curveSelection;
    expect(selection.curveId).toBe('0-0');
    expect(selection.start).not.toBeNull();

    mocks.breaklines.current = buildContourData();
    rerender(<SectionCurveForm onRegisterClickHandler={registerCapture()} />);
    selection = useSession.getState().curveSelection;
    expect(selection.start).toBeNull();
    expect(screen.getByRole('button', { name: 'project_input.generate' })).toBeDisabled();

    clickAnchor(click, staleLineAnchor);
    clickAnchor(click, staleAnchor20);
    selection = useSession.getState().curveSelection;
    expect(selection.curveId).toBeNull();
    expect(screen.getByRole('button', { name: 'project_input.generate' })).toBeDisabled();

    mocks.breaklines.current = undefined;
    rerender(<SectionCurveForm onRegisterClickHandler={registerCapture()} />);
    selection = useSession.getState().curveSelection;
    expect(selection.start).toBeNull();
    expect(screen.getByRole('button', { name: 'project_input.generate' })).toBeDisabled();
  });

  it('clears the registration and current selection when the form unmounts', () => {
    mocks.breaklines.current = buildContourData();
    mounted();
    const click = registered as (anchor: CurveAnchor) => void;
    clickAnchor(click, anchorAt(0));
    clickAnchor(click, anchorAt(0.2));
    expect(useSession.getState().curveSelection.start).not.toBeNull();

    cleanup();
    expect(registered).toBeNull();
    const selection = useSession.getState().curveSelection;
    expect(selection.curveId).toBeNull();
    expect(selection.start).toBeNull();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('preserves spacing, lengths, sector and total length in the payload', () => {
    mocks.breaklines.current = buildContourData();
    const { click } = mounted();
    fireEvent.change(screen.getByLabelText('section_form_file.sector'), {
      target: { value: 'Norte' },
    });
    fireEvent.change(screen.getByLabelText('section_form_file.spacing'), {
      target: { value: '25' },
    });
    fireEvent.change(screen.getByLabelText('project_input.length_up'), {
      target: { value: '150' },
    });
    chooseAnchors(click);

    fireEvent.click(screen.getByRole('button', { name: 'project_input.generate' }));
    expect(mocks.mutation.mutate.mock.calls[0][0]).toEqual({
      points: [[20, 0], [80, 0]],
      spacing: 25,
      length: 250,
      length_up: 150,
      length_down: 100,
      sector: 'Norte',
    });
  });

  it('keeps a fresh selection when a stale success resolves after reselecting', () => {
    mocks.breaklines.current = buildContourData();
    const { click } = mounted();
    chooseAnchors(click);

    fireEvent.click(screen.getByRole('button', { name: 'project_input.generate' }));
    expect(mocks.mutation.mutate).toHaveBeenCalledTimes(1);
    const staleOptions = mocks.mutation.mutate.mock.calls[0][1] as {
      onSuccess: () => void;
    };

    clickAnchor(click, anchorAt(0.3));
    let selection = useSession.getState().curveSelection;
    expect(selection.start?.position[0]).toBe(30);
    expect(selection.end).toBeNull();

    act(() => {
      staleOptions.onSuccess();
    });
    selection = useSession.getState().curveSelection;
    expect(selection.curveId).toBe('0-0');
    expect(selection.start?.position[0]).toBe(30);
    expect(selection.end).toBeNull();
  });

  it('still clears the submitted selection when a rejected foreign click only adds rejection metadata', () => {
    mocks.breaklines.current = buildContourData();
    const { click } = mounted();
    chooseAnchors(click);

    fireEvent.click(screen.getByRole('button', { name: 'project_input.generate' }));
    const staleOptions = mocks.mutation.mutate.mock.calls[0][1] as {
      onSuccess: () => void;
    };

    const submitted = useSession.getState().curveSelection;
    const foreignSnapshot = getCurveGeometrySnapshot('mesh-B', buildContourData());
    const foreignCurve = foreignSnapshot?.curves.get('0-0');
    if (!foreignSnapshot || !foreignCurve) throw new Error('foreign fixture missing');
    clickAnchor(click, createCurveAnchor({
      context: foreignSnapshot.context,
      curveId: foreignCurve.id,
      points: foreignCurve.points,
      segmentIndex: 0,
      t: 0.5,
    })!);

    const afterReject = useSession.getState().curveSelection;
    expect(afterReject.start).toBe(submitted.start);
    expect(afterReject.end).toBe(submitted.end);
    expect(afterReject.curveId).toBe('0-0');

    act(() => {
      staleOptions.onSuccess();
    });
    const after = useSession.getState().curveSelection;
    expect(after.curveId).toBeNull();
    expect(after.start).toBeNull();
    expect(after.end).toBeNull();
  });
});
