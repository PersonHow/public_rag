import { Component, inject, signal, Input, OnInit, OnDestroy, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { PreviewService } from '../../core/services/preview.service';
import { AuthService } from '../../core/services/auth.service';
import { ToastService } from '../../core/services/toast.service';
import { Chunk } from '../../shared/models';
import { StepperComponent } from '../../shared/components/stepper/stepper.component';
import { PageHeadComponent } from '../../shared/components/page-head/page-head.component';
import { StatusBadgeComponent } from '../../shared/components/status-badge/status-badge.component';
import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { TruncateIdPipe } from '../../shared/pipes/truncate-id.pipe';

@Component({
  selector: 'app-preview',
  standalone: true,
  imports: [RouterLink, FormsModule, StepperComponent, PageHeadComponent, StatusBadgeComponent, EmptyStateComponent, TruncateIdPipe],
  templateUrl: './preview.component.html',
  styleUrl: './preview.component.scss',
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

  // Worker 仍在處理中（status=pending_preview 但 chunks 尚未出現）
  readonly isWorkerRunning = computed(() =>
    this.status() === 'pending_preview' && this.svc.chunks().length === 0
  );

  private _pollSub?: Subscription;

  readonly statusLabel = computed(() => {
    if (this.isWorkerRunning()) return '解析中';
    const m: Record<string, string> = {
      pending_preview: '等待確認',
      confirmed: '已確認',
      processing: '處理中',
      done: '完成',
      failed: '已拒絕',
    };
    return m[this.status()] ?? this.status();
  });

  readonly statusColor = computed((): 'teal' | 'rust' | 'ink' | '' => {
    if (this.isWorkerRunning()) return '';
    const s = this.status();
    if (s === 'pending_preview' || s === 'done') return 'teal';
    if (s === 'failed') return 'rust';
    if (s === 'confirmed' || s === 'processing') return 'ink';
    return '';
  });

  async ngOnInit(): Promise<void> {
    // Step 1：只打 status，快速顯示頁面框架
    await this.svc.loadStatus(this.sessionId);

    const status = this.svc.session()?.status;

    if (status === 'pending_preview') {
      // Step 2：先試著撈一次 chunks（若 Worker 剛好跑完就直接顯示）
      await this.svc.tryLoadChunks(this.sessionId);
      // Step 3：啟動 polling，chunks 還是空的話每 3 秒重試
      this._pollSub = this.svc.startPolling(this.sessionId);
    } else {
      // confirmed / done / failed → Worker 肯定跑完了，直接撈
      await this.svc.tryLoadChunks(this.sessionId);
    }
  }

  ngOnDestroy(): void {
    this._pollSub?.unsubscribe();
    this.svc.reset();
  }

  async onConfirm(): Promise<void> {
    this.actionLoading.set(true);
    try {
      const res = await this.svc.confirm(this.sessionId);
      this.toast.success(res.message);
    } catch (e: any) {
      this.toast.error(e?.error?.detail ?? '確認失敗');
    } finally {
      this.actionLoading.set(false);
    }
  }

  async onReject(): Promise<void> {
    if (!confirm('確定要拒絕此 Session？文件需重新上傳。')) return;
    this.actionLoading.set(true);
    try {
      const res = await this.svc.reject(this.sessionId);
      this.toast.success(res.message);
    } catch (e: any) {
      this.toast.error(e?.error?.detail ?? '拒絕失敗');
    } finally {
      this.actionLoading.set(false);
    }
  }

  isLowConf(chunk: Chunk): boolean {
    const doc = this.svc.documents().find(d => d.doc_id === chunk.doc_id);
    return doc?.has_low_confidence === true;
  }

  hasAnyField(c: Chunk): boolean {
    return !!(c.product_name || c.material || c.dimensions || c.face ||
              c.situation || c.action || c.reason || c.applies_to);
  }
}
