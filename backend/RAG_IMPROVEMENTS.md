# RAG Pipeline Improvement Plan

This document outlines potential improvements to the medical RAG system, organized by component and priority.

---

## Current Architecture

```
Query → Retriever (pgvector) → Generator (GPT-4o) → Trust Layer → TrustReport
                                                         ↓
                                          ClaimExtractor → AttributionScorer
                                                         → ConfidenceCalculator
                                                         → GapDetector
```

---

## 1. Retrieval Improvements

### 1.1 Hybrid Search (BM25 + Vector)
**Priority: High | Effort: Medium**

Current system uses pure semantic search. Hybrid search combines keyword matching with vector similarity—important for exact medical terms that embeddings might miss.

**Implementation:**
- Add PostgreSQL full-text search (`ts_vector`) or `pg_trgm` for keyword matching
- Combine scores: `final_score = alpha * semantic_score + (1 - alpha) * bm25_score`
- Tune `alpha` based on evaluation (start with 0.7)

**Files to modify:**
- `app/services/retriever.py`
- `app/models/document.py` (add GIN index for full-text)

---

### 1.2 Query Rewriting / Expansion
**Priority: High | Effort: Low**

Medical queries often use different terminology than papers. Expand queries before retrieval.

**Example:**
```
Input:  "Does metformin help with weight loss?"
Output: "metformin weight reduction obesity body mass index BMI antidiabetic"
```

**Implementation:**
- Add `QueryExpander` service using GPT-4o-mini
- Run before retrieval, cache expansions

**Files to create:**
- `app/services/query_expander.py`

---

### 1.3 Cross-Encoder Re-ranking
**Priority: High | Effort: Medium**

Bi-encoder (current) is fast but approximate. Cross-encoder re-ranking on top-K improves precision significantly.

**Pipeline:**
```
Retriever (top 50) → Cross-Encoder Re-rank → Top 10 to Generator
```

**Models to consider:**
- `cross-encoder/ms-marco-MiniLM-L-12-v2` (general)
- `pritamdeka/BioBERT-mnli-snli-scinli-scitail-mednli-stsb` (medical)

**Implementation:**
- Add `Reranker` service using sentence-transformers
- Run on retriever output before passing to generator

**Files to create:**
- `app/services/reranker.py`

**Dependencies to add:**
- `sentence-transformers`

---

### 1.4 HyDE (Hypothetical Document Embeddings)
**Priority: Medium | Effort: Low**

Instead of embedding the query directly, generate a hypothetical answer first, then embed that. Matches document style better.

**Pipeline:**
```
Query → Generate hypothetical answer → Embed answer → Search
```

**Implementation:**
- Add `HyDERetriever` as alternative retrieval strategy
- Use GPT-4o-mini for hypothetical generation (cheap, fast)

**Files to modify:**
- `app/services/retriever.py` (add HyDE mode)

---

### 1.5 Metadata Filtering
**Priority: Medium | Effort: Low**

Add pre-retrieval filters to improve result quality.

**Filters to support:**
- Recency: `WHERE publication_date > '2015-01-01'`
- Study type: RCT, meta-analysis, cohort, case-report
- Journal quality: high-impact journals list

**Implementation:**
- Add optional filters to `QueryRequest` schema
- Modify retriever SQL to include WHERE clauses

**Files to modify:**
- `app/models/schemas.py` (add filter fields to QueryRequest)
- `app/services/retriever.py` (add filter logic)
- `app/models/document.py` (add study_type field)

---

## 2. Generation Improvements

### 2.1 Relevance-Aware Context Formatting
**Priority: Medium | Effort: Low**

Currently all documents are passed equally. Group by relevance to help the model prioritize.

**Format:**
```
=== HIGH RELEVANCE (>0.85) ===
[PMID:12345] ...

=== MODERATE RELEVANCE (0.70-0.85) ===
[PMID:67890] ...
```

**Files to modify:**
- `app/services/generator.py` (`_format_context` method)

---

### 2.2 Multi-Pass Generation
**Priority: Medium | Effort: Medium**

Use Trust Layer output to trigger re-generation when gaps are found.

**Pipeline:**
```
Generate → Trust Layer → If gaps detected → Retrieve more → Re-generate
```

**Implementation:**
- Add iteration logic in routes.py
- Set max iterations (e.g., 2) to prevent loops

**Files to modify:**
- `app/api/routes.py` (query endpoint)

---

### 2.3 Structured Citation Output
**Priority: Low | Effort: Medium**

Instead of inline `[PMID:xxx]`, have the model output structured JSON with claim-citation pairs. More reliable parsing.

**Output format:**
```json
{
  "claims": [
    {
      "text": "ACE inhibitors reduce mortality",
      "citations": ["12345", "67890"],
      "confidence_hint": "high"
    }
  ]
}
```

**Trade-off:** More structured but may reduce natural flow of text.

---

## 3. Trust Layer Enhancements

### 3.1 NLI-Based Attribution Verification
**Priority: High | Effort: Medium**

Add dedicated Natural Language Inference model for entailment detection.

