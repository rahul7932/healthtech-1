import { useState, useEffect } from 'react';
import { getDocumentCounts } from '../api/client';

export function DocumentCount() {
  const [counts, setCounts] = useState<{ total: number; embedded: number; pending: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    getDocumentCounts()
      .then((res) => {
        if (!cancelled) {
          setCounts({ total: res.total, embedded: res.embedded, pending: res.pending });
        }
      })
      .catch(() => {
        if (!cancelled) setCounts(null);
      });
    return () => { cancelled = true; };
  }, []);

  if (counts === null) return null;

  return (
    <span className="text-sm text-text-muted">
      <span className="font-medium text-text-secondary">{counts.embedded.toLocaleString()}</span>
      {' '}documents indexed (PubMed)
    </span>
  );
}
