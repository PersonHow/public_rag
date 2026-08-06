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
  // 用 sessionStorage：分頁關閉即失效（視同登出），重新整理不受影響。
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
    sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  /**
   * 向後端驗證 cookie session 是否仍有效。
   * 前端身分狀態（sessionStorage）與 httpOnly cookie 可能脫鉤
   * （如 token 過期後重新整理），401 時由 error interceptor 統一登出。
   */
  async validateSession(): Promise<void> {
    if (!this._user()) return;
    try {
      await firstValueFrom(this.http.get(`${environment.apiUrl}/users/me`));
    } catch {
      // 401 已由 error interceptor 處理（自動登出＋提示），其他錯誤不動登入狀態。
    }
  }

  // 防重入：連點登出或多個 401 同時觸發時，避免重複呼叫 logout API（會產生多筆登出稽核記錄）。
  private _loggingOut = false;

  async logout(): Promise<void> {
    if (this._loggingOut) return;
    this._loggingOut = true;
    try {
      await firstValueFrom(this.http.post(`${environment.apiUrl}/auth/logout`, {}));
    } catch {
      // 後端清 cookie 失敗也要清掉前端狀態，避免卡在已登出但畫面仍顯示登入。
    } finally {
      this._loggingOut = false;
    }
    this._user.set(null);
    sessionStorage.removeItem(USER_KEY);
    this.router.navigate(['/login']);
  }

  private _loadUser(): CurrentUser | null {
    localStorage.removeItem(USER_KEY); // 清除舊版存放在 localStorage 的身分（已改用 sessionStorage）
    try {
      const raw = sessionStorage.getItem(USER_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch { return null; }
  }
}
