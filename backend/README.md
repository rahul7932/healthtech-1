# Medical AI Trust Layer — Backend

A RAG (Retrieval-Augmented Generation) system for medical questions with a **post-hoc verification layer** that explains *why* you should trust the answer.

## What Makes This Different

Most medical AI systems:
```
Question → Retrieve docs → Generate answer → Done
```

This system:
```
Question → Retrieve docs → Generate answer → VERIFY → Trust Report
```

The **Trust Layer** analyzes the answer and tells you:
- What claims were made
- Which evidence supports each claim
- How confident you should be
- What evidence is missing

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              USER QUERY                                  │
│                "Do ACE inhibitors reduce mortality?"                     │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         RETRIEVAL LAYER                                  │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐             │
│  │  Embeddings │───▶│  Retriever  │───▶│ Top 10 Documents│             │
│  │  (OpenAI)   │    │  (pgvector) │    │   with scores   │             │
│  └─────────────┘    └─────────────┘    └─────────────────┘             │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        GENERATION LAYER                                  │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                      RAG Generator (GPT-4o)                      │   │
│  │  "ACE inhibitors reduce mortality in heart failure [PMID:123]"  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    TRUST LAYER (The Core Innovation)                     │
│                                                                          │
│  ┌─────────────────┐                                                    │
│  │ Claim Extractor │  "ACE inhibitors reduce mortality"                 │
│  │                 │  "This applies to heart failure patients"          │
│  └────────┬────────┘                                                    │
│           │                                                              │
│           ▼                                                              │
│  ┌─────────────────────┐                                                │
│  │ Attribution Scorer  │  Doc A: SUPPORTS                               │
│  │                     │  Doc B: CONTRADICTS                            │
│  │                     │  Doc C: NEUTRAL                                │
│  └────────┬────────────┘                                                │
│           │                                                              │
│           ▼                                                              │
│  ┌──────────────────────┐                                               │
│  │ Confidence Calculator│  confidence = 0.73                            │
│  │                      │  (based on evidence, NOT model logprobs)      │
│  └────────┬─────────────┘                                               │
│           │                                                              │
│           ▼                                                              │
│  ┌─────────────────┐                                                    │
│  │  Gap Detector   │  "Pediatric population not addressed"              │
│  │                 │  "Long-term outcomes unknown"                      │
│  └─────────────────┘                                                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                           TRUST REPORT                                   │
│  {                                                                       │
│    "answer": "ACE inhibitors reduce mortality...",                      │
│    "claims": [...],                                                      │
│    "overall_confidence": 0.73,                                          │
│    "evidence_summary": {"supporting": 4, "contradicting": 1},           │
│    "global_gaps": ["Long-term outcomes beyond 5 years unknown"]         │
│  }                                                                       │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Services

### Data Layer

| Service | File | Purpose |
|---------|------|---------|
| **PubMed Client** | `services/pubmed.py` | Fetches medical abstracts from PubMed API |
| **Embedding Service** | `services/embeddings.py` | Converts text → 1536-dim vectors (OpenAI) |
| **Retriever** | `services/retriever.py` | Vector similarity search via pgvector |

### Generation Layer

| Service | File | Purpose |
|---------|------|---------|
| **RAG Generator** | `services/generator.py` | Generates answers with `[PMID:xxx]` citations |

### Trust Layer

| Service | File | Purpose |
|---------|------|---------|
| **Claim Extractor** | `services/trust/claim_extractor.py` | Breaks answer into atomic, verifiable claims |
| **Attribution Scorer** | `services/trust/attribution_scorer.py` | Classifies docs as supports/contradicts/neutral |
| **Confidence Calculator** | `services/trust/confidence_calculator.py` | Computes evidence-based confidence (not logprobs) |
| **Gap Detector** | `services/trust/gap_detector.py` | Identifies missing evidence |

---

## Data Flow

### 1. Ingest Phase (Run Once)

```python
POST /api/documents/ingest {"search_term": "ACE inhibitors heart failure"}

# Flow:
PubMed API → fetch 100 abstracts
    │
    ▼
Database → save documents
    │
    ▼
Embedding Service → generate vectors for all docs
    │
    ▼
pgvector → documents now searchable
```

