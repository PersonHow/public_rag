// ── Auth ──────────────────────────────────────────────────
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
