/**
 * WizardProgress — the numbered step indicator at the top of the
 * app. Connects the four steps with a horizontal line so the
 * user can always see where they are.
 *
 * Mission Control aesthetic: orange accent for the active step,
 * neon-green for completed, muted for pending. The connector line
 * is the same accent when previous is done, muted when pending.
 *
 * Two layouts:
 *  - 'numbered' (default): the [1] — [2] — [3] — [4] strip
 *    from the reference design. Uppercase labels under each
 *    number.
 *  - 'compact' (kept for compatibility): just the chips
 *
 * Click a completed/current step to jump back; future steps are
 * disabled (matches the WizardProgress from Parada 1).
 */

import { useTranslation } from 'react-i18next';
import { useSession } from '../../stores/session';

const STEPS: readonly { number: 1 | 2 | 3 | 4; key: string; icon: string }[] = [
  { number: 1, key: 'step1', icon: 'UPLOAD' },
  { number: 2, key: 'step2', icon: 'ALIGN' },
  { number: 3, key: 'step3', icon: 'ANALYZE' },
  { number: 4, key: 'step4', icon: 'SYNC' },
];

interface WizardProgressProps {
  /** When 'numbered', renders the [N] — [N] — [N] strip with
   *  uppercase labels. Otherwise just the chips. */
  variant?: 'numbered' | 'compact';
}

export function WizardProgress({ variant = 'numbered' }: WizardProgressProps) {
  const { t } = useTranslation();
  const currentStep = useSession((s) => s.currentStep);
  const setStep = useSession((s) => s.setStep);

  return (
    <nav
      data-slot="wizard-progress"
      data-variant={variant}
      className="flex items-center justify-center gap-0 px-3 md:px-6 py-3 border-b shrink-0"
      style={{
        backgroundColor: 'var(--color-surface)',
        borderColor: 'var(--color-border)',
      }}
      aria-label={t('wizard.nav_label', { defaultValue: 'Wizard progress' })}
    >
      {STEPS.map((step, idx) => {
        const isActive = step.number === currentStep;
        const isComplete = step.number < currentStep;
        const isClickable = step.number <= currentStep;
        const label = t(`wizard.step.${step.key}`, { defaultValue: step.key });

        return (
          <span key={step.number} className="flex items-center">
            <button
              type="button"
              onClick={() => isClickable && setStep(step.number)}
              disabled={!isClickable}
              data-step={step.number}
              data-state={
                isActive ? 'active' : isComplete ? 'done' : 'pending'
              }
              aria-current={isActive ? 'step' : undefined}
              className={[
                'group flex items-center gap-2 px-2.5 py-1 rounded-md',
                'transition-all duration-150',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-accent',
                isClickable
                  ? 'cursor-pointer hover:opacity-90'
                  : 'cursor-not-allowed opacity-50',
              ].join(' ')}
            >
              <span
                className="flex items-center justify-center w-7 h-7 rounded-md text-xs font-bold"
                style={{
                  backgroundColor: isActive
                    ? 'var(--color-accent)'
                    : isComplete
                    ? 'var(--color-mine-green)'
                    : 'var(--color-surface-muted)',
                  color: isActive
                    ? '#0a0e14'
                    : isComplete
                    ? '#0a0e14'
                    : 'var(--color-text-muted)',
                  fontFamily: 'var(--font-mono)',
                  boxShadow: isActive
                    ? '0 0 12px rgba(249, 115, 22, 0.40)'
                    : 'none',
                }}
                aria-hidden="true"
              >
                {isComplete ? '✓' : step.number}
              </span>
              {variant === 'numbered' && (
                <span
                  className="text-[10px] uppercase tracking-widest font-semibold"
                  style={{
                    color: isActive
                      ? 'var(--color-accent-bright)'
                      : isComplete
                      ? 'var(--color-status-ok-text)'
                      : 'var(--color-text-muted)',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {label}
                </span>
              )}
            </button>
            {idx < STEPS.length - 1 && (
              <span
                aria-hidden="true"
                className="mx-2 sm:mx-3"
                style={{
                  width: '24px',
                  height: '1px',
                  backgroundColor: isComplete
                    ? 'var(--color-mine-green)'
                    : 'var(--color-border)',
                  display: 'inline-block',
                }}
              />
            )}
          </span>
        );
      })}
    </nav>
  );
}
