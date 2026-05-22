import { Injectable, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { CompanyRow } from './admin.service';

@Injectable({ providedIn: 'root' })
export class CompanyContextService {
  private readonly http = inject(HttpClient);

  readonly companies        = signal<CompanyRow[]>([]);
  readonly activeCompanyId  = signal<string | null>(null);
  readonly activeCompany    = signal<CompanyRow | null>(null);

  async loadCompanies(): Promise<void> {
    try {
      const list = await firstValueFrom(
        this.http.get<CompanyRow[]>(`${environment.apiUrl}/companies`)
      );
      this.companies.set(list.filter(c => c.is_active));
    } catch {
      this.companies.set([]);
    }
  }

  select(companyId: string | null): void {
    this.activeCompanyId.set(companyId);
    this.activeCompany.set(
      companyId ? (this.companies().find(c => c.company_id === companyId) ?? null) : null
    );
  }
}
