import { Component, inject, signal, OnInit } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { AdminService, CompanyRow, CompanyCreate } from '../../../core/services/admin.service';
import { ToastService } from '../../../core/services/toast.service';
import { PageHeadComponent } from '../../../shared/components/page-head/page-head.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import { EmptyStateComponent } from '../../../shared/components/empty-state/empty-state.component';
import { TruncateIdPipe } from '../../../shared/pipes/truncate-id.pipe';
import { ButtonComponent } from '../../../shared/components/button/button.component';

/** 右側面板：檢視選取的租戶、編輯選取的租戶、新增租戶 */
type PanelMode = 'view' | 'edit' | 'create';

@Component({
  selector: 'app-admin-companies',
  standalone: true,
  imports: [DatePipe, FormsModule, PageHeadComponent, StatusBadgeComponent, EmptyStateComponent, TruncateIdPipe, ButtonComponent],
  templateUrl: './companies.component.html',
  styleUrl: './companies.component.scss',
})
export class AdminCompaniesComponent implements OnInit {
  private readonly admin = inject(AdminService);
  private readonly toast = inject(ToastService);

  readonly companies  = signal<CompanyRow[]>([]);
  readonly loading    = signal(false);
  readonly apiError   = signal<string | null>(null);
  readonly submitting = signal(false);
  readonly selected   = signal<CompanyRow | null>(null);
  readonly panelMode  = signal<PanelMode | null>(null);

  form: CompanyCreate = this.emptyForm();

  ngOnInit(): void { this.load(); }

  async load(): Promise<void> {
    this.loading.set(true);
    this.apiError.set(null);
    try {
      const list = await this.admin.getCompanies();
      this.companies.set(list);
      // 重新載入後讓面板顯示最新資料
      const selectedId = this.selected()?.company_id;
      if (selectedId) this.selected.set(list.find(c => c.company_id === selectedId) ?? null);
    } catch (e: any) {
      this.apiError.set(e?.error?.detail ?? '無法載入租戶列表');
      this.companies.set([]);
    } finally {
      this.loading.set(false);
    }
  }

  select(company: CompanyRow): void {
    this.selected.set(company);
    this.panelMode.set('view');
  }

  openCreate(): void {
    this.form = this.emptyForm();
    this.selected.set(null);
    this.panelMode.set('create');
  }

  openEdit(company: CompanyRow): void {
    this.form = {
      name: company.name,
      industry: company.industry,
      contact_name: company.contact_name,
      contact_phone: company.contact_phone,
      contact_email: company.contact_email,
    };
    this.panelMode.set('edit');
  }

  /** 編輯時取消回到檢視；新增時取消直接關閉 */
  cancelForm(): void {
    this.panelMode.set(this.selected() ? 'view' : null);
  }

  closePanel(): void {
    this.selected.set(null);
    this.panelMode.set(null);
  }

  async submit(): Promise<void> {
    if (!this.form.name.trim()) return;
    const data: CompanyCreate = {
      name: this.form.name.trim(),
      industry: this.form.industry?.trim() || null,
      contact_name: this.form.contact_name?.trim() || null,
      contact_phone: this.form.contact_phone?.trim() || null,
      contact_email: this.form.contact_email?.trim() || null,
    };
    const editing = this.panelMode() === 'edit' ? this.selected() : null;
    this.submitting.set(true);
    try {
      if (editing) {
        await this.admin.updateCompany(editing.company_id, data);
        this.toast.success('租戶已更新');
      } else {
        this.selected.set(await this.admin.createCompany(data));
        this.toast.success('租戶已建立');
      }
      this.panelMode.set('view');
      await this.load();
    } catch (e: any) {
      this.toast.error(e?.error?.detail ?? (editing ? '更新失敗' : '建立失敗'));
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

  private emptyForm(): CompanyCreate {
    return { name: '', industry: null, contact_name: null, contact_phone: null, contact_email: null };
  }
}
