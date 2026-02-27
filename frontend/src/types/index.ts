/**
 * TypeScript types matching the backend Pydantic schemas.
 * These mirror backend/app/models/schemas.py exactly.
 */

// Evidence reference - a document cited in a claim
export interface EvidenceReference {
  pmid: string;
  title: string;
  relevance_score: number;
}

// A single atomic claim extracted from the answer
export interface Claim {
  id: string;
  text: string;
  span_start: number;
  span_end: number;
  supporting_docs: EvidenceReference[];
  contradicting_docs: EvidenceReference[];
  neutral_docs: EvidenceReference[];
  confidence: number;
  missing_evidence: string[];
}

// Summary of all evidence used
export interface EvidenceSummary {
  total_sources: number;
  supporting: number;
  contradicting: number;
  neutral: number;
}

// The main trust report - returned from /api/query
export interface TrustReport {
  query: string;
  answer: string;
  claims: Claim[];
  overall_confidence: number;
  evidence_summary: EvidenceSummary;
  global_gaps: string[];
}

// Request body for /api/query
export interface QueryRequest {
  question: string;
  top_k?: number;
}

// Document response from the backend
export interface Document {
  id: number;
  pmid: string;
  title: string;
  abstract: string;
  authors: string[];
  publication_date: string | null;
  journal: string | null;
  has_embedding: boolean;
  created_at: string;
}

// Ingest request for /api/documents/ingest
export interface IngestRequest {
  query: string;
  max_results?: number;
}

// Ingest response
export interface IngestResponse {
  message: string;
  documents_added: number;
  pmids: string[];
}

// Document count response
export interface DocumentCountResponse {
  total: number;
  with_embeddings: number;
  without_embeddings: number;
}
