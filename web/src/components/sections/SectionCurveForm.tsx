import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useMeshBreaklines, useCurveSection } from '../../api/hooks';
import { Button } from '../ui/Button';
import { ProjectField, PROJECT_INPUT_CLASS } from '../ui/ProjectControls';
import { getCurveGeometrySnapshot } from './curveGeometryAdapter';
import { buildCurveRange } from './curveRange';
import { createCurveAnchor } from './curveAnchorGeometry';
import type { CurveGeometrySnapshot } from './curveGeometryAdapter';
import type { CurveAnchor, CurveSelectionContext, CurveSelectionRejection } from './curveSelectionState';

const REJECTION_MESSAGE_KEYS: Record<CurveSelectionRejection, string> = {
  different_curve: 'project_input.curve_rejection_different_curve',
  stale_context: 'project_input.curve_rejection_stale_context',
  invalid_anchor: 'project_input.curve_rejection_invalid_anchor',
  coincident_anchor: 'project_input.curve_rejection_coincident_anchor',
  invalid_geometry: 'project_input.curve_rejection_invalid_geometry',
};

function formatXY(position: readonly [number, number, number]): string {
  return `${position[0].toFixed(3)}, ${position[1].toFixed(3)}`;
}

function formatRawXY(position: readonly [number, number, number]): string {
  return `${position[0]}, ${position[1]}`;
}

function anchorIsDisplayable(
  anchor: CurveAnchor | null,
  snapshot: CurveGeometrySnapshot | null,
  curveId: string | null,
  selectionContext: CurveSelectionContext | null,
): boolean {
  if (!anchor || !snapshot || !curveId || !selectionContext) return false;
  if (anchor.curveId !== curveId) return false;
  if (
    anchor.context.designMeshId !== snapshot.context.designMeshId ||
    anchor.context.geometryKey !== snapshot.context.geometryKey ||
    selectionContext.designMeshId !== snapshot.context.designMeshId ||
    selectionContext.geometryKey !== snapshot.context.geometryKey
  ) {
    return false;
  }
  const curve = snapshot.curves.get(curveId);
  if (!curve) return false;
  const recalculated = createCurveAnchor({
    context: snapshot.context,
    curveId,
    points: curve.points,
    segmentIndex: anchor.segmentIndex,
    t: anchor.t,
  });
  if (!recalculated) return false;
  return (
    recalculated.position[0] === anchor.position[0] &&
    recalculated.position[1] === anchor.position[1] &&
    recalculated.position[2] === anchor.position[2] &&
    recalculated.chainage === anchor.chainage
  );
}

const SPACING_MIN = 1;
const SPACING_MAX = 100;
const LENGTH_MIN = 1;
const LENGTH_MAX = 1000;

function parseParameterDraft(draft: string, min: number, max: number): number | null {
  const trimmed = draft.trim();
  if (trimmed === '') return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < min || value > max) return null;
  return value;
}

