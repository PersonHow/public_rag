import { Component, inject, signal, Input, OnInit, OnDestroy, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { PreviewService } from './services/preview.service';
import { AuthService } from '../../core/auth/auth.service';
import { ToastService } from '../../core/notifications/toast.service';
import { Chunk } from '../../core/models';
import { StepperComponent } from '../../components/stepper/stepper.component';

@Component({
  selector: 'app-preview',
  standalone: true,
  imports: [RouterLink, FormsModule, StepperComponent],
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

  private _pollSub?: Subscription;

  readonly statusLabel = computed(() => {
    const m: Record<string, string> = {
      pending_preview: '等待確認', confirmed: '已確認',
      processing: '處理中', done: '完成', failed: '已拒絕',
    };
    return m[this.status()] ?? this.status();
  });

  async ngOnInit(): Promise<void> {
    await this.svc.loadSession(this.sessionId);
    if (this.svc.session()?.status === 'pending_preview') {
      this._pollSub = this.svc.startPolling(this.sessionId);
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
