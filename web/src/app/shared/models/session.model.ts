// ── Session ───────────────────────────────────────────────
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
