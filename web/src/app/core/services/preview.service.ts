import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom, interval, switchMap, takeWhile } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  SessionStatusResponse, SessionChunksResponse,
  Document, Chunk, ConfirmResponse
} from '../../shared/models';

@Injectable({ providedIn: 'root' })
export class PreviewService {
  private readonly http = inject(HttpClient);

  readonly session   = signal<SessionStatusResponse | null>(null);
  readonly documents = signal<Document[]>([]);
  readonly chunks    = signal<Chunk[]>([]);
  readonly loading   = signal(false);
  readonly error     = signal<string | null>(null);

  readonly selectedDocId = signal<string | null>(null);
  readonly filter        = signal('');
  readonly groupBy       = signal<'case_id' | 'product_id'>('product_id');

  readonly lowConfidenceCount = computed(() =>
    this.documents().filter(d => d.has_low_confidence).length
  );

  readonly canConfirm = computed(() =>
    this.session()?.status === 'pending_preview' && this.chunks().length > 0
  );

  readonly filteredChunks = computed(() => {
    const docId = this.selectedDocId();
    const q     = this.filter().toLowerCase();
    return this.chunks().filter(c => {
      const matchDoc = !docId || c.doc_id === docId;
      const matchQ   = !q ||
        (c.product_name ?? '').toLowerCase().includes(q) ||
        (c.embed_text ?? '').toLowerCase().includes(q) ||
        (c.case_id ?? '').toLowerCase().includes(q);
      return matchDoc && matchQ;
    });
  });

  // ── 載入 session status（不撈 chunks）────────────────────────────────
  async loadStatus(sessionId: string): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const status = await firstValueFrom(
        this.http.get<SessionStatusResponse>(
          `${environment.apiUrl}/sessions/${sessionId}`
        )
      );
      this.session.set(status);
    } catch (e: any) {
      this.error.set(e?.error?.detail ?? '載入失敗');
    } finally {
      this.loading.set(false);
    }
  }

  // ── 嘗試撈 chunks（Worker 未完成時回傳空陣列，不報錯）────────────────
  async tryLoadChunks(sessionId: string): Promise<void> {
    try {
      const data = await firstValueFrom(
        this.http.get<SessionChunksResponse>(
          `${environment.apiUrl}/sessions/${sessionId}/chunks`
        )
      );
      this.documents.set(data.documents);
      this.chunks.set(data.chunks);
      if (!this.selectedDocId() && data.documents.length > 0) {
        this.selectedDocId.set(data.documents[0].doc_id);
      }
    } catch (_) {
      // Worker 未完成或網路錯誤，靜默忽略，交給 polling 重試
    }
  }

  // ── Polling：每 3 秒打 status，chunks 尚未撈到時順帶重試 /chunks ─────
  startPolling(sessionId: string) {
    return interval(3000).pipe(
      switchMap(() =>
        this.http.get<SessionStatusResponse>(
          `${environment.apiUrl}/sessions/${sessionId}`
        )
      ),
      // 停止條件：chunks 已有資料，或 status 不再是 pending_preview
      // inclusive=true → 最後一筆仍送入 subscribe（確保 session signal 更新）
      takeWhile(
        s => s.status === 'pending_preview' && this.chunks().length === 0,
        true
      ),
    ).subscribe(async s => {
      this.session.set(s);

      // chunks 還沒進來 + Worker 仍在跑 → 重試一次 /chunks
      if (this.chunks().length === 0 && s.status === 'pending_preview') {
        await this.tryLoadChunks(sessionId);
      }
    });
  }

  async confirm(sessionId: string): Promise<ConfirmResponse> {
    const res = await firstValueFrom(
      this.http.post<ConfirmResponse>(
        `${environment.apiUrl}/sessions/${sessionId}/confirm`, {}
      )
    );
    this.session.update(s => s ? { ...s, status: 'confirmed' } : s);
    return res;
  }

  async reject(sessionId: string): Promise<ConfirmResponse> {
    const res = await firstValueFrom(
      this.http.post<ConfirmResponse>(
        `${environment.apiUrl}/sessions/${sessionId}/reject`, {}
      )
    );
    this.session.update(s => s ? { ...s, status: 'failed' } : s);
    return res;
  }

  reset(): void {
    this.session.set(null);
    this.documents.set([]);
    this.chunks.set([]);
    this.selectedDocId.set(null);
    this.filter.set('');
  }
}
