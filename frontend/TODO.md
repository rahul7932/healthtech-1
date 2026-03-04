# Frontend TODO

## AI process transparency (implemented)

The following items are **done** and live in this repo:

| # | Item | Where |
|---|------|--------|
| 9.1 | Multi-step pipeline indicator for `/api/query` | `PipelineStepper.tsx`, `App.tsx` (loading state) |
| 9.2 | System status and data coverage | `SystemStatus.tsx`, footer in `App.tsx` |
| 9.3 | Explain query handling | `QueryInput.tsx` (copy under textarea) |
| 9.4 | “How this answer was generated” | `AnswerPanel.tsx` (collapsible section) |
| 9.5 | Evidence Map step + relevance explanation | `EvidenceMap.tsx` (header + description) |
| 9.6 | Confidence computation + low/moderate reason | `ConfidenceMeter.tsx` (“How we compute this” + reason box) |
| 9.7 | Explain gap detection in GapsPanel | `GapsPanel.tsx` (description + note) |

## Optional / future

- **9.8** — Optional “Advanced / AI activity log” panel: collapsible panel logging key events during a query (retrieval, N docs, claims, confidence) and optionally extra signals (e.g. retrieval scores, documents considered but not used).

---

*Last updated: March 2026*
