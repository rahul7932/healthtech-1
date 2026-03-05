import { useState } from 'react';
import { QueryInput, type QueryOptions, AnswerPanel, EvidenceMap, ConfidenceMeter, GapsPanel, PipelineStepper, SystemStatus, DebatePanel } from './components';
import { submitQuery, ApiError } from './api/client';
import type { TrustReport } from './types';

function App() {
  const [report, setReport] = useState<TrustReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastOptions, setLastOptions] = useState<QueryOptions | null>(null);
  const [showDemoLimitModal, setShowDemoLimitModal] = useState(false);

  const handleQuery = async (question: string, options: QueryOptions) => {
    setIsLoading(true);
    setError(null);
    setShowDemoLimitModal(false);
    setLastOptions(options);
    
    try {
      const result = await submitQuery({
        question,
        top_k: 5,
        live_fetch: options.live_fetch,
        use_agentic_debate: options.use_agentic_debate,
      });
      setReport(result);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 429) {
          setShowDemoLimitModal(true);
        } else {
          setError(err.message);
        }
      } else {
        setError('An unexpected error occurred. Please try again.');
      }
      console.error('Query failed:', err);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface text-text-primary">
      {/* Demo limit reached modal */}
      {showDemoLimitModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50"
          onClick={() => setShowDemoLimitModal(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="demo-limit-title"
        >
          <div
            className="rounded-2xl bg-surface-elevated border border-surface-hover shadow-xl max-w-md w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-4">
              <div className="shrink-0 w-12 h-12 rounded-xl bg-contradicts/10 flex items-center justify-center">
                <svg className="w-6 h-6 text-contradicts" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
              </div>
              <div className="min-w-0 flex-1">
                <h2 id="demo-limit-title" className="text-lg font-semibold text-text-primary">
                  Demo limit reached
                </h2>
                <p className="mt-2 text-sm text-text-secondary">
                  You've used the free demo allowance for this session. Please contact us for full access.
                </p>
                <button
                  type="button"
                  onClick={() => setShowDemoLimitModal(false)}
                  className="mt-4 w-full px-4 py-2.5 rounded-xl bg-accent hover:bg-accent-hover text-white font-medium text-sm transition-colors"
                >
                  Got it
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <header className="border-b border-surface-hover bg-surface-elevated/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-6 py-4">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent to-supports flex items-center justify-center">
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
              </svg>
            </div>
            <div>
              <h1 className="text-xl font-bold text-text-primary">MedTrust AI</h1>
              <p className="text-sm text-text-muted">Evidence-based medical answer verification</p>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 py-8">
        {/* Query Input Section */}
        <section className="mb-8">
          <QueryInput onSubmit={handleQuery} isLoading={isLoading} />
        </section>

        {/* Error Display */}
        {error && (
          <div className="mb-8 p-4 rounded-xl bg-contradicts/10 border border-contradicts/30 text-contradicts">
            <div className="flex items-center gap-3">
              <svg className="w-5 h-5 shrink-0" fill="currentColor" viewBox="0 0 20 20">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
              </svg>
              <span>{error}</span>
            </div>
          </div>
        )}

        {/* Loading State - multi-step pipeline indicator */}
        {isLoading && <PipelineStepper isLoading={isLoading} />}

        {/* Live fetch decision (when user allowed it) */}
        {report && !isLoading && lastOptions?.live_fetch && (
          <div className="mb-6 rounded-2xl border border-surface-hover bg-surface-elevated/60 p-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-semibold text-text-primary">Live fetch decision</span>
                  {report.fetch_triggered ? (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-accent/20 text-accent border border-accent/30">
                      Triggered
                    </span>
                  ) : (
                    <span className="text-xs px-2 py-0.5 rounded-full bg-surface-hover/50 text-text-secondary border border-surface-hover">
                      Skipped
                    </span>
                  )}
                </div>
                <p className="mt-1 text-xs text-text-muted">
                  {report.coverage_before_fetch?.reason ?? 'Coverage check completed.'}
                </p>
              </div>

              {report.fetch_triggered && (
                <div className="shrink-0 text-xs text-text-secondary bg-surface border border-surface-hover rounded-xl px-3 py-2">
                  <span className="font-medium text-text-primary">
                    {(report.documents_fetched ?? 0).toLocaleString()}
                  </span>{' '}
                  new documents fetched
                </div>
              )}
            </div>

            {(report.coverage_before_fetch || report.coverage_after_fetch) && (
              <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div className="rounded-xl bg-surface border border-surface-hover p-3">
                  <div className="text-text-muted">Before fetch</div>
                  <div className="mt-1 text-text-secondary">
                    Docs: <span className="font-medium text-text-primary">{report.coverage_before_fetch?.document_count ?? 0}</span>{' '}
                    · Avg relevance: <span className="font-medium text-text-primary">{(report.coverage_before_fetch?.avg_relevance ?? 0).toFixed(2)}</span>
                  </div>
                </div>
                <div className="rounded-xl bg-surface border border-surface-hover p-3">
                  <div className="text-text-muted">After fetch</div>
                  <div className="mt-1 text-text-secondary">
                    Docs: <span className="font-medium text-text-primary">{report.coverage_after_fetch?.document_count ?? report.coverage_before_fetch?.document_count ?? 0}</span>{' '}
                    · Avg relevance: <span className="font-medium text-text-primary">{((report.coverage_after_fetch?.avg_relevance ?? report.coverage_before_fetch?.avg_relevance) ?? 0).toFixed(2)}</span>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Results */}
        {report && !isLoading && (
          <div className="space-y-6 animate-in fade-in duration-500">
            {/* Answer Panel - Full Width */}
            <AnswerPanel report={report} />

            {/* Agentic Debate Panel (when enabled) */}
            {report.used_agentic_debate && (report.debate_advocates?.length ?? 0) > 0 && (
              <DebatePanel report={report} />
            )}

            {/* Two Column Layout for Evidence + Confidence */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Evidence Map - Takes 2 columns */}
              <div className="lg:col-span-2">
                <EvidenceMap claims={report.claims} />
              </div>

              {/* Right Sidebar - Confidence + Gaps */}
              <div className="space-y-6">
                <ConfidenceMeter report={report} />
                <GapsPanel globalGaps={report.global_gaps} />
              </div>
            </div>
          </div>
        )}

        {/* Empty State */}
        {!report && !isLoading && !error && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="w-24 h-24 rounded-2xl bg-surface-elevated flex items-center justify-center mb-6">
              <svg className="w-12 h-12 text-text-muted" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
              </svg>
            </div>
            <h2 className="text-2xl font-semibold text-text-primary mb-2">Ask a Medical Question</h2>
            <p className="text-text-muted max-w-md">
              Get evidence-based answers with transparent confidence scores and source attribution. 
              Our AI verifies every claim against peer-reviewed literature.
            </p>
          </div>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-surface-hover mt-16">
        <div className="max-w-7xl mx-auto px-6 py-6 space-y-4">
          <div className="flex flex-wrap justify-center gap-x-4 gap-y-2">
            <SystemStatus />
          </div>
          <p className="text-sm text-text-muted text-center">
            <span className="font-semibold">Disclaimer:</span> This tool is for informational purposes only 
            and should not be used as a substitute for professional medical advice, diagnosis, or treatment.
          </p>
        </div>
      </footer>
    </div>
  );
}

export default App;
