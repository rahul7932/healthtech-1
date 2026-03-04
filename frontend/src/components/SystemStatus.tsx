import { useState, useEffect } from 'react';
import { healthCheck, getDocumentCounts } from '../api/client';

export function SystemStatus() {
  const [health, setHealth] = useState<'ok' | 'error' | null>(null);
  const [counts, setCounts] = useState<{ total: number; with_embeddings: number } | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const [healthRes, countRes] = await Promise.all([
          healthCheck(),
          getDocumentCounts(),
        ]);
        if (!cancelled) {
          setHealth(healthRes.status === 'ok' ? 'ok' : 'error');
          setCounts({
            total: countRes.total,
            with_embeddings: countRes.with_embeddings,
          });
        }
      } catch {
        if (!cancelled) {
          setHealth('error');
          setCounts(null);
        }
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  if (health === null && counts === null) {
    return (
      <div className="flex items-center gap-2 text-text-muted text-xs">
        <span className="inline-block w-2 h-2 rounded-full bg-text-muted animate-pulse" />
        Checking system…
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-muted">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block w-2 h-2 rounded-full shrink-0 ${health === 'ok' ? 'bg-trust-high' : 'bg-contradicts'
            }`}
        />
        <span>Backend {health === 'ok' ? 'connected' : 'unavailable'}</span>
      </div>
      {counts !== null && (
        <>
          <span className="text-surface-hover">·</span>
          <span>
            <span className="font-medium text-text-secondary">{counts.with_embeddings.toLocaleString()}</span>
            {' '}documents indexed (PubMed)
          </span>
        </>
      )}
      <span className="text-surface-hover">·</span>
      <span>Evidence from PubMed only</span>
    </div>
  );
}
