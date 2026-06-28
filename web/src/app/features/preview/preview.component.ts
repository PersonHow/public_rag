import { Component, inject, signal, Input, OnInit, OnDestroy, computed } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { UpperCasePipe } from '@angular/common';
import { Subscription } from 'rxjs';
import { PreviewService } from '../../core/services/preview.service';
import { AuthService } from '../../core/services/auth.service';
import { ToastService } from '../../core/services/toast.service';
import { Chunk, SessionStatus } from '../../shared/models';
import { StepperComponent } from '../../shared/components/stepper/stepper.component';
import { PageHeadComponent } from '../../shared/components/page-head/page-head.component';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ChunkCardComponent, ChunkGroup } from './components/chunk-card/chunk-card.component';
import { FulltextViewComponent } from './components/fulltext-view/fulltext-view.component';
import { ButtonComponent } from '../../shared/components/button/button.component';

interface BatchFile {
  sessionId: string;
  filename: string;
  status: SessionStatus;
}

@Component({
  selector: 'app-preview',
  standalone: true,
  imports: [
    RouterLink, FormsModule, UpperCasePipe,
    StepperComponent, PageHeadComponent,
    StatusBadgeComponent, EmptyStateComponent,
    ChunkCardComponent, FulltextViewComponent, ButtonComponent,
  ],
  templateUrl: './preview.component.html',
  styleUrl:    './preview.component.scss',
})
export class PreviewComponent implements OnInit, OnDestroy {
  @Input() sessionId!: string;

  readonly svc   = inject(PreviewService);
  private readonly auth  = inject(AuthService);
  private readonly toast = inject(ToastService);
  private readonly route = inject(ActivatedRoute);

  readonly isAdmin       = this.auth.isAdmin;
  readonly actionLoading = signal(false);
  readonly status        = computed(() => this.svc.session()?.status ?? '');
  readonly isConfirmed   = computed(() => this.status() === 'confirmed');

  // ── 批次預覽 ──────────────────────────────────────────
  /** 目前正在預覽的 session（批次時可在 batchFiles 之間切換）。 */
  readonly activeSessionId = signal<string>('');
  readonly batchFiles      = signal<BatchFile[]>([]);
  readonly isBatch         = computed(() => this.batchFiles().length > 1);
  readonly pendingBatchCount = computed(() =>
    this.batchFiles().filter(f => f.status === 'pending_preview').length
  );

  // ── View mode ─────────────────────────────────────────
  readonly viewMode     = signal<'card' | 'full'>('card');
  readonly showViewTabs = computed(() => !!this.svc.selectedDocId());

  readonly isWorkerRunning = computed(() =>
    this.status() === 'pending_preview' &&
    this.svc.chunks().length === 0 &&
    !this.svc.isCodeFileOnly()
  );

  /** v2：只有 pending_preview + admin 才允許 inline 編輯 chunk。 */
  readonly canEditChunks = computed(() =>
    this.status() === 'pending_preview' && this.isAdmin()
  );

  // ── 卡片模式：分組（輪播狀態已移入 ChunkCardComponent）──
  readonly groupedChunks = computed((): ChunkGroup[] => {
    const map = new Map<string, ChunkGroup>();
    for (const chunk of this.svc.filteredChunks()) {
      const key = chunk.product_name || '（未指定產品）';
      if (!map.has(key)) {
        map.set(key, {
          productName: key,
          material:    chunk.material    ?? null,
          dimensions:  chunk.dimensions  ?? null,
          docType:     chunk.doc_type    ?? '',
          chunks:      [],
        });
      }
      map.get(key)!.chunks.push(chunk);
    }
    return Array.from(map.values());
  });

  // ── Status helpers ────────────────────────────────────
  private _pollSub?: Subscription;

  readonly statusLabel = computed(() => {
    if (this.isWorkerRunning()) return '解析中';
    return this.statusText(this.status());
  });

  statusText(s: string): string {
    const m: Record<string, string> = {
      pending_preview: '等待確認',
      confirmed:       '已確認',
      processing:      '處理中',
      done:            '完成',
      failed:          '已拒絕',
    };
    return m[s] ?? s;
  }

  readonly statusColor = computed(() => this.statusColorFor(this.status()));

  statusColorFor(s: string): '' | 'rust' | 'ink' | 'teal' | 'wine' {
    const m: Record<string, '' | 'rust' | 'ink' | 'teal' | 'wine'> = {
      pending_preview: 'wine',
      confirmed:       'teal',
      processing:      'ink',
      done:            'teal',
      failed:          'rust',
    };
    return m[s] ?? '';
  }

