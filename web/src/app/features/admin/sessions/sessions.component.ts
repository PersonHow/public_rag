import { Component, inject, signal, computed, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router, RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { SessionStatusResponse } from '../../../shared/models';
import { ToastService } from '../../../core/services/toast.service';
import { PreviewService } from '../../../core/services/preview.service';
import { PageHeadComponent } from '../../../shared/components/page-head/page-head.component';
import { StatusBadgeComponent } from '../../../shared/components/status-badge/status-badge.component';
import { EmptyStateComponent } from '../../../shared/components/empty-state/empty-state.component';
import { TruncateIdPipe } from '../../../shared/pipes/truncate-id.pipe';
import { ButtonComponent } from '../../../shared/components/button/button.component';

@Component({
  selector: 'app-admin-sessions',
  standalone: true,
  imports: [RouterLink, PageHeadComponent, StatusBadgeComponent, EmptyStateComponent, TruncateIdPipe, ButtonComponent],
  templateUrl: './sessions.component.html',
  styleUrl: './sessions.component.scss',
})
export class AdminSessionsComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly toast = inject(ToastService);
  private readonly router = inject(Router);
  private readonly preview = inject(PreviewService);

  readonly sessions = signal<SessionStatusResponse[]>([]);
  readonly loading = signal(false);
  readonly apiError = signal<string | null>(null);
  readonly pendingCount = computed(() => this.sessions().filter(s => s.status === 'pending_preview').length);

  // ── 批次選取（僅 pending_preview 可選）─────────────────
  readonly selected = signal<Set<string>>(new Set());
  readonly selectedCount = computed(() => this.selected().size);
  readonly batchLoading = signal(false);
  readonly pendingSessions = computed(() => this.sessions().filter(s => s.status === 'pending_preview'));
  readonly allPendingSelected = computed(() => {
    const pend = this.pendingSessions();
    return pend.length > 0 && pend.every(s => this.selected().has(s.session_id));
  });

  ngOnInit(): void { this.load(); }

  async load(): Promise<void> {
    this.loading.set(true);
    this.apiError.set(null);
    try {
      const res = await firstValueFrom(
        this.http.get<SessionStatusResponse[]>(`${environment.apiUrl}/sessions`)
      );
      this.sessions.set(Array.isArray(res) ? res : []);
      this._pruneSelection();
    } catch (e: any) {
      // 404 = 後端 list endpoint 尚未實作，顯示空列表即可
      this.sessions.set([]);
      if (e?.status !== 404) {
        this.apiError.set(e?.error?.detail ?? '無法載入');
      }
    } finally {
      this.loading.set(false);
    }
  }

  isSelected(id: string): boolean {
    return this.selected().has(id);
  }

  toggle(id: string): void {
    this.selected.update(set => {
      const next = new Set(set);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  toggleAll(): void {
    const pend = this.pendingSessions();
    this.selected.update(() =>
      this.allPendingSelected() ? new Set() : new Set(pend.map(s => s.session_id))
    );
  }

  /** 把選取的 session 一次帶進批次預覽頁。 */
  previewSelected(): void {
    const ids = [...this.selected()];
    if (ids.length === 0) return;
    this.router.navigate(['/preview', ids[0]], { queryParams: { batch: ids.join(',') } });
  }

  /** 不進預覽頁，直接確認選取（僅確認已解析完成者）。 */
  async confirmSelected(): Promise<void> {
    const ids = [...this.selected()];
    if (ids.length === 0) return;

    this.batchLoading.set(true);
    let ok = 0, skipped = 0, failed = 0;
    for (const id of ids) {
      const ready = await this.preview.checkReady(id);
      if (!ready) { skipped++; continue; }
      try {
        await this.preview.confirmRaw(id);
        ok++;
      } catch {
        failed++;
      }
    }
    this.batchLoading.set(false);
    this.selected.set(new Set());
    await this.load();

    const parts: string[] = [];
    if (ok > 0)      parts.push(`已確認 ${ok} 份`);
    if (skipped > 0) parts.push(`${skipped} 份尚未解析完成略過`);
    if (failed > 0)  parts.push(`${failed} 份失敗`);
    const msg = parts.join('、');
    if (failed > 0) this.toast.error(msg);
    else this.toast.success(msg || '沒有可確認的檔案');
  }

  private _pruneSelection(): void {
    const valid = new Set(this.pendingSessions().map(s => s.session_id));
    this.selected.update(set => new Set([...set].filter(id => valid.has(id))));
  }

  statusColor(status: string): 'teal' | 'rust' | 'ink' | '' {
    if (status === 'pending_preview' || status === 'done') return 'teal';
    if (status === 'failed') return 'rust';
    if (status === 'confirmed' || status === 'processing') return 'ink';
    return '';
  }
}