### 2. Query Phase (Every User Question)

```python
POST /api/query {"question": "Do ACE inhibitors reduce mortality?"}

# Flow:
Embedding Service → embed the question (1 API call)
    │
    ▼
Retriever → find top 10 similar documents (pgvector)
    │
    ▼
RAG Generator → generate answer with citations (GPT-4o)
    │
    ▼
Claim Extractor → break into claims (GPT-4o-mini)
    │
    ▼
Attribution Scorer → score each claim (GPT-4o-mini)
    │
    ▼
Confidence Calculator → compute confidence (no API call)
    │
    ▼
Gap Detector → find missing evidence (GPT-4o-mini)
    │
    ▼
Trust Report → final output for dashboard
```

---

## Key Schemas

### TrustReport (Main Output)

```python
{
  "query": "Do ACE inhibitors reduce mortality?",
  "answer": "ACE inhibitors reduce mortality in heart failure [PMID:12345]...",
  "claims": [
    {
      "id": "claim_1",
      "text": "ACE inhibitors reduce mortality",
      "supporting_docs": [{"pmid": "12345", "title": "..."}],
      "contradicting_docs": [],
      "confidence": 0.81,
      "missing_evidence": ["Pediatric population not addressed"]
    }
  ],
  "overall_confidence": 0.73,
  "evidence_summary": {
    "total_sources": 5,
    "supporting": 4,
    "contradicting": 0,
    "neutral": 1
  },
  "global_gaps": ["Long-term outcomes beyond 5 years unknown"]
}
```

---

## Project Structure

```
backend/
├── app/
│   ├── main.py              # FastAPI app, lifespan, health check
│   ├── config.py            # Environment settings (Supabase, OpenAI)
│   ├── database.py          # SQLAlchemy async setup
│   │
│   ├── models/
│   │   ├── document.py      # SQLAlchemy model (pgvector column)
│   │   └── schemas.py       # Pydantic schemas (TrustReport, Claim, etc.)
│   │
│   ├── services/
│   │   ├── pubmed.py        # PubMed E-utilities client
│   │   ├── embeddings.py    # OpenAI embedding service
│   │   ├── retriever.py     # pgvector similarity search
│   │   ├── generator.py     # RAG answer generation
│   │   │
│   │   └── trust/           # THE CORE INNOVATION
│   │       ├── claim_extractor.py
│   │       ├── attribution_scorer.py
│   │       ├── confidence_calculator.py
│   │       └── gap_detector.py
│   │
│   └── api/
│       └── routes.py        # FastAPI endpoints (coming soon)
│
├── tests/
│   └── test_pubmed.py       # Sanity check tests
│
├── requirements.txt
├── pytest.ini
└── env.example
```

---

## Setup

### 1. Create Supabase Project

1. Go to [supabase.com](https://supabase.com) and create a project
2. Enable pgvector: Database → Extensions → Search "vector" → Enable
3. Get connection string: Project Settings → Database → Connection string

### 2. Configure Environment

```bash
cd backend
cp env.example .env
# Edit .env with your Supabase URL and OpenAI API key
```

### 3. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. Run Server

```bash
uvicorn app.main:app --reload
```

### 5. Run Tests

```bash
pytest tests/test_pubmed.py -v
```

---

## Why This Architecture?

### Separation of Concerns

Each service does ONE thing:
- PubMed client: fetch data
- Embeddings: convert to vectors
- Retriever: find similar docs
- Generator: produce answer
- Trust Layer: verify answer

### Evidence-Based Confidence

We don't use model logprobs (how certain the model is about its words).
We use **evidence confidence** (how well the evidence supports the claim).

```python
confidence = evidence_agreement × log(num_sources + 1) × quality_weight
```

### Explicit Uncertainty

The Gap Detector identifies what we DON'T know — crucial for responsible medical AI.

---

## Tech Stack

- **FastAPI** — Async Python web framework
- **PostgreSQL + pgvector** — Vector similarity search
- **Supabase** — Hosted PostgreSQL
- **OpenAI** — Embeddings (text-embedding-3-small) and LLM (GPT-4o)
- **SQLAlchemy** — Async ORM
- **Pydantic** — Data validation
