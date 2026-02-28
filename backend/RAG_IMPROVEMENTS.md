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

#### Understanding Bi-Encoders vs Cross-Encoders

**Bi-Encoder (current approach):**
```
Query    → Embed independently → [vector A]  ─┐
                                              ├─→ Cosine similarity → Score
Document → Embed independently → [vector B]  ─┘
```
- Query and document are embedded **separately**
- Fast because document embeddings are pre-computed at ingest time
- Limitation: the model never "sees" query and document together, so it can miss nuanced relevance

**Cross-Encoder:**
```
┌─────────────────────────────────────────────────────────────┐
│ [CLS] Query text here [SEP] Document text here [SEP]       │
└─────────────────────────────────────────────────────────────┘
                              ↓
                    Transformer processes ALL tokens together
                              ↓
                    Relevance score: 0.92
```
- Query and document are processed **together** in a single forward pass
- The model attends to both simultaneously, capturing fine-grained interactions
- Much more accurate, but slow (can't pre-compute anything)
- **Does NOT produce embeddings** — outputs a relevance score directly

#### What are [CLS] and [SEP] tokens?

These are special tokens used by BERT-style transformers:

- **[CLS]** (Classification): Placed at the start. The model learns to encode the "meaning of the whole input" into this token's position. Used for classification tasks.
- **[SEP]** (Separator): Marks boundaries between different text segments. Tells the model "here's where one piece ends and another begins."

The cross-encoder feeds [CLS] vector into a classifier head that outputs a relevance score (0-1).

#### Two-Stage Pipeline

Cross-encoders are too slow to run on entire database. Solution: use both approaches.

```
STAGE 1: Bi-encoder (fast, approximate)
─────────────────────────────────────────
Query: "Do ACE inhibitors help heart failure?"
    ↓
OpenAI embed query → [0.2, -0.4, 0.8, ...]
    ↓
Compare to pre-embedded docs in pgvector
    ↓
Get top 50 candidates (~50ms)


STAGE 2: Cross-encoder (slow, accurate)
─────────────────────────────────────────
For each of those 50 docs:
    Feed raw text into cross-encoder model
    Get relevance score
    ↓
Sort by cross-encoder score
Return top 10 (~200ms)
```

#### Why This Matters for Medical RAG

Medical literature has extensive synonym issues that bi-encoders can miss:

| Query Term | Document Term | Bi-Encoder | Cross-Encoder |
|------------|---------------|------------|---------------|
| heart attack | myocardial infarction | May miss | Understands |
| high blood pressure | hypertension | Weak match | Strong match |
| Advil | ibuprofen | May miss | Understands |
| ACE inhibitors | angiotensin-converting enzyme inhibitors | Partial | Full match |

Cross-encoders see both texts together and can reason about whether they discuss the same concept.

#### Cost and Latency Trade-offs

| Aspect | Bi-Encoder | Cross-Encoder |
|--------|------------|---------------|
| **API cost** | Paid (OpenAI) | Free (local model) |
| **Latency** | ~50ms | +100-300ms |
| **Hardware** | Minimal | CPU/GPU |
| **Accuracy** | Good | Better |

The cross-encoder runs locally (no API calls), so it adds latency but not cost.

#### Comparison with Alternative Approaches

| Era | Approach | Speed | Accuracy | Notes |
|-----|----------|-------|----------|-------|
| Current | Bi-encoder only | Fast | Good | Your current setup |
| Recommended | Bi + Cross-encoder | Medium | Better | Proven production pattern |
| 2020+ | ColBERT (late interaction) | Medium | Better | Stores multiple vectors per doc |
| 2023+ | LLM reranker (GPT-4) | Slow | Best | Expensive (~$0.25/query) |

The bi-encoder + cross-encoder pattern is like HTTPS: not bleeding edge, but proven, well-understood, and the right choice for most production systems.

#### Models to Consider

**General purpose:**
- `cross-encoder/ms-marco-MiniLM-L-12-v2` — Fast, good quality
- `cross-encoder/ms-marco-MiniLM-L-6-v2` — Faster, slightly lower quality

**Medical/scientific:**
- `pritamdeka/BioBERT-mnli-snli-scinli-scitail-mednli-stsb` — Trained on medical NLI
- `cross-encoder/stsb-roberta-base` — Good for semantic similarity

**MS MARCO** = Microsoft Machine Reading Comprehension — a dataset of millions of (query, document, relevance) examples from Bing search, used to train these models.

#### Implementation

```python
from sentence_transformers import CrossEncoder

class Reranker:
    def __init__(self):
        self.model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-12-v2')
    
    def rerank(
        self, 
        query: str, 
        documents: list[DocumentWithScore], 
        top_k: int = 10
    ) -> list[DocumentWithScore]:
        """Re-rank documents using cross-encoder."""
        
        # Create (query, document) pairs
        pairs = [(query, doc.abstract) for doc in documents]
        
        # Get cross-encoder scores
        scores = self.model.predict(pairs)
        
        # Sort by score and return top_k
        doc_scores = list(zip(documents, scores))
        doc_scores.sort(key=lambda x: x[1], reverse=True)
        
        # Update relevance_score with cross-encoder score
        reranked = []
        for doc, score in doc_scores[:top_k]:
            doc.relevance_score = float(score)
            reranked.append(doc)
        
        return reranked
```

**Files to create:**
- `app/services/reranker.py`

**Files to modify:**
- `app/api/routes.py` (call reranker after retriever)

**Dependencies to add:**
- `sentence-transformers`
- `torch` (if not already installed)

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

Add a dedicated Natural Language Inference (NLI) model to verify that documents actually support the claims that cite them.

#### What is NLI?

Natural Language Inference is a classification task where a model determines the relationship between two texts:

- **Premise**: The source text (in our case, the document abstract)
- **Hypothesis**: The statement to verify (in our case, a claim)

The model outputs one of three labels:
- **Entailment**: The premise supports/implies the hypothesis
- **Contradiction**: The premise contradicts the hypothesis
- **Neutral**: No clear logical relationship

#### Why Use NLI Instead of GPT?

| Approach | Speed | Cost | Accuracy | Runs Locally |
|----------|-------|------|----------|--------------|
| GPT-4o-mini (current) | ~500ms | ~$0.001/pair | Good | No |
| NLI model (proposed) | ~50ms | Free | Good for this task | Yes |

NLI models are **trained specifically for this task** on millions of premise-hypothesis pairs. They're faster, cheaper, and don't require API calls.

#### How It Works

```
Premise (document):
"Our randomized controlled trial of 5,000 patients showed that ACE inhibitors 
reduced all-cause mortality by 23% compared to placebo (p<0.001)."

Hypothesis (claim):
"ACE inhibitors reduce mortality"

                    ↓
              NLI Model
                    ↓
              
Output: ENTAILMENT (confidence: 0.94)
```

Another example showing contradiction detection:

```
Premise (document):
"Our study found no significant difference in mortality between ACE inhibitor 
and placebo groups (HR 0.98, 95% CI 0.87-1.10)."

Hypothesis (claim):
"ACE inhibitors significantly reduce mortality"

                    ↓
              NLI Model
                    ↓
              
Output: CONTRADICTION (confidence: 0.89)
```

#### Models to Consider

**General NLI models:**
- `microsoft/deberta-v3-large-mnli` — Best accuracy, larger (400M params)
- `microsoft/deberta-v3-base-mnli` — Good balance of speed/accuracy
- `facebook/bart-large-mnli` — Fast, good for zero-shot

**Medical/Scientific NLI models:**
- `microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract` — Trained on PubMed
- `pritamdeka/BioBERT-mnli-snli-scinli-scitail-mednli-stsb` — Medical NLI
- `allenai/scibert_scivocab_uncased` — Scientific text

#### Training Data Behind These Models

NLI models are trained on datasets like:
- **MNLI** (Multi-Genre NLI): 433K sentence pairs across genres
- **SNLI** (Stanford NLI): 570K human-written pairs
- **MedNLI**: 14K clinical sentence pairs from MIMIC-III
- **SciTail**: Science exam entailment dataset

#### Integration with Current Attribution Scorer

Current flow:
```
Claims + Documents → GPT-4o-mini evaluates each pair → supports/contradicts/neutral
```

Proposed flow:
```
Claims + Documents → NLI model evaluates each pair → entailment/contradiction/neutral
                            ↓
                  (Optional) GPT-4o-mini for edge cases only
```

#### Implementation

```python
from transformers import pipeline

class NLIVerifier:
    """
    Verifies claim-document attribution using Natural Language Inference.
    """
    
    def __init__(self, model_name: str = "microsoft/deberta-v3-base-mnli"):
        self.nli = pipeline(
            "zero-shot-classification",
            model=model_name,
            device=0 if torch.cuda.is_available() else -1  # GPU if available
        )
    
    def verify(self, claim: str, document: str) -> dict:
        """
        Check if document supports the claim.
        
        Returns:
            {
                "label": "entailment" | "contradiction" | "neutral",
                "confidence": 0.94,
                "scores": {"entailment": 0.94, "contradiction": 0.03, "neutral": 0.03}
            }
        """
        # Truncate document if too long (model max ~512 tokens)
        doc_truncated = document[:2000]
        
        result = self.nli(
            doc_truncated,
            candidate_labels=["entailment", "contradiction", "neutral"],
            hypothesis=claim
        )
        
        return {
            "label": result["labels"][0],
            "confidence": result["scores"][0],
            "scores": dict(zip(result["labels"], result["scores"]))
        }
    
    def verify_batch(self, pairs: list[tuple[str, str]]) -> list[dict]:
        """Verify multiple claim-document pairs efficiently."""
        return [self.verify(claim, doc) for claim, doc in pairs]


# Usage in AttributionScorer
async def score_with_nli(claims, documents):
    verifier = NLIVerifier()
    
    for claim in claims:
        for doc in documents:
            result = verifier.verify(claim.text, doc.abstract)
            
            if result["label"] == "entailment" and result["confidence"] > 0.7:
                claim.supporting_docs.append(doc)
            elif result["label"] == "contradiction" and result["confidence"] > 0.7:
                claim.contradicting_docs.append(doc)
            else:
                claim.neutral_docs.append(doc)
```

#### Confidence Thresholds

Recommended thresholds for medical claims (conservative):
- **Entailment**: confidence > 0.8 to mark as "supporting"
- **Contradiction**: confidence > 0.8 to mark as "contradicting"
- **Otherwise**: mark as "neutral" (when in doubt, don't make strong claims)

#### Hybrid Approach

For best results, combine NLI with LLM:

```
Step 1: NLI model scores all claim-document pairs (fast, cheap)
            ↓
Step 2: For pairs with confidence < 0.7 (uncertain), use GPT-4o-mini
            ↓
Step 3: Return final attribution scores
```

This gives you:
- Speed of NLI for clear cases
- Reasoning ability of LLM for ambiguous cases
- Lower cost overall

#### Benefits for Medical RAG

1. **Catches "citation bluffing"**: When LLM cites a document that doesn't actually support the claim
2. **Detects contradictions**: Important when studies disagree
3. **Faster iteration**: Can re-verify without API rate limits
4. **Audit trail**: Deterministic scores for the same input

#### Challenges

- **Context length**: NLI models typically handle ~512 tokens, may need to truncate abstracts
- **Domain shift**: General NLI models may underperform on medical text
- **Nuance**: NLI is binary-ish, may miss degrees of support
- **GPU recommended**: CPU inference is slow for large models

#### Files to Modify

- `app/services/trust/attribution_scorer.py` — Add NLI verification
- `app/services/trust/nli_verifier.py` — New service file

#### Dependencies to Add

```
transformers>=4.30.0
torch>=2.0.0
```

Note: `torch` is large (~2GB). Consider using `onnxruntime` for smaller deployments.

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

## 7. Research: Multi-Agent Debate Architecture

**Priority: Experimental | Effort: High**

A novel approach where multiple agents each advocate for their assigned documents, then an orchestrator evaluates the arguments to synthesize the best answer.

#### Concept

Instead of a single RAG pipeline, create a "debate" between document-advocate agents:

```
Retrieved Documents (e.g., 10 papers)
              ↓
    ┌─────────┼─────────┐
    ↓         ↓         ↓
 Agent A   Agent B   Agent C
 (Doc 1-3) (Doc 4-6) (Doc 7-10)
    ↓         ↓         ↓
 "Doc 2    "Doc 5    "Doc 8 
  shows     shows     shows
  X..."     Y..."     Z..."
    ↓         ↓         ↓
    └─────────┼─────────┘
              ↓
      Orchestrator Agent
    (Evaluates all arguments,
     resolves conflicts,
     picks most logical conclusion)
              ↓
        Final Answer
```

#### Why This Could Work

1. **Adversarial validation:** Weak evidence gets challenged by other agents
2. **Conflict surfacing:** Contradictory findings are explicitly debated
3. **Reasoning transparency:** Each agent must justify why their documents matter
4. **Specialization:** Agents can focus deeply on fewer documents

#### Proposed Architecture

**Document Advocate Agents:**
```python
class DocumentAdvocate:
    """
    An agent that argues for the relevance and findings of assigned documents.
    """
    def __init__(self, documents: list[Document]):
        self.documents = documents
    
    async def make_case(self, query: str) -> AdvocateResponse:
        """
        Analyze assigned documents and argue their relevance to the query.
        
        Returns:
        - key_findings: What these documents contribute
        - evidence_strength: Self-assessed strength (with justification)
        - limitations: Acknowledged weaknesses
        - recommended_conclusion: What answer these docs support
        """
        pass
```

**Orchestrator Agent:**
```python
class DebateOrchestrator:
    """
    Evaluates arguments from all advocates and synthesizes final answer.
    """
    async def evaluate_debate(
        self, 
        query: str,
        advocate_responses: list[AdvocateResponse]
    ) -> FinalVerdict:
        """
        - Identify consensus vs. conflicts
        - Weigh evidence quality (study type, sample size, recency)
        - Resolve contradictions with reasoning
        - Produce final answer with confidence
        """
        pass
```

#### Debate Protocol

1. **Opening arguments:** Each advocate presents key findings from their documents
2. **Cross-examination:** Orchestrator asks follow-up questions to advocates
3. **Rebuttal:** Advocates can challenge other advocates' claims
4. **Closing:** Orchestrator synthesizes final answer

#### Potential Benefits

- Better handling of **conflicting evidence** (common in medicine)
- More **transparent reasoning** about why certain evidence was weighted higher
- **Reduced hallucination** — harder to make up facts when agents must cite specific docs
- **Richer Trust Layer** — debate transcript provides audit trail

#### Challenges

- **Latency:** Multiple agent calls adds significant time
- **Cost:** More LLM calls = higher API costs
- **Complexity:** Orchestrating multi-agent systems is non-trivial
- **Evaluation:** How do we measure if debate improves answer quality?

#### Research Questions

1. How many advocates is optimal? (1 per doc? groups of 3?)
2. Should advocates know about other advocates' documents?
3. How to handle unanimous agreement vs. split decisions?
4. Can smaller models (GPT-4o-mini) be advocates while GPT-4o orchestrates?

#### Related Work

- "Debate" paper from Anthropic on AI safety through debate
- Multi-agent systems in software engineering (AutoGen, CrewAI)
- Mixture-of-Experts architectures

#### Implementation Phases

**Phase 1: Simple debate (2 advocates)**
- Split documents into 2 groups
- Each advocate summarizes their findings
- Orchestrator picks winner or synthesizes

**Phase 2: Full debate protocol**
- Add cross-examination round
- Implement rebuttal mechanism
- Track debate transcript

**Phase 3: Integration with Trust Layer**
- Debate outcomes feed into confidence scoring
- Conflicts identified in debate become gaps
- Advocate agreement → higher confidence

---

## 8. Data Source Expansion

### 8.1 ClinicalTrials.gov Integration
**Priority: High | Effort: Medium**

**TODO:** Add ClinicalTrials.gov data to the knowledge base.

Currently we only ingest PubMed abstracts. Clinical trials data provides:
- **Ongoing studies** — Evidence gaps could be addressed by active trials
- **Study protocols** — Detailed methodology not in abstracts
- **Results data** — Structured outcomes (primary/secondary endpoints)
- **Population details** — Inclusion/exclusion criteria for patient matching

**API Access:**
- ClinicalTrials.gov provides a REST API: `https://clinicaltrials.gov/api/v2/`
- No API key required (rate limited to ~10 requests/second)
- Returns JSON with study metadata, eligibility, interventions, outcomes

**Implementation:**
```python
# Example: Search for ACE inhibitor trials
GET https://clinicaltrials.gov/api/v2/studies?query.cond=heart+failure&query.intr=ACE+inhibitor&pageSize=100
```

**New fields for Document model:**
- `source`: "pubmed" | "clinicaltrials"
- `nct_id`: ClinicalTrials.gov identifier (e.g., "NCT01234567")
- `study_phase`: Phase 1/2/3/4
- `enrollment`: Number of participants
- `study_status`: Recruiting, Completed, etc.

**Trust Layer enhancements:**
- Gap detector can suggest relevant ongoing trials
- Confidence calculator can weight by study phase/enrollment
- Evidence map can distinguish published results vs. trial data

**Files to create/modify:**
- `app/services/clinicaltrials.py` — New API client
- `app/models/document.py` — Add trial-specific fields
- `app/services/trust/gap_detector.py` — Surface relevant trials

---

### 8.2 Other Potential Sources (Future)
- **Cochrane Library** — Systematic reviews and meta-analyses
- **FDA Drug Labels** — Official prescribing information
- **UpToDate/DynaMed** — Clinical decision support (requires licensing)
- **NICE/WHO Guidelines** — Treatment guidelines

---

## Implementation Priority Matrix

| Improvement | Impact | Effort | Priority |
|-------------|--------|--------|----------|
| Citation hallucination detection | High | Low | P0 |
| Hybrid search (BM25 + vector) | High | Medium | P0 |
| **ClinicalTrials.gov integration** | **High** | **Medium** | **P1** |
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
| Multi-agent debate | Experimental | High | Research |

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
