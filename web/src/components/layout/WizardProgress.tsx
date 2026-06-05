import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';
import { useSections, useProcessStatus } from '../../api/hooks';
import { Tooltip } from '../ui/Tooltip';

type StepState = 'done' | 'active' | 'ready' | 'pending';

interface StepInfo {
  number: number;
  label: string;
  state: StepState;
  /** Short human-readable reason why the step is pending (for tooltip). */
  hint?: string;
}

/**
 * Top-of-app progress strip. Unlike the old StepNav, this shows
 * real readiness state for each step based on session data
 * (mesh IDs, sections count, process status). Hovering a pending
 * step shows a tooltip with what's missing.
 *
 * Click a ready/done step to jump there. Active step is highlighted.
 * Pending steps are disabled but visible so the user sees the path.
 */
export function WizardProgress() {
  const { t } = useTranslation();
  const { currentStep, setStep, designMeshId, topoMeshId } = useSession();
  const { data: sections } = useSections();
  const { data: processStatus } = useProcessStatus();

  const hasDesign = !!designMeshId;
  const hasTopo = !!topoMeshId;
  const hasBothMeshes = hasDesign && hasTopo;

  const nSections = sections?.length ?? 0;
  const hasSections = nSections > 0;

  const isProcessComplete = processStatus?.status === 'complete';
  const isProcessStarted = processStatus?.status !== 'idle' && processStatus?.status !== undefined;

  const hasResults = isProcessComplete;

  const stepInfo: StepInfo[] = [
    {
      number: 1,
      label: t('nav.step1'),
      state: hasBothMeshes ? 'done' : currentStep === 1 ? 'active' : 'pending',
      hint: !hasDesign
        ? t('wizard.hint_mesh_design')
        : !hasTopo
        ? t('wizard.hint_mesh_topo')
        : undefined,
    },
    {
      number: 2,
      label: t('nav.step2'),
      state: hasSections
        ? 'done'
        : hasBothMeshes
        ? 'ready'
        : currentStep === 2
        ? 'active'
        : 'pending',
      hint: !hasBothMeshes
        ? t('wizard.hint_step2_needs_meshes')
        : !hasSections
        ? t('wizard.hint_step2_no_sections')
        : undefined,
    },
    {
      number: 3,
      label: t('nav.step3'),
      state: hasResults
        ? 'done'
        : hasSections
        ? 'ready'
        : currentStep === 3
        ? 'active'
        : 'pending',
      hint: !hasSections
        ? t('wizard.hint_step3_needs_sections')
        : !isProcessComplete
        ? t('wizard.hint_step3_needs_run')
        : undefined,
    },
    {
      number: 4,
      label: t('nav.step4'),
      state: hasResults
        ? currentStep === 4
          ? 'active'
          : 'done'
        : isProcessStarted
        ? 'ready'
        : 'pending',
      hint: !isProcessStarted
        ? t('wizard.hint_step4_needs_run')
        : isProcessStarted && !isProcessComplete
        ? t('wizard.hint_step4_running')
        : undefined,
    },
  ];

  return (
    <nav
      data-slot="wizard-progress"
      className="flex items-center justify-center gap-1 py-3 px-4 border-b"
      style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
      aria-label={t('wizard.nav_label')}
    >
      {stepInfo.map((info, idx) => {
        const isClickable = info.state === 'done' || info.state === 'ready' || info.state === 'active';
        const chip = (
          <button
            type="button"
            onClick={() => isClickable && setStep(info.number)}
            disabled={!isClickable}
            aria-current={info.state === 'active' ? 'step' : undefined}
            aria-label={`${t('wizard.step')} ${info.number}: ${info.label}${
              info.hint ? ` — ${info.hint}` : ''
            }`}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
            style={{
              backgroundColor:
                info.state === 'active'
                  ? 'var(--color-mine-blue)'
                  : info.state === 'done'
                  ? 'var(--color-mine-green)'
                  : info.state === 'ready'
                  ? 'var(--color-surface-muted)'
                  : 'transparent',
              color:
                info.state === 'active' || info.state === 'done'
                  ? '#fff'
                  : info.state === 'ready'
                  ? 'var(--color-text-primary)'
                  : 'var(--color-text-muted)',
              border:
                info.state === 'ready'
                  ? '1px dashed var(--color-border-strong)'
                  : '1px solid transparent',
              cursor: isClickable ? 'pointer' : 'not-allowed',
            }}
          >
            <span
              className="flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold"
              style={{
                backgroundColor:
                  info.state === 'active' || info.state === 'done'
                    ? 'rgba(255,255,255,0.2)'
                    : info.state === 'ready'
                    ? 'var(--color-mine-blue)'
                    : 'var(--color-surface-muted)',
                color:
                  info.state === 'active' || info.state === 'done'
                    ? '#fff'
                    : info.state === 'ready'
                    ? '#fff'
                    : 'var(--color-text-muted)',
              }}
            >
              {info.state === 'done' ? '✓' : info.state === 'ready' ? '→' : info.number}
            </span>
            <span className="hidden sm:inline" style={{ color: 'inherit' }}>
              {info.label}
            </span>
          </button>
        );

        return (
          <span key={info.number} className="flex items-center">
            {info.hint ? (
              <Tooltip content={info.hint} side="bottom">
                {chip}
              </Tooltip>
            ) : (
              chip
            )}
            {idx < stepInfo.length - 1 && (
              <span
                className="mx-2 hidden sm:inline"
                style={{ color: 'var(--color-border-strong)' }}
                aria-hidden="true"
              >
                →
              </span>
            )}
          </span>
        );
      })}
    </nav>
  );
}