export function SectionCurveForm() {
  const { t } = useTranslation();
  const designMeshId = useSession((s) => s.designMeshId);
  const { data: contourData } = useMeshBreaklines(designMeshId);
  const mutation = useCurveSection();

  const [spacing, setSpacing] = useState('10');
  const [lengthUp, setLengthUp] = useState('100');
  const [lengthDown, setLengthDown] = useState('100');
  const [sector, setSector] = useState('');
  const spacingValue = parseParameterDraft(spacing, SPACING_MIN, SPACING_MAX);
  const lengthUpValue = parseParameterDraft(lengthUp, LENGTH_MIN, LENGTH_MAX);
  const lengthDownValue = parseParameterDraft(lengthDown, LENGTH_MIN, LENGTH_MAX);
  const parametersValid = spacingValue !== null && lengthUpValue !== null && lengthDownValue !== null;
  const curveSelection = useSession((s) => s.curveSelection);
  const dispatchCurveSelection = useSession((s) => s.dispatchCurveSelection);
  const guideCurve = useSession((s) => s.guideCurve);
  const setGuideCurve = useSession((s) => s.setGuideCurve);

  const snapshot = useMemo(
    () => getCurveGeometrySnapshot(designMeshId, contourData),
    [designMeshId, contourData],
  );

  useEffect(() => {
    dispatchCurveSelection({ type: 'context', context: snapshot ? snapshot.context : null });
  }, [snapshot, dispatchCurveSelection]);

  const helpSummaryRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.key !== 'Escape') return;
      if (useSession.getState().curveSelection.curveId === null) return;
      event.preventDefault();
      dispatchCurveSelection({ type: 'cancel' });
      helpSummaryRef.current?.focus();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [dispatchCurveSelection]);

  const handleReset = useCallback(() => {
    dispatchCurveSelection({ type: 'cancel' });
    helpSummaryRef.current?.focus();
  }, [dispatchCurveSelection]);

  const selectedCurve = snapshot?.curves.get(curveSelection.curveId ?? '') ?? null;
  const range = useMemo(() => {
    if (!snapshot || !selectedCurve || !curveSelection.start || !curveSelection.end) return null;
    if (
      !curveSelection.context
      || curveSelection.context.designMeshId !== snapshot.context.designMeshId
      || curveSelection.context.geometryKey !== snapshot.context.geometryKey
    ) {
      return null;
    }
    return buildCurveRange({
      context: snapshot.context,
      curveId: curveSelection.curveId ?? '',
      points: selectedCurve.points,
      start: curveSelection.start,
      end: curveSelection.end,
    });
  }, [snapshot, selectedCurve, curveSelection.context, curveSelection.start, curveSelection.end]);

  useEffect(() => {
    if (!snapshot || !selectedCurve || !curveSelection.curveId || !curveSelection.context) return;
    if (curveSelection.context.designMeshId !== snapshot.context.designMeshId || curveSelection.context.geometryKey !== snapshot.context.geometryKey) return;
    if (curveSelection.start && curveSelection.end && !range) return;
    setGuideCurve({ id: curveSelection.curveId, points: range ?? selectedCurve.points });
  }, [snapshot, selectedCurve, curveSelection.curveId, curveSelection.context, curveSelection.start, curveSelection.end, range, setGuideCurve]);

  const handleGenerate = useCallback(() => {
    if (!range || spacingValue === null || lengthUpValue === null || lengthDownValue === null || mutation.isPending) return;
    const submittedSelection = curveSelection;
    const submittedContext = submittedSelection.context;
    mutation.mutate({
      points: range.map(([east, north]) => [east, north]),
      spacing: spacingValue,
      length: lengthUpValue + lengthDownValue,
      length_up: lengthUpValue,
      length_down: lengthDownValue,
      sector,
    }, {
      onSuccess: () => {
        const current = useSession.getState().curveSelection;
        const sameContext = current.context !== null
          && current.context.designMeshId === submittedContext?.designMeshId
          && current.context.geometryKey === submittedContext?.geometryKey;
        const sameSelection = current.curveId === submittedSelection.curveId
          && current.start === submittedSelection.start
          && current.end === submittedSelection.end;
        if (sameContext && sameSelection) {
          dispatchCurveSelection({ type: 'generated' });
        }
      },
      onError: (err) => {
        console.error('Profile generation mutation failed:', err);
      },
    });
  }, [range, mutation, spacingValue, lengthUpValue, lengthDownValue, sector, curveSelection, dispatchCurveSelection]);

  const isReady = range !== null;

  const rangeLength = useMemo(() => {
    if (!range) return null;
    let total = 0;
    for (let i = 0; i + 1 < range.length; i += 1) {
      total += Math.hypot(range[i + 1][0] - range[i][0], range[i + 1][1] - range[i][1]);
    }
    return total;
  }, [range]);

  const [p1, p2] = useMemo(() => {
    const displayable = (anchor: CurveAnchor | null): CurveAnchor | null =>
      anchorIsDisplayable(anchor, snapshot, curveSelection.curveId, curveSelection.context)
        ? anchor
        : null;
    return [displayable(curveSelection.start), displayable(curveSelection.end)] as const;
  }, [snapshot, curveSelection.curveId, curveSelection.context, curveSelection.start, curveSelection.end]);

  const statusMessage = curveSelection.rejection
    ? t(REJECTION_MESSAGE_KEYS[curveSelection.rejection])
    : range !== null
      ? parametersValid
        ? t('project_input.curve_phase_ready')
        : t('project_input.curve_params_invalid')
      : p1 && p2
        ? t('project_input.curve_phase_invalid_range')
        : p1
          ? t('project_input.curve_phase_end')
          : curveSelection.curveId && selectedCurve
            ? t('project_input.curve_phase_start')
            : t('project_input.curve_phase_choose_curve');

  return (
    <div className="space-y-2" data-slot="section-curve-form">
      <details className="rounded-md border border-border bg-surface-raised px-2 py-1.5 text-xs text-text-secondary">
        <summary ref={helpSummaryRef} className="cursor-pointer font-medium">{t('project_input.curve_help')}</summary>
        <ol className="mt-2 list-decimal space-y-1 pl-4">
          <li>{t('project_input.curve_step1')}</li>
          <li>{t('project_input.curve_step2')}</li>
          <li>{t('project_input.curve_step3')}</li>
        </ol>
        <p className="mt-2 text-text-muted">{t('project_input.curve_sector_note')}</p>
      </details>
      <div className="space-y-2 rounded-md border border-border bg-surface-raised px-2 py-1.5 text-xs">
        <div className="flex min-w-0 justify-between gap-2">
          <span className="text-text-muted">{t('project_input.selected_curve')}</span>
          <span className="truncate font-medium" title={curveSelection.curveId ?? undefined}>{curveSelection.curveId || t('project_input.none')}</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {[p1, p2].map((point, index) => (
            <div key={index} className="min-w-0" data-slot={index === 0 ? 'curve-start-summary' : 'curve-end-summary'}>
              <p className="text-text-muted">{t(index === 0 ? 'project_input.start' : 'project_input.end')}</p>
              {point ? (
                <p
                  className="truncate text-[10px] leading-4 tabular-nums text-accent-bright"
                  title={formatRawXY(point.position)}
                >
                  {`${formatXY(point.position)} · ${t('project_input.curve_chainage')} ${point.chainage.toFixed(3)} m`}
                </p>
              ) : (
                <p className="text-text-muted">{t('project_input.waiting')}</p>
              )}
            </div>
          ))}
        </div>
        <p data-slot="curve-selection-status" role="status" aria-live="polite" className="text-text-muted">
          {statusMessage}
        </p>
        {rangeLength !== null && (
          <div className="flex min-w-0 justify-between gap-2 tabular-nums" data-slot="curve-range-length">
            <span className="text-text-muted">{t('project_input.curve_range_length')}</span>
            <span className="truncate font-medium">{rangeLength.toFixed(3)} m</span>
          </div>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <ProjectField id="curve-sector" label={t('section_form_file.sector')}>
          <input id="curve-sector" value={sector} onChange={(e) => setSector(e.target.value)} placeholder={t('project_input.optional')} className={PROJECT_INPUT_CLASS} />
        </ProjectField>
        <ProjectField id="curve-spacing" label={t('section_form_file.spacing')}>
          <input id="curve-spacing" type="number" value={spacing} onChange={(e) => setSpacing(e.target.value)} min={1} max={100} step={1} aria-invalid={spacingValue === null} aria-describedby={parametersValid ? undefined : 'curve-params-error'} className={PROJECT_INPUT_CLASS} />
        </ProjectField>
        <ProjectField id="curve-up" label={t('project_input.length_up')} title={t('project_input.length_help')}>
          <input id="curve-up" type="number" value={lengthUp} onChange={(e) => setLengthUp(e.target.value)} min={1} max={1000} step={10} aria-invalid={lengthUpValue === null} aria-describedby={parametersValid ? undefined : 'curve-params-error'} className={PROJECT_INPUT_CLASS} />
        </ProjectField>
        <ProjectField id="curve-down" label={t('project_input.length_down')} title={t('project_input.length_help')}>
          <input id="curve-down" type="number" value={lengthDown} onChange={(e) => setLengthDown(e.target.value)} min={1} max={1000} step={10} aria-invalid={lengthDownValue === null} aria-describedby={parametersValid ? undefined : 'curve-params-error'} className={PROJECT_INPUT_CLASS} />
        </ProjectField>
      </div>
      {!parametersValid && (
        <p id="curve-params-error" className="text-xs text-mine-red">{t('project_input.curve_params_invalid')}</p>
      )}
      <div className="grid grid-cols-2 gap-2">
        <Button size="sm" fullWidth className="min-h-8 h-full text-center leading-tight" disabled={!isReady || !parametersValid || mutation.isPending} loading={mutation.isPending} onClick={handleGenerate}>
          {t(mutation.isPending ? 'project_input.generating' : 'project_input.generate')}
        </Button>
        <Button size="sm" variant="secondary" fullWidth className="min-h-8 h-full text-center leading-tight" onClick={handleReset}>
          {t('project_input.curve_reset')}
        </Button>
      </div>
      {guideCurve && <Button size="sm" variant="secondary" fullWidth onClick={() => { setGuideCurve(null); dispatchCurveSelection({ type: 'cancel' }); }}>{t('project_input.remove_guide')}</Button>}
      {mutation.isError && <p role="alert" className="text-xs text-mine-red">{t('common.error')}: {mutation.error instanceof Error ? mutation.error.message : t('section_form_file.error_generic')}</p>}
      {mutation.isSuccess && <p role="status" className="text-xs text-mine-green">{t('project_input.curve_success')}</p>}
    </div>
  );
}
