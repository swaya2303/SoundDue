import { Check, Lock, ChevronRight } from 'lucide-react';

export interface StepItem {
  id: string;
  label: string;
  status: 'done' | 'current' | 'upcoming' | 'blocked';
  blockedReason?: string;
  badge?: number | string;
}

interface StepperProps {
  steps: StepItem[];
  currentStepId: string;
  onStepClick?: (id: string) => void;
}

export function Stepper({ steps, currentStepId, onStepClick }: StepperProps) {
  return (
    <nav aria-label="Workflow progress" className="w-full overflow-x-auto py-2">
      <ol className="flex items-center min-w-max gap-2 text-xs">
        {steps.map((step, index) => {
          const isCurrent = step.id === currentStepId;
          const isDone = step.status === 'done';
          const isBlocked = step.status === 'blocked';
          const canClick = onStepClick && (isDone || isCurrent || step.status === 'upcoming');

          return (
            <li key={step.id} className="flex items-center gap-2">
              <button
                type="button"
                disabled={isBlocked || !canClick}
                onClick={() => canClick && onStepClick(step.id)}
                title={isBlocked ? step.blockedReason || 'Step is locked' : undefined}
                className={`flex items-center gap-2 px-3 py-1.5 rounded-lg font-medium transition-all focus-ring text-left ${
                  isCurrent
                    ? 'bg-brand-50 text-brand-700 border border-brand-200 shadow-subtle'
                    : isDone
                    ? 'bg-white text-slate-700 hover:bg-slate-50 border border-slate-200'
                    : isBlocked
                    ? 'bg-slate-50 text-slate-400 border border-slate-200/80 cursor-not-allowed opacity-80'
                    : 'bg-white text-slate-500 hover:text-slate-800 border border-transparent'
                }`}
              >
                {/* Step badge/indicator */}
                <span
                  className={`w-5 h-5 rounded-full flex items-center justify-center text-[11px] font-semibold shrink-0 ${
                    isCurrent
                      ? 'bg-brand-600 text-white'
                      : isDone
                      ? 'bg-emerald-600 text-white'
                      : isBlocked
                      ? 'bg-slate-200 text-slate-500'
                      : 'bg-slate-100 text-slate-600'
                  }`}
                >
                  {isDone ? (
                    <Check className="w-3 h-3 stroke-[2.5]" />
                  ) : isBlocked ? (
                    <Lock className="w-2.5 h-2.5" />
                  ) : (
                    index + 1
                  )}
                </span>

                <span className="whitespace-nowrap">{step.label}</span>

                {step.badge !== undefined && (
                  <span
                    className={`ml-1 px-1.5 py-0.2 rounded-full text-[10px] font-mono ${
                      isCurrent
                        ? 'bg-brand-200 text-brand-800'
                        : isDone
                        ? 'bg-emerald-100 text-emerald-800'
                        : 'bg-slate-100 text-slate-600'
                    }`}
                  >
                    {step.badge}
                  </span>
                )}
              </button>

              {index < steps.length - 1 && (
                <ChevronRight className="w-3.5 h-3.5 text-slate-300 shrink-0" />
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
