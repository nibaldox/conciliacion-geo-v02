import { STEPS } from '../../utils/constants';
import { useSession } from '../../stores/session';

export function StepNav() {
  const { currentStep, setStep } = useSession();

  return (
    <nav
      className="flex items-center justify-center gap-1 py-3 px-4 border-b"
      style={{ backgroundColor: 'var(--color-surface)', borderColor: 'var(--color-border)' }}
    >
      {STEPS.map((step, idx) => {
        const isActive = step.number === currentStep;
        const isComplete = step.number < currentStep;
        const isClickable = step.number <= currentStep;

        return (
          <button
            key={step.number}
            onClick={() => isClickable && setStep(step.number)}
            disabled={!isClickable}
            className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all"
            style={{
              backgroundColor: isActive ? 'var(--color-mine-blue)' : isComplete ? 'var(--color-mine-green)' : 'transparent',
              color: isActive || isComplete ? '#fff' : 'var(--color-text-muted)',
              cursor: isClickable ? 'pointer' : 'not-allowed',
            }}
          >
            <span
              className="flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold"
              style={{ backgroundColor: isActive || isComplete ? 'rgba(255,255,255,0.2)' : 'var(--color-surface-muted)', color: isActive || isComplete ? '#fff' : 'var(--color-text-muted)' }}
            >
              {isComplete ? '✓' : step.number}
            </span>
            <span className="hidden sm:inline" style={{ color: 'inherit' }}>{step.label}</span>
            {idx < STEPS.length - 1 && (
              <span className="mx-2 hidden sm:inline" style={{ color: 'var(--color-border-strong)' }}>→</span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
