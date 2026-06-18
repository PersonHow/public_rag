// ── Auth ──────────────────────────────────────────────────
export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  role: string;
  company_id: string | null;
  company_name: string | null;
}

export interface CurrentUser {
  email: string;
  role: 'superadmin' | 'company_admin' | 'field_user';
  company_id: string | null;
  company_name: string | null;
}
