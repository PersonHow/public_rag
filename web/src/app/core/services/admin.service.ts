import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';

export interface UserRow {
  user_id: string;
  email: string;
  role: string;
  is_active: boolean;
  company_id: string | null;
  company_name: string | null;
}

export interface UserCreate {
  email: string;
  password: string;
  role: 'superadmin' | 'company_admin' | 'field_user';
  company_id?: string | null;
}

export interface CompanyRow {
  company_id: string;
  name: string;
  industry: string | null;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  is_active: boolean;
  created_at: string;
  /** 只有 GET /companies 列表會帶 */
  session_count: number | null;
}

export interface CompanyCreate {
  name: string;
  industry?: string | null;
  contact_name?: string | null;
  contact_phone?: string | null;
  contact_email?: string | null;
}

@Injectable({ providedIn: 'root' })
export class AdminService {
  private readonly http = inject(HttpClient);
  private readonly base = environment.apiUrl;

  // ── Users ─────────────────────────────────────────────────
  getUsers(): Promise<UserRow[]> {
    return firstValueFrom(this.http.get<UserRow[]>(`${this.base}/users`));
  }

  createUser(data: UserCreate): Promise<UserRow> {
    return firstValueFrom(this.http.post<UserRow>(`${this.base}/users`, data));
  }

  deactivateUser(userId: string): Promise<UserRow> {
    return firstValueFrom(
      this.http.patch<UserRow>(`${this.base}/users/${userId}/deactivate`, {})
    );
  }

  // ── Companies ─────────────────────────────────────────────
  getCompanies(): Promise<CompanyRow[]> {
    return firstValueFrom(this.http.get<CompanyRow[]>(`${this.base}/companies`));
  }

  createCompany(data: CompanyCreate): Promise<CompanyRow> {
    return firstValueFrom(this.http.post<CompanyRow>(`${this.base}/companies`, data));
  }

  updateCompany(companyId: string, data: CompanyCreate): Promise<CompanyRow> {
    return firstValueFrom(this.http.put<CompanyRow>(`${this.base}/companies/${companyId}`, data));
  }

  deactivateCompany(companyId: string): Promise<CompanyRow> {
    return firstValueFrom(
      this.http.patch<CompanyRow>(`${this.base}/companies/${companyId}/deactivate`, {})
    );
  }
}
