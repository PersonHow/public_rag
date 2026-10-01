import { Component, inject, signal, computed, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AdminService, UserRow, UserCreate } from '../../../core/services/admin.service';
import { AuthService } from '../../../core/services/auth.service';
import { ToastService } from '../../../core/services/toast.service';
import { PageHeadComponent } from '../../../shared/components/page-head/page-head.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import { EmptyStateComponent } from '../../../shared/components/empty-state/empty-state.component';
import { TruncateIdPipe } from '../../../shared/pipes/truncate-id.pipe';
import { ButtonComponent } from '../../../shared/components/button/button.component';
import { PasswordToggleComponent } from '../../../shared/components/password-toggle/password-toggle.component';

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [FormsModule, PageHeadComponent, StatusBadgeComponent, EmptyStateComponent, TruncateIdPipe, ButtonComponent, PasswordToggleComponent],
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
  readonly showPassword = signal(false);

  readonly isSuperAdmin = this.auth.isSuperAdmin;
  readonly myCompanyId  = computed(() => this.auth.currentUser()?.company_id ?? null);

  form: UserCreate = { email: '', password: '', role: 'field_user', company_id: null };

  // 與後端 app/schemas/user.py 的 password_strength 同步
  readonly passwordRules = [
    { label: '至少 12 碼',   test: (v: string) => v.length >= 12 },
    { label: '大寫英文字母', test: (v: string) => /[A-Z]/.test(v) },
    { label: '小寫英文字母', test: (v: string) => /[a-z]/.test(v) },
    { label: '數字',         test: (v: string) => /\d/.test(v) },
    { label: '符號',         test: (v: string) => /[^A-Za-z0-9]/.test(v) },
  ];

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
    this.showPassword.set(false);
    this.showForm.set(true);
  }

  passwordValid(): boolean {
    return this.passwordRules.every(r => r.test(this.form.password));
  }

  cancelForm(): void { this.showForm.set(false); }

  async submit(): Promise<void> {
    if (!this.form.email || !this.passwordValid()) return;
    this.submitting.set(true);
    try {
      const payload: UserCreate = {
        email: this.form.email,
        password: this.form.password,
        role: this.form.role,
        company_id: this.form.role === 'superadmin' ? null : (this.form.company_id || null),
      };
      await this.admin.createUser(payload);
      this.toast.success('使用者已建立');
      this.showForm.set(false);
      await this.load();
    } catch (e: any) {
      // 422 驗證錯誤的 detail 是陣列（FastAPI 格式）
      const detail = e?.error?.detail;
      this.toast.error((Array.isArray(detail) ? detail[0]?.msg : detail) ?? '建立失敗');
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
