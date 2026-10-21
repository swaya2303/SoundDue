export const API_BASE = 'http://localhost:8000';

import type { Case, UploadedFile, MappingState, Finding, MatchCandidate } from './types';

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Cases ──────────────────────────────────────────────────────────────────

export const listCases = () => apiFetch<Case[]>(`${API_BASE}/cases`);

export async function createCase(name: string, description: string): Promise<Case> {
  const form = new FormData();
  form.append('name', name);
  form.append('description', description);
  return apiFetch<Case>(`${API_BASE}/cases`, { method: 'POST', body: form });
}

// ── File upload ────────────────────────────────────────────────────────────

export async function uploadFile(
  caseId: number,
  file: File,
  fileKind: string,
): Promise<UploadedFile> {
  const form = new FormData();
  form.append('file', file);
  form.append('file_kind', fileKind);
  return apiFetch<UploadedFile>(`${API_BASE}/cases/${caseId}/files`, {
    method: 'POST',
    body: form,
  });
}

// ── File preview ───────────────────────────────────────────────────────────

export interface PreviewData {
  file_id: number;
  original_name: string;
  file_kind: string;
  row_count: number;
  detected_columns: string[];
  preview_rows: Record<string, string>[];
  validation: import('./types').ValidationReport;
}

export const getFilePreview = (fileId: number) =>
  apiFetch<PreviewData>(`${API_BASE}/files/${fileId}/preview`);

// ── Mapping ────────────────────────────────────────────────────────────────

export const getMappingSuggestions = (fileId: number) =>
  apiFetch<MappingState>(`${API_BASE}/files/${fileId}/mapping/suggestions`);

export async function confirmMapping(
  fileId: number,
  mappings: { source_column: string; canonical_field: string }[],
) {
  return apiFetch<{
    all_confirmed: boolean;
    confirmed_mappings: { source_column: string; canonical_field: string }[];
  }>(`${API_BASE}/files/${fileId}/mapping`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mappings }),
  });
}

// ── Analyze ────────────────────────────────────────────────────────────────

export interface AnalyzeResult {
  finding_count: number;
  findings_by_type: Record<string, number>;
  finding_ids: number[];
  record_count: number;
  link_count: number;
}

export const analyzeCase = (caseId: number) =>
  apiFetch<AnalyzeResult>(`${API_BASE}/cases/${caseId}/analyze`, { method: 'POST' });

// ── Findings ───────────────────────────────────────────────────────────────

export const getCaseFindings = (caseId: number) =>
  apiFetch<Finding[]>(`${API_BASE}/cases/${caseId}/findings`);

export const getFinding = (id: number) =>
  apiFetch<import('./types').FindingDetail>(`${API_BASE}/findings/${id}`);

// ── Candidates ─────────────────────────────────────────────────────────────

export const getCaseCandidates = (caseId: number) =>
  apiFetch<MatchCandidate[]>(`${API_BASE}/cases/${caseId}/candidates`);

// ── Review / Rerun ─────────────────────────────────────────────────────────

export interface ReviewBody {
  decision: 'accept' | 'reject' | 'correct';
  note?: string;
  corrected_values?: Record<string, unknown>;
}

export interface ReviewResult {
  finding_id: number;
  decision_id: number;
  new_status: string;
  decision: string;
  new_record_versions: number[];
}

export const reviewFinding = (id: number, body: ReviewBody) =>
  apiFetch<ReviewResult>(`${API_BASE}/findings/${id}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

export interface RerunDiffEntry {
  finding_id: number;
  finding_type: string;
  severity: string;
  summary: string;
  status?: string;
  fingerprint: string;
  prev_finding_id?: number;
  prev_summary?: string;
  note?: string;
}

export interface RerunResult {
  case_id: number;
  status: string;
  summary: { new: number; unchanged: number; changed: number; resolved: number; rejected: number };
  diff: { new: RerunDiffEntry[]; unchanged: RerunDiffEntry[]; changed: RerunDiffEntry[]; resolved: RerunDiffEntry[]; rejected: RerunDiffEntry[] };
  analysis: { finding_count: number; findings_by_type: Record<string, number>; record_count: number };
}

export const rerunCase = (caseId: number) =>
  apiFetch<RerunResult>(`${API_BASE}/cases/${caseId}/rerun`, { method: 'POST' });

export const reviewCandidate = (caseId: number, candidateId: number, action: 'accept' | 'reject') =>
  apiFetch<{ id: number; status: string }>(`${API_BASE}/cases/${caseId}/candidates/${candidateId}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action }),
  });

// ── Legacy (kept for existing components that may import them) ─────────────

export async function fetchFindings(): Promise<Finding[]> {
  return apiFetch<Finding[]>(`${API_BASE}/findings`);
}

export async function runMatching(): Promise<unknown> {
  return apiFetch<unknown>(`${API_BASE}/run-matching`, { method: 'POST' });
}
