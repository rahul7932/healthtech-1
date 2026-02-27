import { useState } from 'react';
import type { Claim, EvidenceReference } from '../types';

interface EvidenceMapProps {
  claims: Claim[];
}

function EvidenceDoc({ doc, type }: { doc: EvidenceReference; type: 'supporting' | 'contradicting' | 'neutral' }) {
  const colorClass = type === 'supporting'
    ? 'border-supports/30 bg-supports/5'
    : type === 'contradicting'
    ? 'border-contradicts/30 bg-contradicts/5'
    : 'border-neutral/30 bg-neutral/5';
  
  const iconColor = type === 'supporting' ? 'text-supports' : type === 'contradicting' ? 'text-contradicts' : 'text-neutral';

  return (
    <a
      href={`https://pubmed.ncbi.nlm.nih.gov/${doc.pmid}/`}
      target="_blank"
      rel="noopener noreferrer"
      className={`block p-3 rounded-lg border ${colorClass} hover:opacity-80 transition-opacity`}
    >
      <div className="flex items-start gap-2">
        <div className={`mt-0.5 ${iconColor}`}>
          {type === 'supporting' ? (
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clipRule="evenodd" />
            </svg>
          ) : type === 'contradicting' ? (
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clipRule="evenodd" />
            </svg>
          ) : (
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clipRule="evenodd" />
            </svg>
          )}
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-text-primary text-sm font-medium line-clamp-2">{doc.title}</p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-text-muted text-xs font-mono">PMID:{doc.pmid}</span>
            <span className="text-text-muted text-xs">•</span>
            <span className="text-text-muted text-xs">
              Relevance: {(doc.relevance_score * 100).toFixed(0)}%
            </span>
          </div>
        </div>
      </div>
    </a>
  );
}

function ClaimCard({ claim, index }: { claim: Claim; index: number }) {
  const [isExpanded, setIsExpanded] = useState(index === 0);

  const totalDocs = claim.supporting_docs.length + claim.contradicting_docs.length + claim.neutral_docs.length;
  
  // Confidence color
  const confidenceColor = claim.confidence >= 0.7 
    ? 'text-trust-high' 
    : claim.confidence >= 0.4 
    ? 'text-trust-medium' 
    : 'text-trust-low';

  return (
    <div className="bg-surface rounded-xl border border-surface-hover overflow-hidden">
      {/* Claim header - always visible */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-4 text-left hover:bg-surface-hover/30 transition-colors"
      >
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-mono text-text-muted bg-surface-hover px-2 py-0.5 rounded">
                #{index + 1}
              </span>
              <span className={`text-xs font-semibold ${confidenceColor}`}>
                {(claim.confidence * 100).toFixed(0)}% confident
              </span>
            </div>
            <p className="text-text-primary text-sm leading-relaxed">{claim.text}</p>
          </div>
          
          <div className="flex items-center gap-2 shrink-0">
            {/* Evidence count badges */}
            {claim.supporting_docs.length > 0 && (
              <span className="flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-supports/20 text-supports">
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                </svg>
                {claim.supporting_docs.length}
              </span>
            )}
            {claim.contradicting_docs.length > 0 && (
              <span className="flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-contradicts/20 text-contradicts">
                <svg className="w-3 h-3" fill="currentColor" viewBox="0 0 20 20">
                  <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
                </svg>
                {claim.contradicting_docs.length}
              </span>
            )}
            
            {/* Expand/collapse icon */}
            <svg 
              className={`w-5 h-5 text-text-muted transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </div>
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && totalDocs > 0 && (
        <div className="px-4 pb-4 space-y-4 border-t border-surface-hover pt-4">
          {/* Supporting evidence */}
          {claim.supporting_docs.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-supports uppercase tracking-wider mb-2">
                Supporting Evidence ({claim.supporting_docs.length})
              </h4>
              <div className="space-y-2">
                {claim.supporting_docs.map((doc) => (
                  <EvidenceDoc key={doc.pmid} doc={doc} type="supporting" />
                ))}
              </div>
            </div>
          )}

          {/* Contradicting evidence */}
          {claim.contradicting_docs.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-contradicts uppercase tracking-wider mb-2">
                Contradicting Evidence ({claim.contradicting_docs.length})
              </h4>
              <div className="space-y-2">
                {claim.contradicting_docs.map((doc) => (
                  <EvidenceDoc key={doc.pmid} doc={doc} type="contradicting" />
                ))}
              </div>
            </div>
          )}

          {/* Neutral/mentioned */}
          {claim.neutral_docs.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-neutral uppercase tracking-wider mb-2">
                Mentioned ({claim.neutral_docs.length})
              </h4>
              <div className="space-y-2">
                {claim.neutral_docs.map((doc) => (
                  <EvidenceDoc key={doc.pmid} doc={doc} type="neutral" />
                ))}
              </div>
            </div>
          )}

          {/* Missing evidence for this claim */}
          {claim.missing_evidence.length > 0 && (
            <div>
              <h4 className="text-xs font-semibold text-trust-medium uppercase tracking-wider mb-2">
                Evidence Gaps
              </h4>
              <ul className="space-y-1">
                {claim.missing_evidence.map((gap, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                    <svg className="w-4 h-4 mt-0.5 text-trust-medium shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                    {gap}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function EvidenceMap({ claims }: EvidenceMapProps) {
  return (
    <div className="bg-surface-elevated rounded-2xl p-6 border border-surface-hover">
      <div className="flex items-center gap-3 mb-4">
        <div className="w-10 h-10 rounded-xl bg-supports/20 flex items-center justify-center">
          <svg className="w-5 h-5 text-supports" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-3 7h3m-3 4h3m-6-4h.01M9 16h.01" />
          </svg>
        </div>
        <div>
          <h2 className="text-xl font-semibold text-text-primary">Evidence Map</h2>
          <p className="text-text-muted text-sm">{claims.length} claims extracted</p>
        </div>
      </div>

      <div className="space-y-3">
        {claims.map((claim, i) => (
          <ClaimCard key={claim.id} claim={claim} index={i} />
        ))}
      </div>
    </div>
  );
}