**Models:**
- `microsoft/deberta-v3-large-mnli`
- `MoritzLaworski/mDeBERTa-v3-base-mnli-xnli` (multilingual)

**Pipeline:**
```
For each (claim, cited_document):
    entailment_score = NLI(premise=document, hypothesis=claim)
    # Output: entailment / contradiction / neutral
```

**Files to modify:**
- `app/services/trust/attribution_scorer.py`

**Dependencies to add:**
- `transformers`

---

### 3.2 Citation Hallucination Detection
**Priority: High | Effort: Low**

Verify that cited PMIDs actually exist in retrieved documents. Currently possible the LLM hallucinates PMIDs.

**Implementation:**
```python
def verify_citations(answer: str, retrieved_docs: list[Document]) -> list[str]:
    """Return list of hallucinated PMIDs."""
    cited_pmids = extract_pmids(answer)
    retrieved_pmids = {doc.pmid for doc in retrieved_docs}
    return [pmid for pmid in cited_pmids if pmid not in retrieved_pmids]
```

**Files to modify:**
- `app/services/trust/attribution_scorer.py` (add verification step)

---

### 3.3 Confidence Calibration
**Priority: Medium | Effort: High**

Train or calibrate confidence scores against human judgments so scores are meaningful (0.8 = 80% accurate).

**Approach:**
1. Collect human ratings on claim accuracy
2. Plot calibration curve (predicted vs actual)
3. Apply isotonic regression or Platt scaling

**Requires:** Human evaluation dataset

---

## 4. Data Quality Improvements

### 4.1 Sentence-Level Chunking
**Priority: Medium | Effort: Medium**

Currently embedding full abstracts. Long abstracts dilute the embedding signal.

**Options:**
- **Option A:** Sentence-level chunks (precise, more storage)
- **Option B:** Section-based (Background, Methods, Results, Conclusion)
- **Option C:** Keep abstract + store sentence embeddings for re-ranking

**Files to modify:**
- `app/services/embeddings.py`
- `app/models/document.py` (add chunks table)

---

### 4.2 Full-Text Retrieval
**Priority: Low | Effort: High**

Abstracts are summaries. Methods/Results sections often have critical details.

**Implementation:**
- Integrate PMC Open Access for full papers
- Add section-level chunking and storage

**Dependencies:**
- PMC API integration
- Significantly more storage

---

## 5. Infrastructure Improvements

### 5.1 Query Embedding Cache
**Priority: Medium | Effort: Low**

Cache embeddings for common/repeated queries.

**Implementation:**
- Redis cache with TTL
- Key: hash of query text
- Value: embedding vector

**Files to create:**
- `app/services/cache.py`

**Dependencies to add:**
- `redis`

---

### 5.2 Retrieval Logging & Analytics
**Priority: Medium | Effort: Low**

Log retrieval results for analysis and improvement.

**Data to log:**
- Query text
- Retrieved PMIDs + scores
- Final answer confidence
- User feedback (if available)

**Files to create:**
- `app/services/analytics.py`
- `app/models/query_log.py`

---

### 5.3 Streaming Responses
**Priority: Low | Effort: Medium**

Stream generation output for better UX on long answers.

**Implementation:**
- Use OpenAI streaming API
- SSE (Server-Sent Events) to frontend

---

## 6. Advanced: Agentic RAG

**Priority: Low | Effort: High**

Let the system decide when retrieval is needed and iterate autonomously.

**Capabilities:**
- Decide if more documents are needed
- Reformulate query if results are poor
- Search for specific missing evidence types
- Handle multi-hop reasoning

**Implementation:**
- Add `RAGAgent` orchestrator
- Define action space: retrieve, generate, verify, search_more

---

## Implementation Priority Matrix

| Improvement | Impact | Effort | Priority |
|-------------|--------|--------|----------|
| Citation hallucination detection | High | Low | P0 |
| Hybrid search (BM25 + vector) | High | Medium | P0 |
| Cross-encoder re-ranking | High | Medium | P1 |
| Query rewriting/expansion | High | Low | P1 |
| NLI-based attribution | High | Medium | P1 |
| Metadata filtering | Medium | Low | P2 |
| Relevance-aware formatting | Medium | Low | P2 |
| HyDE retrieval | Medium | Low | P2 |
| Query embedding cache | Medium | Low | P2 |
| Multi-pass generation | Medium | Medium | P3 |
| Sentence-level chunking | Medium | Medium | P3 |
| Confidence calibration | Medium | High | P3 |
| Full-text retrieval | Low | High | P4 |
| Agentic RAG | Low | High | P4 |

---

## Next Steps

1. **Quick wins first:** Implement citation hallucination detection (P0, low effort)
2. **Core retrieval:** Add hybrid search and cross-encoder re-ranking
3. **Evaluate:** Set up evaluation dataset to measure improvements
4. **Iterate:** Use analytics to identify bottlenecks

---

## Evaluation Metrics

To measure improvements, track:

- **Retrieval:** Recall@K, MRR, nDCG
- **Generation:** Citation accuracy, factual correctness (human eval)
- **Trust Layer:** Calibration error, gap detection precision
- **End-to-end:** User satisfaction, answer usefulness

---

*Last updated: February 2026*
