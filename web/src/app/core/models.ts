// ── Auth ─────────────────────────────────────────────────
export interface LoginRequest {
  email: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  role: string;
  company_id: string | null;
}

export interface CurrentUser {
  email: string;
  role: 'superadmin' | 'company_admin' | 'field_user';
  company_id: string | null;
}

// ── Upload ────────────────────────────────────────────────
export interface UploadResponse {
  session_id: string;
  doc_id: string;
  status: string;
  doc_type: string;
  gcs_raw_path: string;
}

// ── Sessions ──────────────────────────────────────────────
export type SessionStatus =
  | 'pending_preview'
  | 'confirmed'
  | 'processing'
  | 'done'
  | 'failed';

export interface SessionStatusResponse {
  session_id: string;
  status: SessionStatus;
  fail_reason: string | null;
  preview_confirmed: boolean;
}

export interface ConfirmResponse {
  session_id: string;
  status: string;
  message: string;
}

// ── Document ──────────────────────────────────────────────
export type DocType = 'pdf' | 'docx' | 'tap' | 'nc' | 'dxf' | 'unknown';

export interface Document {
  doc_id: string;
  filename: string;
  doc_type: DocType;
  has_low_confidence: boolean | null;
  min_confidence: number | null;
  gcs_raw_path: string;
}

// ── Chunk ─────────────────────────────────────────────────
export interface Chunk {
  chunk_id: string;
  doc_id: string;
  company_id: string;
  doc_type: string;
  rule_version: string;
  embed_text: string;
  created_at: string | null;

  // spec group
  product_name?: string;
  product_id?: string;
  material?: string;
  dimensions?: string;
  specs?: string;
  face?: string;

  // knowledge group
  situation?: string;
  action?: string;
  reason?: string;
  applies_to?: string;

  // common
  case_id?: string;

  // attachments
  code_gcs_path?: string;
  drawing_gcs_path?: string;
}

export interface SessionChunksResponse {
  session_id: string;
  status: SessionStatus;
  documents: Document[];
  chunks: Chunk[];
  chunk_count: number;
}

// ── Upload Queue ──────────────────────────────────────────
export type UploadJobStatus = 'uploading' | 'done' | 'error';

export interface UploadJob {
  id: string;
  name: string;
  size: number;
  pct: number;
  status: UploadJobStatus;
  sessionId?: string;
  errorMsg?: string;
}
