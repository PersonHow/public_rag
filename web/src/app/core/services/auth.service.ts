import { Injectable, signal, computed, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { LoginRequest, LoginResponse, CurrentUser } from '../../shared/models';

const USER_KEY = 'plm_user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http   = inject(HttpClient);
  private readonly router = inject(Router);

  // access_token 改放 httpOnly cookie，JS 不再持有；此處只保留非敏感的身分資訊供 UI 使用。
  private readonly _user = signal<CurrentUser | null>(this._loadUser());

  readonly currentUser  = this._user.asReadonly();
  readonly isLoggedIn   = computed(() => !!this._user());
  readonly isAdmin      = computed(() => {
    const r = this._user()?.role;
    return r === 'superadmin' || r === 'company_admin';
  });
  readonly isSuperAdmin = computed(() => this._user()?.role === 'superadmin');

  async login(email: string, password: string): Promise<void> {
    const body: LoginRequest = { email, password };
    const res = await firstValueFrom(
      this.http.post<LoginResponse>(`${environment.apiUrl}/auth/login`, body)
    );
    const user: CurrentUser = {
      email,
      role: res.role as CurrentUser['role'],
      company_id: res.company_id,
      company_name: res.company_name,
    };
    this._user.set(user);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  async logout(): Promise<void> {
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/auth/logout`, {}));
    } catch {
      // 後端清 cookie 失敗也要清掉前端狀態，避免卡在已登出但畫面仍顯示登入。
    }
    this._user.set(null);
    localStorage.removeItem(USER_KEY);
    this.router.navigate(['/login']);
  }

  private _loadUser(): CurrentUser | null {
    try {
      const raw = localStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  }
}
