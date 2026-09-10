import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/services/auth.service';
import { ToastService } from '../../../core/services/toast.service';
import { ButtonComponent } from '../../../shared/components/button/button.component';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule, ButtonComponent],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  private readonly auth   = inject(AuthService);
  private readonly router = inject(Router);
  private readonly toast  = inject(ToastService);

  email    = '';
  password = '';
  loading  = signal(false);
  errorMsg = signal('');

  async onSubmit(): Promise<void> {
    if (!this.email || !this.password) return;
    this.loading.set(true);
    this.errorMsg.set('');
    try {
      await this.auth.login(this.email, this.password);
      this.toast.success(`歡迎回來！`);
      this.router.navigate(['/hub']);
    } catch (err: any) {
      const msg = this._errorMessage(err?.status);
      this.errorMsg.set(msg);
      this.toast.error(msg);
      this.password = '';
    } finally {
      this.loading.set(false);
    }
  }

  private _errorMessage(status?: number): string {
    switch (status) {
      case 401: return '帳號或密碼錯誤';
      case 403: return '此帳號已被停用，請聯絡管理員';
      case 429: return '登入失敗次數過多，請稍後再試';
      case 0:   return '無法連線到伺服器，請稍後再試';
      default:  return status && status >= 500 ? '伺服器錯誤，請稍後再試' : '登入失敗，請稍後再試';
    }
  }
}
