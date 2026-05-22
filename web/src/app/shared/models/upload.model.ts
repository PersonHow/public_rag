// ── Upload ────────────────────────────────────────────────
export interface UploadResponse {
  session_id: string;
  doc_id: string;
  status: string;
  doc_type: string;
  gcs_raw_path: string;
}

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
