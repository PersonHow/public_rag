import { Component, inject, signal, computed, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminService, UserRow, UserCreate } from '../../../core/services/admin.service';
import { AuthService } from '../../../core/services/auth.service';
import { ToastService } from '../../../core/services/toast.service';
import { PageHeadComponent } from '../../../shared/components/page-head/page-head.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import { EmptyStateComponent } from '../../../shared/components/empty-state/empty-state.component';
import { TruncateIdPipe } from '../../../shared/pipes/truncate-id.pipe';

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [FormsModule, PageHeadComponent, StatusBadgeComponent, EmptyStateComponent, TruncateIdPipe],
  templateUrl: './users.component.html',
  styleUrl: './users.component.scss',
})
export class AdminUsersComponent implements OnInit {
  private readonly admin  = inject(AdminService);
  private readonly auth   = inject(AuthService);
  private readonly toast  = inject(ToastService);

  readonly users      = signal<UserRow[]>([]);
  readonly loading    = signal(false);
  readonly apiError   = signal<string | null>(null);
  readonly showForm   = signal(false);
  readonly submitting = signal(false);

  readonly isSuperAdmin = this.auth.isSuperAdmin;
  readonly myCompanyId  = computed(() => this.auth.currentUser()?.company_id ?? null);

  form: UserCreate = { email: '', password: '', role: 'field_user', company_id: null };

  readonly availableRoles = computed<Array<'superadmin' | 'company_admin' | 'field_user'>>(() =>
    this.isSuperAdmin()
      ? ['superadmin', 'company_admin', 'field_user']
      : ['field_user']
  );

  ngOnInit(): void { this.load(); }

  async load(): Promise<void> {
    this.loading.set(true);
    this.apiError.set(null);
    try {
      this.users.set(await this.admin.getUsers());
    } catch (e: any) {
      this.apiError.set(e?.error?.detail ?? '無法載入使用者');
      this.users.set([]);
    } finally {
      this.loading.set(false);
    }
  }

  openForm(): void {
    this.form = {
      email: '',
      password: '',
      role: 'field_user',
      company_id: this.isSuperAdmin() ? null : this.myCompanyId(),
    };
    this.showForm.set(true);
  }

  cancelForm(): void { this.showForm.set(false); }

  async submit(): Promise<void> {
    if (!this.form.email || !this.form.password) return;
    this.submitting.set(true);
    try {
      const payload: UserCreate = {
        email: this.form.email,
        password: this.form.password,
        role: this.form.role,
        company_id: this.form.company_id || null,
      };
      await this.admin.createUser(payload);
      this.toast.success('使用者已建立');
      this.showForm.set(false);
      await this.load();
    } catch (e: any) {
      this.toast.error(e?.error?.detail ?? '建立失敗');
    } finally {
      this.submitting.set(false);
    }
  }

  async deactivate(user: UserRow): Promise<void> {
    if (!confirm(`確認停用 ${user.email}？`)) return;
    try {
      await this.admin.deactivateUser(user.user_id);
      this.toast.success('已停用');
      await this.load();
    } catch (e: any) {
      this.toast.error(e?.error?.detail ?? '停用失敗');
    }
  }

  roleColor(role: string): 'rust' | 'teal' | '' {
    if (role === 'superadmin') return 'rust';
    if (role === 'company_admin') return 'teal';
    return '';
  }
}
