// ── Document ──────────────────────────────────────────────
import { SessionStatus } from './session.model';

export type DocType = 'pdf' | 'docx' | 'tap' | 'nc' | 'dxf' | 'unknown';

export interface Document {
  doc_id: string;
  filename: string;
  doc_type: DocType;
  has_low_confidence: boolean | null;
  min_confidence: number | null;
  gcs_raw_path: string;
}

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

// ── Phase 5：整體預覽 ──────────────────────────────────────
export interface FullTextChunk {
  chunk_id: string;
  chunk_index: number | null;
  product_name?: string;
  product_id?: string;
  situation?: string;
  action?: string;
  reason?: string;
  applies_to?: string;
  material?: string;
  dimensions?: string;
  face?: string;
  case_id?: string;
  embed_text: string;
}

export interface FullTextResponse {
  doc_id: string;
  filename: string;
  chunk_count: number;
  chunks: FullTextChunk[];
}
