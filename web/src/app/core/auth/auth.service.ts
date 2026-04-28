import { Injectable, signal, computed, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { LoginRequest, TokenResponse, CurrentUser } from '../models';

const TOKEN_KEY = 'plm_token';
const USER_KEY  = 'plm_user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http   = inject(HttpClient);
  private readonly router = inject(Router);

  private readonly _token = signal<string | null>(localStorage.getItem(TOKEN_KEY));
  private readonly _user  = signal<CurrentUser | null>(this._loadUser());

  readonly token        = this._token.asReadonly();
  readonly currentUser  = this._user.asReadonly();
  readonly isLoggedIn   = computed(() => !!this._token());
  readonly isAdmin      = computed(() => {
    const r = this._user()?.role;
    return r === 'superadmin' || r === 'company_admin';
  });
  readonly isSuperAdmin = computed(() => this._user()?.role === 'superadmin');

  async login(email: string, password: string): Promise<void> {
    const body: LoginRequest = { email, password };
    const res = await firstValueFrom(
      this.http.post<TokenResponse>(`${environment.apiUrl}/auth/login`, body)
    );
    const user: CurrentUser = {
      email,
      role: res.role as CurrentUser['role'],
      company_id: res.company_id,
    };
    this._token.set(res.access_token);
    this._user.set(user);
    localStorage.setItem(TOKEN_KEY, res.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  }

  logout(): void {
    this._token.set(null);
    this._user.set(null);
    localStorage.removeItem(TOKEN_KEY);
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
