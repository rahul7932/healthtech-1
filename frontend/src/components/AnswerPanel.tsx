import { useMemo, useState } from 'react';
import type { TrustReport } from '../types';

interface AnswerPanelProps {
  report: TrustReport;
}

export function AnswerPanel({ report }: AnswerPanelProps) {
  // Parse the answer and highlight PMID citations
  const formattedAnswer = useMemo(() => {
    // Match [PMID:xxxxx] patterns
    const pmidRegex = /\[PMID:(\d+)\]/g;
    const parts: (string | { pmid: string })[] = [];
    let lastIndex = 0;
    let match;

    while ((match = pmidRegex.exec(report.answer)) !== null) {
      // Add text before the citation
      if (match.index > lastIndex) {
        parts.push(report.answer.slice(lastIndex, match.index));
      }
      // Add the citation as an object
      parts.push({ pmid: match[1] });
      lastIndex = match.index + match[0].length;
    }

    // Add remaining text
    if (lastIndex < report.answer.length) {
      parts.push(report.answer.slice(lastIndex));
    }

    return parts;
  }, [report.answer]);

  // Get all unique PMIDs from all claims for quick lookup
  const pmidInfo = useMemo(() => {
    const info = new Map<string, { title: string; type: 'supporting' | 'contradicting' | 'neutral' }>();
    
    for (const claim of report.claims) {
      for (const doc of claim.supporting_docs) {
        if (!info.has(doc.pmid)) {
          info.set(doc.pmid, { title: doc.title, type: 'supporting' });
        }
      }
      for (const doc of claim.contradicting_docs) {
        if (!info.has(doc.pmid)) {
          info.set(doc.pmid, { title: doc.title, type: 'contradicting' });
        }
      }
      for (const doc of claim.neutral_docs) {
        if (!info.has(doc.pmid)) {
          info.set(doc.pmid, { title: doc.title, type: 'neutral' });
        }
      }
    }
    
    return info;
  }, [report.claims]);

  const [showHowGenerated, setShowHowGenerated] = useState(false);

  return (
    <div className="bg-surface-elevated rounded-2xl p-6 border border-surface-hover">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-accent/20 flex items-center justify-center">
          <svg className="w-5 h-5 text-accent" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
        </div>
        <h2 className="text-xl font-semibold text-text-primary">Answer</h2>
      </div>

      <div className="prose prose-invert max-w-none">
        <p className="text-text-primary leading-relaxed whitespace-pre-wrap">
          {formattedAnswer.map((part, i) => {
            if (typeof part === 'string') {
              return <span key={i}>{part}</span>;
            }
            
            const docInfo = pmidInfo.get(part.pmid);
            const colorClass = docInfo?.type === 'supporting' 
              ? 'bg-supports/20 text-supports border-supports/30 hover:bg-supports/30'
              : docInfo?.type === 'contradicting'
              ? 'bg-contradicts/20 text-contradicts border-contradicts/30 hover:bg-contradicts/30'
              : 'bg-neutral/20 text-neutral border-neutral/30 hover:bg-neutral/30';

            return (
              <a
                key={i}
                href={`https://pubmed.ncbi.nlm.nih.gov/${part.pmid}/`}
                target="_blank"
                rel="noopener noreferrer"
                title={docInfo?.title || `PMID: ${part.pmid}`}
                className={`inline-flex items-center px-1.5 py-0.5 mx-0.5 text-xs font-mono 
                           rounded border transition-colors duration-150 ${colorClass}`}
              >
                {part.pmid}
              </a>
            );
          })}
        </p>
      </div>

      {/* How this answer was generated - collapsible */}
      <div className="mt-6 pt-4 border-t border-surface-hover">
        <button
          type="button"
          onClick={() => setShowHowGenerated(!showHowGenerated)}
          className="flex w-full items-center justify-between gap-2 text-left text-sm font-medium text-text-secondary hover:text-text-primary transition-colors"
        >
          <span>How this answer was generated</span>
          <svg
            className={`w-4 h-4 shrink-0 transition-transform duration-200 ${showHowGenerated ? 'rotate-180' : ''}`}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </button>
        {showHowGenerated && (
          <div className="mt-3 space-y-2 text-sm text-text-muted leading-relaxed">
            <p>
              The model first generated a draft answer from retrieved PubMed abstracts. Our trust layer then extracted {report.claims.length} atomic claim(s), matched each to supporting, contradicting, or neutral studies, and detected evidence gaps. The final answer combines these into a single narrative; citation colors show how each source relates to the claims (support / contradict / neutral).
            </p>
            <p>
              You can expand each claim in the Evidence Map below to see the exact studies and relevance scores used.
            </p>
          </div>
        )}
      </div>

      {/* Citation Legend */}
      <div className="mt-6 pt-4 border-t border-surface-hover">
        <div className="flex flex-wrap gap-4 text-sm">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-supports"></span>
            <span className="text-text-secondary">Supports claim</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-contradicts"></span>
            <span className="text-text-secondary">Contradicts claim</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-neutral"></span>
            <span className="text-text-secondary">Neutral/Mentioned</span>
          </div>
        </div>
      </div>
    </div>
  );
}
