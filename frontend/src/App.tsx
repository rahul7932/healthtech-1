import { useState } from 'react';
import { QueryInput, AnswerPanel, EvidenceMap, ConfidenceMeter, GapsPanel } from './components';
import { submitQuery, ApiError } from './api/client';
import type { TrustReport } from './types';

function App() {
  const [report, setReport] = useState<TrustReport | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleQuery = async (question: string) => {
    setIsLoading(true);
    setError(null);
    
    try {
      const result = await submitQuery({ question, top_k: 5 });
      setReport(result);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
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

        {/* Loading State */}
        {isLoading && (
          <div className="flex flex-col items-center justify-center py-20">
            <div className="relative w-20 h-20">
              <div className="absolute inset-0 rounded-full border-4 border-surface-hover"></div>
              <div className="absolute inset-0 rounded-full border-4 border-accent border-t-transparent animate-spin"></div>
            </div>
            <p className="mt-6 text-text-secondary text-lg">Analyzing evidence...</p>
            <p className="mt-2 text-text-muted text-sm">This may take a moment</p>
          </div>
        )}

        {/* Results */}
        {report && !isLoading && (
          <div className="space-y-6 animate-in fade-in duration-500">
            {/* Answer Panel - Full Width */}
            <AnswerPanel report={report} />

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
        <div className="max-w-7xl mx-auto px-6 py-6">
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
