interface GapsPanelProps {
  globalGaps: string[];
}

export function GapsPanel({ globalGaps }: GapsPanelProps) {
  if (globalGaps.length === 0) {
    return null;
  }

  return (
    <div className="bg-surface-elevated rounded-2xl p-6 border border-surface-hover">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-trust-medium/20 flex items-center justify-center">
          <svg className="w-5 h-5 text-trust-medium" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <div>
          <h2 className="text-xl font-semibold text-text-primary">Knowledge Gaps</h2>
          <p className="text-text-muted text-sm">Missing or incomplete evidence</p>
        </div>
      </div>

      <div className="space-y-3">
        {globalGaps.map((gap, i) => (
          <div
            key={i}
            className="flex items-start gap-3 p-3 rounded-lg bg-trust-medium/5 border border-trust-medium/20"
          >
            <div className="shrink-0 mt-0.5">
              <svg className="w-5 h-5 text-trust-medium" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <p className="text-sm text-text-secondary leading-relaxed">{gap}</p>
          </div>
        ))}
      </div>

      {/* Disclaimer */}
      <div className="mt-4 pt-4 border-t border-surface-hover">
        <p className="text-xs text-text-muted leading-relaxed">
          <span className="font-semibold">Note:</span> These gaps indicate areas where the retrieved 
          evidence may not fully address all relevant clinical considerations. Additional research 
          or expert consultation may be warranted.
        </p>
      </div>
    </div>
  );
}
