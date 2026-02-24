// ─────────────────────────────────────────────────────────────────────────────
// src/types/api.ts — TypeScript mirrors of all backend Pydantic response schemas
// ─────────────────────────────────────────────────────────────────────────────

// ── Auth ──────────────────────────────────────────────────────────────────────
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export type RoleEnum = "ADMIN" | "EDITOR" | "REVIEWER" | "VIEWER";

export interface UserOut {
  id: string;
  username: string;
  email: string | null;
  role: RoleEnum;
  is_active: boolean;
  created_at: string;
}

// ── Documents ─────────────────────────────────────────────────────────────────
export type DocumentStatus =
  | "pending"
  | "extracting"
  | "extracted"
  | "mapping"
  | "mapped"
  | "failed";

export interface DocumentOut {
  id: string;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number;
  file_hash: string;
  page_count: number | null;
  status: DocumentStatus;
  error_message: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
}

export interface DocumentListResponse {
  items: DocumentOut[];
  total: number;
  page: number;
  page_size: number;
}

export type SectionType =
  | "PREAMBLE"
  | "HEADING"
  | "CLAUSE"
  | "DEFINITION"
  | "TABLE"
  | "LIST"
  | "APPENDIX"
  | "UNKNOWN";

export interface SectionOut {
  id: string;
  document_id: string;
  parent_id: string | null;
  sequence_no: number;
  depth: number;
  section_type: SectionType;
  heading: string | null;
  original_text: string;
  content_hash: string;
  page_start: number | null;
  page_end: number | null;
  char_count: number;
}

export interface DocumentGraphNode {
  section: SectionOut;
  children: DocumentGraphNode[];
}

// ── Rulesets ──────────────────────────────────────────────────────────────────
export interface RuleDefinition {
  id: string;
  priority: number;
  name: string;
  section_types: SectionType[];
  instruction: string;
}

export interface RulesetOut {
  id: string;
  name: string;
  description: string;
  jurisdiction: string | null;
  version: string;
  schema_version: string;
  content_hash: string;
  is_active: boolean;
  rules: RuleDefinition[];
  created_by: string;
  created_at: string;
}

export interface RuleConflictOut {
  id: string;
  ruleset_id: string;
  rule_a_id: string;
  rule_b_id: string;
  description: string;
  is_resolved: boolean;
}

// ── Jobs ──────────────────────────────────────────────────────────────────────
export type JobStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type RiskSeverity = "critical" | "high" | "medium" | "low" | "info";

export interface RiskFindingOut {
  id: string;
  severity: RiskSeverity;
  category: string;
  description: string;
  score: number;
  detail_json: Record<string, unknown> | null;
  created_at: string;
}

export type RewriteStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped";

export interface SectionRewriteOut {
  id: string;
  job_id: string;
  section_id: string;
  status: RewriteStatus;
  prompt_hash: string;
  rewritten_text: string | null;
  model_name: string;
  tokens_prompt: number;
  tokens_completion: number;
  duration_ms: number;
  attempt_number: number;
  risk_findings: RiskFindingOut[];
  created_at: string;
  updated_at: string;
}

export interface RewriteJobOut {
  id: string;
  document_id: string;
  ruleset_id: string;
  status: JobStatus;
  created_by: string;
  error_message: string | null;
  total_sections: number;
  completed_sections: number;
  created_at: string;
  updated_at: string;
}

export interface JobProgressUpdate {
  job_id: string;
  section_id: string;
  rewrite_id: string;
  status: RewriteStatus;
  token?: string;               // streaming token (partial text)
  completed_sections: number;
  total_sections: number;
  risk_findings: RiskFindingOut[];
  done: boolean;
}

// ── Reviews ───────────────────────────────────────────────────────────────────
export type ReviewStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "edited"
  | "rerun_requested";

export type ReviewDecision =
  | "approve"
  | "reject"
  | "edit"
  | "request_rerun";

export interface DiffHunk {
  type: "equal" | "insert" | "delete" | "replace";
  original_words: string[];
  rewritten_words: string[];
  index: number;
}

export interface ReviewCommentOut {
  id: string;
  review_id: string;
  parent_comment_id: string | null;
  author_id: string;
  hunk_index: number | null;
  body: string;
  is_resolved: boolean;
  created_at: string;
}

export interface ReviewOut {
  id: string;
  rewrite_id: string;
  reviewer_id: string;
  status: ReviewStatus;
  edited_text: string | null;
  original_text: string | null;
  rewritten_text: string | null;
  diff_hunks: DiffHunk[];
  risk_override_reason: string | null;
  risk_findings: RiskFindingOut[];
  comments: ReviewCommentOut[];
  reviewed_at: string | null;
  created_at: string;
}

// ── Audit ─────────────────────────────────────────────────────────────────────
export interface AuditEventOut {
  id: string;
  event_type: string;
  actor_id: string | null;
  actor_username: string | null;
  entity_type: string | null;
  entity_id: string | null;
  correlation_id: string | null;
  payload_json: Record<string, unknown> | null;
  event_hash: string;
  prev_hash: string | null;
  created_at: string;
}

export interface AuditListResponse {
  items: AuditEventOut[];
  total: number;
  page: number;
  page_size: number;
}

export interface ChainVerificationResult {
  valid: boolean;
  total_events: number;
  first_broken_at: string | null;
  message: string;
}

// ── Error ─────────────────────────────────────────────────────────────────────
export interface ApiErrorPayload {
  error: {
    code: string;
    message: string;
    detail?: unknown;
  };
}
