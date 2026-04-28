import { Component, inject, signal, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { ToastService } from '../../../core/notifications/toast.service';

interface UserRow {
  user_id: string;
  email: string;
  role: string;
  is_active: boolean;
  company_id: string | null;
}

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [],
  styles: [`
    .users-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .users-table th, .users-table td {
      text-align: left; padding: 11px 14px; border-bottom: 1px solid var(--line); vertical-align: middle;
    }
    .users-table th {
      font-family: var(--font-mono); font-size: 10px; letter-spacing: .1em;
      text-transform: uppercase; font-weight: 700; background: rgba(40,61,59,.04);
    }
    .users-table tr:hover td { background: var(--bg-3); }
    .uid { font-family: var(--font-mono); font-size: 11px; color: var(--muted); }
  `],
  template: `
    <div style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:22px;flex-wrap:wrap;gap:12px">
      <div>
        <span class="px-stamp">ADMIN · USERS</span>
        <h1 style="margin-top:8px;font-size:28px">使用者管理</h1>
        <p style="color:var(--muted);font-size:13px;margin:0">租戶成員與角色管理（需要 superadmin 或 company_admin）</p>
      </div>
      <button class="btn" (click)="load()">↺ 重新整理</button>
    </div>

    @if (loading()) {
      <div style="text-align:center;padding:48px;font-family:var(--font-mono);color:var(--muted)">⏳ 載入中…</div>
    }

    @if (!loading() && users().length > 0) {
      <div class="card" style="padding:0;overflow:hidden">
        <table class="users-table">
          <thead>
            <tr>
              <th>User ID</th>
              <th>Email</th>
              <th>角色</th>
              <th>狀態</th>
              <th>Company</th>
            </tr>
          </thead>
          <tbody>
            @for (u of users(); track u.user_id) {
              <tr>
                <td class="uid">{{ u.user_id.slice(0,8) }}…</td>
                <td>{{ u.email }}</td>
                <td>
                  <span class="pill"
                        [class.rust]="u.role==='superadmin'"
                        [class.teal]="u.role==='company_admin'">
                    {{ u.role }}
                  </span>
                </td>
                <td>
                  <span class="pill" [class.teal]="u.is_active" [class.rust]="!u.is_active">
                    {{ u.is_active ? '啟用' : '停用' }}
                  </span>
                </td>
                <td style="font-family:var(--font-mono);font-size:11px;color:var(--muted)">
                  {{ u.company_id ?? '—' }}
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>
    }

    @if (!loading() && users().length === 0) {
      <div style="text-align:center;padding:48px;color:var(--muted);font-family:var(--font-mono)">
        <div style="font-size:32px;margin-bottom:12px">□</div>
        無使用者資料
        @if (apiError()) {
          <div style="margin-top:12px;font-size:11px;color:var(--rust)">{{ apiError() }}</div>
        }
      </div>
    }
  `,
})
export class AdminUsersComponent implements OnInit {
  private readonly http  = inject(HttpClient);
  private readonly toast = inject(ToastService);

  readonly users    = signal<UserRow[]>([]);
  readonly loading  = signal(false);
  readonly apiError = signal<string | null>(null);

  ngOnInit(): void { this.load(); }

  async load(): Promise<void> {
    this.loading.set(true);
    this.apiError.set(null);
    try {
      const res = await firstValueFrom(
        this.http.get<UserRow[]>(`${environment.apiUrl}/admin/users`)
      );
      this.users.set(Array.isArray(res) ? res : []);
    } catch (e: any) {
      this.apiError.set(e?.error?.detail ?? '無法載入使用者');
      this.users.set([]);
    } finally {
      this.loading.set(false);
    }
  }
}
