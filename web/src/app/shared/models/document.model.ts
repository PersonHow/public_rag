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
  chunk_index: number | null;
  doc_type: string;

  // 識別欄位
  product_name: string | null;
  product_id: string | null;
  case_id: string | null;
  face: string | null;

  // 結構欄位（v2 新增，若原本沒有需補上）
  material: string | null;
  dimensions: string | null;
  situation: string | null;
  action: string | null;
  reason: string | null;
  applies_to: string | null;

  // 向量搜尋用
  embed_text: string;

  // 文件品質
  has_low_confidence?: boolean;

  created_at?: string;
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
