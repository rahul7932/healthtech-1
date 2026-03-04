import { useState, useEffect } from 'react';

const STEPS = [
  { label: 'Retrieving articles', description: 'Searching PubMed-indexed literature' },
  { label: 'Extracting claims', description: 'Identifying atomic claims from the answer' },
  { label: 'Linking evidence', description: 'Matching each claim to supporting or contradicting studies' },
  { label: 'Detecting gaps', description: 'Flagging missing or incomplete evidence' },
  { label: 'Computing confidence', description: 'Scoring overall confidence from claims and evidence' },
];

interface PipelineStepperProps {
  isLoading: boolean;
}

export function PipelineStepper({ isLoading }: PipelineStepperProps) {
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    if (!isLoading) return;
    setCurrentStep(0);
    const interval = setInterval(() => {
      setCurrentStep((prev) => (prev + 1) % STEPS.length);
    }, 2200);
    return () => clearInterval(interval);
  }, [isLoading]);

  if (!isLoading) return null;

  return (
    <div className="flex flex-col items-center justify-center py-20">
      <div className="w-full max-w-md space-y-3">
        {STEPS.map((step, i) => {
          const isActive = isLoading && currentStep === i;
          return (
            <div
              key={step.label}
              className={`flex items-start gap-3 rounded-xl border px-4 py-3 transition-all duration-300 ${
                isActive
                  ? 'border-accent bg-accent/10'
                  : 'border-surface-hover bg-surface-elevated/50'
              }`}
            >
              <div
                className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
                  isActive ? 'bg-accent text-white' : 'bg-surface-hover text-text-muted'
                }`}
              >
                {i + 1}
              </div>
              <div className="min-w-0 flex-1">
                <p className={`text-sm font-medium ${isActive ? 'text-text-primary' : 'text-text-secondary'}`}>
                  {step.label}
                </p>
                <p className="mt-0.5 text-xs text-text-muted">{step.description}</p>
              </div>
              {isActive && (
                <div className="shrink-0">
                  <div className="h-5 w-5 rounded-full border-2 border-accent border-t-transparent animate-spin" />
                </div>
              )}
            </div>
          );
        })}
      </div>
      <p className="mt-6 text-text-muted text-sm">This may take a moment</p>
    </div>
  );
}
