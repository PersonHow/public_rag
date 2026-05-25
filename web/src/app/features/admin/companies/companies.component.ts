import { Component, inject, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminService, CompanyRow, CompanyCreate } from '../../../core/services/admin.service';
import { ToastService } from '../../../core/services/toast.service';
import { PageHeadComponent } from '../../../shared/components/page-head/page-head.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import { EmptyStateComponent } from '../../../shared/components/empty-state/empty-state.component';
import { TruncateIdPipe } from '../../../shared/pipes/truncate-id.pipe';
import { ButtonComponent } from '../../../shared/components/button/button.component';

@Component({
  selector: 'app-admin-companies',
  standalone: true,
  imports: [FormsModule, PageHeadComponent, StatusBadgeComponent, EmptyStateComponent, TruncateIdPipe, ButtonComponent],
  templateUrl: './companies.component.html',
  styleUrl: './companies.component.scss',
})
export class AdminCompaniesComponent implements OnInit {
  private readonly admin = inject(AdminService);
  private readonly toast = inject(ToastService);

  readonly companies  = signal<CompanyRow[]>([]);
  readonly loading    = signal(false);
  readonly apiError   = signal<string | null>(null);
  readonly showForm   = signal(false);
  readonly submitting = signal(false);

  form: CompanyCreate = { name: '', industry: null };

  ngOnInit(): void { this.load(); }

  async load(): Promise<void> {
    this.loading.set(true);
    this.apiError.set(null);
    try {
      this.companies.set(await this.admin.getCompanies());
    } catch (e: any) {
      this.apiError.set(e?.error?.detail ?? '無法載入租戶列表');
      this.companies.set([]);
    } finally {
      this.loading.set(false);
    }
  }

  openForm(): void {
    this.form = { name: '', industry: null };
    this.showForm.set(true);
  }

  cancelForm(): void { this.showForm.set(false); }

  async submit(): Promise<void> {
    if (!this.form.name.trim()) return;
    this.submitting.set(true);
    try {
      await this.admin.createCompany({
        name: this.form.name.trim(),
        industry: this.form.industry?.trim() || null,
      });
      this.toast.success('租戶已建立');
      this.showForm.set(false);
      await this.load();
    } catch (e: any) {
      this.toast.error(e?.error?.detail ?? '建立失敗');
    } finally {
      this.submitting.set(false);
    }
  }

  async deactivate(company: CompanyRow): Promise<void> {
    if (!confirm(`確認停用租戶「${company.name}」？此操作會影響旗下所有用戶。`)) return;
    try {
      await this.admin.deactivateCompany(company.company_id);
      this.toast.success('租戶已停用');
      await this.load();
    } catch (e: any) {
      this.toast.error(e?.error?.detail ?? '停用失敗');
    }
  }
}
