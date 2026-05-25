import { Component, inject, signal, Input, OnInit, OnDestroy, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { UpperCasePipe } from '@angular/common';
import { Subscription } from 'rxjs';
import { PreviewService } from '../../core/services/preview.service';
import { AuthService } from '../../core/services/auth.service';
import { ToastService } from '../../core/services/toast.service';
import { Chunk } from '../../shared/models';
import { StepperComponent } from '../../shared/components/stepper/stepper.component';
import { PageHeadComponent } from '../../shared/components/page-head/page-head.component';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ChunkCardComponent, ChunkGroup } from './components/chunk-card/chunk-card.component';
import { FulltextViewComponent } from './components/fulltext-view/fulltext-view.component';
import { ButtonComponent } from '../../shared/components/button/button.component';

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

  readonly isAdmin       = this.auth.isAdmin;
  readonly actionLoading = signal(false);
  readonly status        = computed(() => this.svc.session()?.status ?? '');
  readonly isConfirmed   = computed(() => this.status() === 'confirmed');

  // ── View mode ─────────────────────────────────────────
  readonly viewMode     = signal<'card' | 'full'>('card');
  readonly showViewTabs = computed(() => !!this.svc.selectedDocId());

  readonly isWorkerRunning = computed(() =>
    this.status() === 'pending_preview' && this.svc.chunks().length === 0
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
    const m: Record<string, string> = {
      pending_preview: '等待確認',
      confirmed:       '已確認',
      processing:      '處理中',
      done:            '完成',
      failed:          '已拒絕',
    };
    return m[this.status()] ?? this.status();
  });

  readonly statusColor = computed((): '' | 'rust' | 'ink' | 'teal' | 'wine' => {
    const m: Record<string, '' | 'rust' | 'ink' | 'teal' | 'wine'> = {
      pending_preview: 'wine',
      confirmed:       'teal',
      processing:      'ink',
      done:            'teal',
      failed:          'rust',
    };
    return m[this.status()] ?? '';
  });

  // ── Lifecycle ─────────────────────────────────────────
  ngOnInit(): void {
    this.svc.loadSession(this.sessionId);

    this._pollSub = new Subscription();
    const poll = setInterval(() => {
      if (this.isWorkerRunning()) {
        this.svc.loadSession(this.sessionId);
      } else {
        clearInterval(poll);
      }
    }, 5000);
    this._pollSub.add(() => clearInterval(poll));
  }

  ngOnDestroy(): void {
    this._pollSub?.unsubscribe();
    this.svc.reset();
  }

  // ── Doc selection ─────────────────────────────────────
  selectDoc(docId: string | null): void {
    this.svc.selectedDocId.set(docId);
    this.viewMode.set('card');
    if (docId) {
      this.svc.loadFullText(this.sessionId, docId);
    }
  }

  // ── Confirm / Reject ──────────────────────────────────
  async onConfirm(): Promise<void> {
    this.actionLoading.set(true);
    try {
      await this.svc.confirm(this.sessionId);
      this.toast.success('已確認，Chunks 送入向量化 Pipeline');
    } catch {
      this.toast.error('確認失敗');
    } finally {
      this.actionLoading.set(false);
    }
  }

  async onReject(): Promise<void> {
    this.actionLoading.set(true);
    try {
      await this.svc.reject(this.sessionId);
      this.toast.success('已拒絕');
    } catch {
      this.toast.error('拒絕失敗');
    } finally {
      this.actionLoading.set(false);
    }
  }

  isLowConf(chunk: Chunk): boolean {
    return this.svc.documents().find(d => d.doc_id === chunk.doc_id)?.has_low_confidence === true;
  }
}
