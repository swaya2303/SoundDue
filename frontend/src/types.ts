export interface Case {
  id: number;
  name: string;
  description: string;
  status: string;
  created_at: string;
  file_count: number;
}

export interface UploadedFile {
  file_id: number;
  case_id: number;
  original_name: string;
  file_kind: string;
  row_count: number;
  detected_columns: string[];
  validation: ValidationReport;
}

export interface ValidationReport {
  issue_count: number;
  has_errors: boolean;
  issues: ValidationIssue[];
}

export interface ValidationIssue {
  row: number | null;
  column: string | null;
  code: string;
  message: string;
  value: string | null;
}

export interface MappingSuggestion {
  source_column: string;
  best_canonical: string | null;
  confidence: string;
  score: number;
  method: string;
  alternatives: { canonical_field: string; score: number }[];
}

export interface MappingState {
  file_id: number;
  file_kind: string;
  required_fields: string[];
  all_confirmed: boolean;
  confirmed_mappings: { source_column: string; canonical_field: string }[];
  suggestions: MappingSuggestion[];
}

export interface Finding {
  id: number;
  finding_type: string;
  rule_id: string | null;
  rule_version: string | null;
  severity: 'info' | 'warning' | 'error';
  summary: string;
  status: 'open' | 'resolved' | 'accepted' | 'rejected';
  created_at: string;
}

export interface RuleTrace {
  rule_id: string;
  rule_version: string;
  matched_conditions: string[];
  supporting_record_ids: number[];
  missing_information: string | null;
  conflicting_information: string | null;
  evaluated_at: string;
}

export interface Evidence {
  id: number;
  source_record_id: number | null;
  source_file_id: number | null;
  source_row: number | null;
  field_values: Record<string, unknown>;
  note: string | null;
}

export interface ReviewDecision {
  id: number;
  decision: string;
  actor: string;
  note: string;
  corrected_values: Record<string, unknown>;
  decided_at: string;
}

export interface FindingDetail extends Finding {
  case_id: number;
  uncertainty: string;
  next_step: string;
  rule_trace: RuleTrace | null;
  evidence: Evidence[];
  review_decisions: ReviewDecision[];
}


export interface ReviewEvent {
  id: number;
  finding_id: number;
  action: string;
  actor: string;
  timestamp: string;
  note: string | null;
}

export interface MatchCandidate {
  id: number;
  left_record_id: number;
  right_record_id: number;
  score: number;
  field_scores: Record<string, number>;
  reasons: string[];
  status: string;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string | null;
}
