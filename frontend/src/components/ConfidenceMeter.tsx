import type { TrustReport } from '../types';

interface ConfidenceMeterProps {
  report: TrustReport;
}

export function ConfidenceMeter({ report }: ConfidenceMeterProps) {
  const confidence = report.overall_confidence;
  const percentage = confidence * 100;
  
  // Determine color based on confidence level
  const getColor = (value: number) => {
    if (value >= 0.7) return { text: 'text-trust-high', bg: 'bg-trust-high', ring: 'ring-trust-high/30' };
    if (value >= 0.4) return { text: 'text-trust-medium', bg: 'bg-trust-medium', ring: 'ring-trust-medium/30' };
    return { text: 'text-trust-low', bg: 'bg-trust-low', ring: 'ring-trust-low/30' };
  };

  const colors = getColor(confidence);

  // Confidence breakdown by claim
  const claimConfidences = report.claims.map((c) => c.confidence);
  const highConfClaims = claimConfidences.filter((c) => c >= 0.7).length;
  const medConfClaims = claimConfidences.filter((c) => c >= 0.4 && c < 0.7).length;
  const lowConfClaims = claimConfidences.filter((c) => c < 0.4).length;

  return (
    <div className="bg-surface-elevated rounded-2xl p-6 border border-surface-hover">
      <div className="flex items-center gap-3 mb-6">
        <div className={`w-10 h-10 rounded-xl ${colors.bg}/20 flex items-center justify-center`}>
          <svg className={`w-5 h-5 ${colors.text}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-text-primary">Confidence</h2>
      </div>

      {/* Main confidence gauge */}
      <div className="flex flex-col items-center mb-6">
        <div className={`relative w-32 h-32 rounded-full ${colors.ring} ring-4`}>
          {/* Background circle */}
          <svg className="w-full h-full transform -rotate-90" viewBox="0 0 100 100">
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              stroke="currentColor"
              strokeWidth="8"
              className="text-surface-hover"
            />
            <circle
              cx="50"
              cy="50"
              r="42"
              fill="none"
              stroke="currentColor"
              strokeWidth="8"
              strokeLinecap="round"
              strokeDasharray={`${percentage * 2.64} 264`}
              className={colors.text}
              style={{
                transition: 'stroke-dasharray 0.5s ease-out',
              }}
            />
          </svg>
          {/* Center text */}
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className={`text-3xl font-bold ${colors.text}`}>
              {percentage.toFixed(0)}%
            </span>
            <span className="text-text-muted text-xs uppercase tracking-wider">
              {confidence >= 0.7 ? 'High' : confidence >= 0.4 ? 'Moderate' : 'Low'}
            </span>
          </div>
        </div>
      </div>

      {/* Claim confidence breakdown */}
      <div className="space-y-3">
        <h3 className="text-sm font-medium text-text-secondary">Claims by Confidence</h3>
        
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-trust-high"></span>
              <span className="text-sm text-text-secondary">High confidence</span>
            </div>
            <span className="text-sm font-medium text-text-primary">{highConfClaims}</span>
          </div>
          
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-trust-medium"></span>
              <span className="text-sm text-text-secondary">Moderate confidence</span>
            </div>
            <span className="text-sm font-medium text-text-primary">{medConfClaims}</span>
          </div>
          
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-trust-low"></span>
              <span className="text-sm text-text-secondary">Low confidence</span>
            </div>
            <span className="text-sm font-medium text-text-primary">{lowConfClaims}</span>
          </div>
        </div>

        {/* Visual bar breakdown */}
        <div className="h-2 rounded-full bg-surface-hover overflow-hidden flex">
          {highConfClaims > 0 && (
            <div 
              className="h-full bg-trust-high" 
              style={{ width: `${(highConfClaims / report.claims.length) * 100}%` }}
            />
          )}
          {medConfClaims > 0 && (
            <div 
              className="h-full bg-trust-medium" 
              style={{ width: `${(medConfClaims / report.claims.length) * 100}%` }}
            />
          )}
          {lowConfClaims > 0 && (
            <div 
              className="h-full bg-trust-low" 
              style={{ width: `${(lowConfClaims / report.claims.length) * 100}%` }}
            />
          )}
        </div>
      </div>

      {/* Evidence summary */}
      <div className="mt-6 pt-4 border-t border-surface-hover">
        <h3 className="text-sm font-medium text-text-secondary mb-3">Evidence Summary</h3>
        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="bg-surface rounded-lg p-3">
            <div className="text-2xl font-bold text-text-primary">{report.evidence_summary.total_sources}</div>
            <div className="text-xs text-text-muted">Total Sources</div>
          </div>
          <div className="bg-supports/10 rounded-lg p-3">
            <div className="text-2xl font-bold text-supports">{report.evidence_summary.supporting}</div>
            <div className="text-xs text-text-muted">Supporting</div>
          </div>
          <div className="bg-contradicts/10 rounded-lg p-3">
            <div className="text-2xl font-bold text-contradicts">{report.evidence_summary.contradicting}</div>
            <div className="text-xs text-text-muted">Contradicting</div>
          </div>
        </div>
      </div>
    </div>
  );
}
