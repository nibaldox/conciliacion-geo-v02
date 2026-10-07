import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useMeshBreaklines, useCurveSection } from '../../api/hooks';
import { Button } from '../ui/Button';
import { ProjectField, PROJECT_INPUT_CLASS } from '../ui/ProjectControls';

export function SectionCurveForm({ onRegisterClickHandler }: { onRegisterClickHandler?: (handler: ((x: number, y: number, curveId?: string, pointIndex?: number) => void) | null) => void }) {
  const { t } = useTranslation();
  const designMeshId = useSession((s) => s.designMeshId);
  const { data: contourData } = useMeshBreaklines(designMeshId);
  const mutation = useCurveSection();

  const [spacing, setSpacing] = useState(10);
  const [lengthUp, setLengthUp] = useState(100);
  const [lengthDown, setLengthDown] = useState(100);
  const [sector, setSector] = useState('');
  const selectedCurveId = useSession((s) => s.selectedCurveId);
  const selectedCurvePoints = useSession((s) => s.selectedCurvePoints);
  const setSelectedCurveId = useSession((s) => s.setSelectedCurveId);
  const setSelectedCurvePoints = useSession((s) => s.setSelectedCurvePoints);

  const handleMapClick = useCallback(
    (x: number, y: number, curveId?: string, pointIndex?: number) => {
      if (!curveId) return;

      const session = useSession.getState();
      const currentSelectedCurve = session.selectedCurveId;
      const currentPoints = session.selectedCurvePoints;

      if (!currentSelectedCurve) {
        // Line selection phase
        session.setSelectedCurveId(curveId);
      } else {
        // Point selection phase
        if (curveId !== currentSelectedCurve || pointIndex === undefined) {
          // Blocked, do nothing if they click a different line or no specific point
          return;
        }
        
        // They clicked the correct line. Add point.
        if (currentPoints.length < 2) {
          session.setSelectedCurvePoints([...currentPoints, { curveId, pointIndex, x, y }]);
        } else {
          // Reset to just this point if they already had 2
          session.setSelectedCurvePoints([{ curveId, pointIndex, x, y }]);
        }
      }
    },
    []
  );

  useEffect(() => {
    onRegisterClickHandler?.(handleMapClick);
    return () => {
      onRegisterClickHandler?.(null);
      // Clean up selections when unmounting the form
      useSession.getState().setSelectedCurveId(null);
      useSession.getState().setSelectedCurvePoints([]);
    };
  }, [onRegisterClickHandler, handleMapClick]);

  const handleGenerate = () => {
    if (selectedCurvePoints.length < 2 || !contourData) return;
    
    const p1 = selectedCurvePoints[0];
    const p2 = selectedCurvePoints[1];
    
    // Parse curveId
    const parts = p1.curveId.split('-');
    const elevIdx = parseInt(parts[0], 10);
    const segIdx = parseInt(parts[1], 10);
    
    const segment = contourData.lines[elevIdx].segments[segIdx];
    
    const startIdx = Math.min(p1.pointIndex, p2.pointIndex);
    const endIdx = Math.max(p1.pointIndex, p2.pointIndex);
    
    let points = segment.slice(startIdx, endIdx + 1);
    if (p1.pointIndex > p2.pointIndex) {
      points = points.reverse();
    }

    mutation.mutate({
      points,
      spacing,
      length: lengthUp + lengthDown,
      length_up: lengthUp,
      length_down: lengthDown,
      sector
    }, {
      onSuccess: () => {
        // Reset selection after successful generation
        setSelectedCurveId(null);
        setSelectedCurvePoints([]);
      },
      onError: (err) => {
        console.error("Profile generation mutation failed:", err);
      }
    });
  };

  const isReady = selectedCurvePoints.length === 2 && Math.abs(selectedCurvePoints[0].pointIndex - selectedCurvePoints[1].pointIndex) > 0;
  const p1 = selectedCurvePoints[0];
  const p2 = selectedCurvePoints[1];

  return (
    <div className="space-y-2" data-slot="section-curve-form">
      <details className="rounded-md border border-border bg-surface-raised px-2 py-1.5 text-xs text-text-secondary">
        <summary className="cursor-pointer font-medium">{t('project_input.curve_help')}</summary>
        <ol className="mt-2 list-decimal space-y-1 pl-4">
          <li>{t('project_input.curve_step1')}</li>
          <li>{t('project_input.curve_step2')}</li>
          <li>{t('project_input.curve_step3')}</li>
        </ol>
      </details>
      <div className="space-y-2 rounded-md border border-border bg-surface-raised px-2 py-1.5 text-xs">
        <div className="flex min-w-0 justify-between gap-2">
          <span className="text-text-muted">{t('project_input.selected_curve')}</span>
          <span className="truncate font-medium" title={selectedCurveId ?? undefined}>{selectedCurveId || t('project_input.none')}</span>
        </div>
        <div className="grid grid-cols-2 gap-2">
          {[p1, p2].map((point, index) => (
            <div key={index} className="min-w-0">
              <p className="text-text-muted">{t(index === 0 ? 'project_input.start' : 'project_input.end')}{point ? ` · P${point.pointIndex}` : ''}</p>
              <p className={point ? 'truncate text-[10px] leading-4 tabular-nums text-accent-bright' : 'text-text-muted'} title={point ? `${point.x.toFixed(1)}, ${point.y.toFixed(1)}` : undefined}>
                {point ? `${point.x.toFixed(1)}, ${point.y.toFixed(1)}` : t('project_input.waiting')}
              </p>
            </div>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <ProjectField id="curve-sector" label={t('section_form_file.sector')}>
          <input id="curve-sector" value={sector} onChange={(e) => setSector(e.target.value)} placeholder={t('project_input.optional')} className={PROJECT_INPUT_CLASS} />
        </ProjectField>
        <ProjectField id="curve-spacing" label={t('section_form_file.spacing')}>
          <input id="curve-spacing" type="number" value={spacing} onChange={(e) => setSpacing(Number(e.target.value))} min={1} max={100} step={1} className={PROJECT_INPUT_CLASS} />
        </ProjectField>
        <ProjectField id="curve-up" label={t('project_input.length_up')} title={t('project_input.length_help')}>
          <input id="curve-up" type="number" value={lengthUp} onChange={(e) => setLengthUp(Number(e.target.value))} min={1} max={1000} step={10} className={PROJECT_INPUT_CLASS} />
        </ProjectField>
        <ProjectField id="curve-down" label={t('project_input.length_down')} title={t('project_input.length_help')}>
          <input id="curve-down" type="number" value={lengthDown} onChange={(e) => setLengthDown(Number(e.target.value))} min={1} max={1000} step={10} className={PROJECT_INPUT_CLASS} />
        </ProjectField>
      </div>
      <Button size="sm" fullWidth className="min-h-8" disabled={!isReady || mutation.isPending} loading={mutation.isPending} onClick={handleGenerate}>
        {t(mutation.isPending ? 'project_input.generating' : 'project_input.generate')}
      </Button>
      {mutation.isError && <p role="alert" className="text-xs text-mine-red">{t('common.error')}: {mutation.error instanceof Error ? mutation.error.message : t('section_form_file.error_generic')}</p>}
      {mutation.isSuccess && <p role="status" className="text-xs text-mine-green">{t('project_input.curve_success')}</p>}
    </div>
  );
}
