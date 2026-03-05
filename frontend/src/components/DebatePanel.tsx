import { useState } from 'react';
import type { DebateAdvocateView, TrustReport } from '../types';

interface DebatePanelProps {
  report: TrustReport;
}

export function DebatePanel({ report }: DebatePanelProps) {
  const advocates = report.debate_advocates ?? [];
  const usedDebate = report.used_agentic_debate && advocates.length > 0;

  const [showTranscript, setShowTranscript] = useState(false);

  if (!usedDebate) {
    return null;
  }

  return (
    <div className="bg-surface-elevated rounded-2xl p-6 border border-surface-hover">
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-accent/20 flex items-center justify-center">
            <svg className="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 8h10M7 12h4m-2 8a8 8 0 100-16 8 8 0 000 16z" />
            </svg>
          </div>
          <div>
            <h2 className="text-xl font-semibold text-text-primary">Agentic Debate</h2>
            <p className="text-sm text-text-muted">
              {advocates.length} debate agent{advocates.length === 1 ? '' : 's'} argued from different document groups.
            </p>
          </div>
        </div>
        {report.debate_metadata && typeof report.debate_metadata.total_time_seconds === 'number' && (
          <div className="shrink-0 text-xs text-text-secondary bg-surface border border-surface-hover rounded-xl px-3 py-2">
            <span className="font-medium text-text-primary">
              {report.debate_metadata.total_time_seconds.toFixed(1)}s
            </span>{' '}
            total debate time
          </div>
        )}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        {advocates.map((adv: DebateAdvocateView) => (
          <div
            key={adv.group_id}
            className="rounded-xl bg-surface border border-surface-hover p-4 flex flex-col gap-2"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs font-mono text-text-muted bg-surface-hover px-2 py-0.5 rounded">
                    {adv.group_id.toUpperCase()}
                  </span>
                  <span className="text-xs font-semibold text-trust-high">
                    {(adv.confidence * 100).toFixed(0)}% confident
                  </span>
                </div>
                <p className="text-sm text-text-secondary line-clamp-3">
                  {adv.argument}
                </p>
              </div>
            </div>

            {adv.key_findings.length > 0 && (
              <div className="mt-2">
                <h3 className="text-xs font-semibold text-text-muted uppercase tracking-wide mb-1">
                  Key findings
                </h3>
                <ul className="space-y-1 text-xs text-text-secondary">
                  {adv.key_findings.map((finding, idx) => (
                    <li key={idx} className="flex items-start gap-2">
                      <span className="mt-1 h-1 w-1 rounded-full bg-accent shrink-0" />
                      <span>{finding}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {adv.cited_pmids.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {adv.cited_pmids.slice(0, 6).map((pmid) => (
                  <a
                    key={pmid}
                    href={`https://pubmed.ncbi.nlm.nih.gov/${pmid}/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center px-1.5 py-0.5 rounded border border-surface-hover bg-surface text-[11px] font-mono text-text-muted hover:border-accent hover:text-accent transition-colors"
                    title={`PMID: ${pmid}`}
                  >
                    {pmid}
                  </a>
                ))}
                {adv.cited_pmids.length > 6 && (
                  <span className="text-[11px] text-text-muted">
                    +{adv.cited_pmids.length - 6} more
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {report.debate_synthesis_reasoning && (
        <div className="mt-4 pt-4 border-t border-surface-hover">
          <h3 className="text-sm font-semibold text-text-primary mb-1">
            How the final answer was synthesized
          </h3>
          <p className="text-sm text-text-secondary leading-relaxed">
            {report.debate_synthesis_reasoning}
          </p>
        </div>
      )}

      {report.debate_transcript && (
        <div className="mt-4 pt-4 border-t border-surface-hover">
          <button
            type="button"
            onClick={() => setShowTranscript((v) => !v)}
            className="flex items-center gap-2 text-xs font-medium text-text-secondary hover:text-text-primary transition-colors"
          >
            <svg
              className={`w-4 h-4 transition-transform duration-200 ${showTranscript ? 'rotate-90' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            <span>{showTranscript ? 'Hide full debate transcript' : 'Show full debate transcript'}</span>
          </button>
          {showTranscript && (
            <pre className="mt-3 max-h-64 overflow-auto rounded-xl bg-surface border border-surface-hover p-3 text-xs text-text-muted whitespace-pre-wrap">
              {report.debate_transcript}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

