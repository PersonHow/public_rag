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
      const msg = err?.error?.detail ?? '帳號或密碼錯誤';
      this.errorMsg.set(msg);
    } finally {
      this.loading.set(false);
    }
  }
}
