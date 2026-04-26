import { STEPS } from '../../utils/constants';
import { useSession } from '../../stores/session';

export function StepNav() {
  const { currentStep, setStep } = useSession();

  return (
    <nav className="flex items-center justify-center gap-1 py-3 px-4 bg-white border-b border-gray-200">
      {STEPS.map((step, idx) => {
        const isActive = step.number === currentStep;
        const isComplete = step.number < currentStep;
        const isClickable = step.number <= currentStep;

        return (
          <button
            key={step.number}
            onClick={() => isClickable && setStep(step.number)}
            disabled={!isClickable}
            className={`
              flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all
              max-[480px]:p-0 max-[480px]:rounded-full
              ${isActive ? 'bg-mine-blue text-white shadow-md' : ''}
              ${isComplete ? 'bg-mine-green text-white hover:bg-green-700' : ''}
              ${!isActive && !isComplete ? 'bg-gray-100 text-gray-400' : ''}
              ${isClickable ? 'cursor-pointer' : 'cursor-not-allowed'}
            `}
          >
            <span className="flex items-center justify-center w-7 h-7 rounded-full text-xs font-bold bg-white/20">
              {isComplete ? '✓' : step.number}
            </span>
            {/* Label: hidden below 640px */}
            <span className="hidden sm:inline">{step.label}</span>
            {/* Arrow: hidden below 640px */}
            {idx < STEPS.length - 1 && (
              <span className="mx-2 text-gray-300 hidden sm:inline">→</span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