  // ── Lifecycle ─────────────────────────────────────────
  ngOnInit(): void {
    const active = this.route.snapshot.paramMap.get('sessionId') ?? this.sessionId;
    const batchParam = this.route.snapshot.queryParamMap.get('batch');
    const ids = batchParam
      ? batchParam.split(',').map(s => s.trim()).filter(Boolean)
      : [active];
    // 確保 active 一定在批次清單內
    if (!ids.includes(active)) ids.unshift(active);

    this.activeSessionId.set(active);
    this.batchFiles.set(ids.map(id => ({ sessionId: id, filename: '', status: 'pending_preview' })));
    this._loadBatchMeta(ids);
    this._loadActive(active);
  }

  ngOnDestroy(): void {
    this._pollSub?.unsubscribe();
    this.svc.reset();
  }

  /** 批次切換器需要的檔名與狀態（不影響主預覽載入）。 */
  private async _loadBatchMeta(ids: string[]): Promise<void> {
    await Promise.all(ids.map(async id => {
      try {
        const s = await this.svc.fetchStatus(id);
        this._patchBatch(id, { filename: s.filename ?? id, status: s.status });
      } catch {
        this._patchBatch(id, { filename: id });
      }
    }));
  }

  private _loadActive(id: string): void {
    this.svc.reset();
    this.svc.loadSession(id);
    this._startPolling(id);
  }

  private _startPolling(id: string): void {
    this._pollSub?.unsubscribe();
    this._pollSub = new Subscription();
    const poll = setInterval(() => {
      if (id !== this.activeSessionId()) { clearInterval(poll); return; }
      if (this.isWorkerRunning()) {
        // 靜默刷新，避免每 5 秒翻轉 loading 造成整頁 spinner 閃爍
        this.svc.refreshSilent(id);
      } else {
        clearInterval(poll);
      }
    }, 5000);
    this._pollSub.add(() => clearInterval(poll));
  }

  // ── 批次：切換目前預覽的檔案 ───────────────────────────
  selectSession(id: string): void {
    if (id === this.activeSessionId()) return;
    this.activeSessionId.set(id);
    this._loadActive(id);
  }

  private _patchBatch(id: string, patch: Partial<BatchFile>): void {
    this.batchFiles.update(arr => arr.map(f => f.sessionId === id ? { ...f, ...patch } : f));
  }

  // ── Doc selection ─────────────────────────────────────
  selectDoc(docId: string | null): void {
    this.svc.selectedDocId.set(docId);
    this.viewMode.set('card');
    if (docId) {
      this.svc.loadFullText(this.activeSessionId(), docId);
    }
  }

  // ── Confirm / Reject（單一 active session）─────────────
  async onConfirm(): Promise<void> {
    const id = this.activeSessionId();
    this.actionLoading.set(true);
    try {
      await this.svc.confirm(id);
      this._patchBatch(id, { status: 'confirmed' });
      this.toast.success('已確認，Chunks 送入向量化 Pipeline');
    } catch {
      this.toast.error('確認失敗');
    } finally {
      this.actionLoading.set(false);
    }
  }

  async onReject(): Promise<void> {
    const id = this.activeSessionId();
    this.actionLoading.set(true);
    try {
      await this.svc.reject(id);
      this._patchBatch(id, { status: 'failed' });
      this.toast.success('已拒絕');
    } catch {
      this.toast.error('拒絕失敗');
    } finally {
      this.actionLoading.set(false);
    }
  }

  // ── 批次：確認全部已解析完成的 pending session ──────────
  async onConfirmAll(): Promise<void> {
    const targets = this.batchFiles().filter(f => f.status === 'pending_preview');
    if (targets.length === 0) return;

    this.actionLoading.set(true);
    let ok = 0, skipped = 0, failed = 0;
    for (const f of targets) {
      const ready = await this.svc.checkReady(f.sessionId);
      if (!ready) { skipped++; continue; }
      try {
        if (f.sessionId === this.activeSessionId()) {
          await this.svc.confirm(f.sessionId);
        } else {
          await this.svc.confirmRaw(f.sessionId);
        }
        this._patchBatch(f.sessionId, { status: 'confirmed' });
        ok++;
      } catch {
        failed++;
      }
    }
    this.actionLoading.set(false);

    const parts: string[] = [];
    if (ok > 0)      parts.push(`已確認 ${ok} 份`);
    if (skipped > 0) parts.push(`${skipped} 份尚未解析完成略過`);
    if (failed > 0)  parts.push(`${failed} 份失敗`);
    const msg = parts.join('、');
    if (failed > 0) this.toast.error(msg);
    else this.toast.success(msg || '沒有可確認的檔案');
  }

  isLowConf(chunk: Chunk): boolean {
    return this.svc.documents().find(d => d.doc_id === chunk.doc_id)?.has_low_confidence === true;
  }
}
