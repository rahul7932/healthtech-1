/**
 * API client for communicating with the backend.
 * All endpoints are proxied through Vite dev server to avoid CORS issues.
 */

import type {
  TrustReport,
  QueryRequest,
  Document,
  IngestRequest,
  IngestResponse,
  DocumentCountResponse,
} from '../types';

const API_BASE = '/api';

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new ApiError(response.status, error.detail || 'Request failed');
  }
  return response.json();
}

/**
 * Submit a medical question and get a trust report.
 * This is the main endpoint that runs the full RAG + trust pipeline.
 */
export async function submitQuery(request: QueryRequest): Promise<TrustReport> {
  const response = await fetch(`${API_BASE}/query`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<TrustReport>(response);
}

/**
 * Ingest documents from PubMed into the database.
 */
export async function ingestDocuments(request: IngestRequest): Promise<IngestResponse> {
  const response = await fetch(`${API_BASE}/documents/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  return handleResponse<IngestResponse>(response);
}

/**
 * Get a single document by PMID.
 */
export async function getDocument(pmid: string): Promise<Document> {
  const response = await fetch(`${API_BASE}/documents/${pmid}`);
  return handleResponse<Document>(response);
}

/**
 * Get document counts (total, with embeddings, without embeddings).
 */
export async function getDocumentCounts(): Promise<DocumentCountResponse> {
  const response = await fetch(`${API_BASE}/documents/count`);
  return handleResponse<DocumentCountResponse>(response);
}

/**
 * Health check endpoint.
 */
export async function healthCheck(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE.replace('/api', '')}/health`);
  return handleResponse<{ status: string }>(response);
}

export { ApiError };
