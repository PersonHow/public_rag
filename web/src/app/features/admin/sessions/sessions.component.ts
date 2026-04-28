import { Component, inject, signal, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { SessionStatusResponse } from '../../../core/models';
import { ToastService } from '../../../core/notifications/toast.service';

@Component({
  selector: 'app-admin-sessions',
  standalone: true,
  imports: [RouterLink],
  styles: [`
    .sessions-table { width: 100%; border-collapse: collapse; font-size: 13px; }
    .sessions-table th, .sessions-table td {
      text-align: left; padding: 11px 14px; border-bottom: 1px solid var(--line); vertical-align: middle;
    }
    .sessions-table th {
      font-family: var(--font-mono); font-size: 10px; letter-spacing: .1em;
      text-transform: uppercase; font-weight: 700;
      background: rgba(40,61,59,.04);
    }
    .sessions-table tr:hover td { background: var(--bg-3); }
    .session-id { font-family: var(--font-mono); font-size: 11px; color: var(--muted); }
  `],
  template: `
    <div style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:22px;flex-wrap:wrap;gap:12px">
      <div>
        <span class="px-stamp">ADMIN · SESSIONS</span>
        <h1 style="margin-top:8px;font-size:28px">Session 管理</h1>
        <p style="color:var(--muted);font-size:13px;margin:0">所有上傳 Session 與狀態（需要管理員角色）</p>
      </div>
      <button class="btn" (click)="load()">↺ 重新整理</button>
    </div>

    @if (loading()) {
      <div style="text-align:center;padding:48px;font-family:var(--font-mono);color:var(--muted)">⏳ 載入中…</div>
    }

    @if (!loading() && sessions().length === 0) {
      <div style="text-align:center;padding:48px;color:var(--muted);font-family:var(--font-mono)">
        <div style="font-size:32px;margin-bottom:12px">□</div>
        目前沒有任何 Session 記錄
      </div>
    }

    @if (!loading() && sessions().length > 0) {
      <div class="card" style="padding:0;overflow:hidden">
        <table class="sessions-table">
          <thead>
            <tr>
              <th>Session ID</th>
              <th>狀態</th>
              <th>已確認</th>
              <th>失敗原因</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            @for (s of sessions(); track s.session_id) {
              <tr>
                <td class="session-id">{{ s.session_id.slice(0,8) }}…</td>
                <td>
                  <span class="pill"
                        [class.teal]="s.status==='pending_preview'"
                        [class.ink]="s.status==='confirmed'"
                        [class.rust]="s.status==='failed'">
                    {{ s.status }}
                  </span>
                </td>
                <td>{{ s.preview_confirmed ? '✓' : '—' }}</td>
                <td style="color:var(--rust);font-size:12px">{{ s.fail_reason ?? '—' }}</td>
                <td>
                  @if (s.status === 'pending_preview') {
                    <a class="btn sm" [routerLink]="['/preview', s.session_id]">預覽 ▸</a>
                  }
                </td>
              </tr>
            }
          </tbody>
        </table>
      </div>

      <div style="margin-top:12px;font-family:var(--font-mono);font-size:11px;color:var(--muted)">
        共 {{ sessions().length }} 筆 · pending_preview: {{ pendingCount() }} 筆
      </div>
    }

    @if (apiError()) {
      <div style="margin-top:18px;padding:14px;border:2px solid var(--rust);box-shadow:3px 3px 0 var(--rust);font-family:var(--font-mono);font-size:12px;color:var(--rust)">
        ⚠ {{ apiError() }}<br/>
        <span style="color:var(--muted)">Sessions 列表 API 尚未實作（Phase 2+），顯示空列表。</span>
      </div>
    }
  `,
})
export class AdminSessionsComponent implements OnInit {
  private readonly http  = inject(HttpClient);
  private readonly toast = inject(ToastService);

  readonly sessions  = signal<SessionStatusResponse[]>([]);
  readonly loading   = signal(false);
  readonly apiError  = signal<string | null>(null);
  readonly pendingCount = () => this.sessions().filter(s => s.status === 'pending_preview').length;

  ngOnInit(): void { this.load(); }

  async load(): Promise<void> {
    this.loading.set(true);
    this.apiError.set(null);
    try {
      // GET /sessions is Phase 2+ — handle 404/401 gracefully
      const res = await firstValueFrom(
        this.http.get<SessionStatusResponse[]>(`${environment.apiUrl}/sessions`)
      );
      this.sessions.set(Array.isArray(res) ? res : []);
    } catch (e: any) {
      const detail = e?.error?.detail ?? e?.message ?? '無法載入';
      this.apiError.set(detail);
      this.sessions.set([]);
    } finally {
      this.loading.set(false);
    }
  }
}
