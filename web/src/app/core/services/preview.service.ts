import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom, interval, switchMap, takeWhile } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  SessionStatusResponse, SessionChunksResponse,
  Document, Chunk, ConfirmResponse, FullTextResponse
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

  // ── Phase 5：整體預覽 ──────────────────────────────────
  readonly fullText        = signal<FullTextResponse | null>(null);
  readonly fullTextLoading = signal(false);

  // ── 便利 alias（供 template 使用）──────────────────────
  /** filter 的 alias，讓 template 可用 svc.searchQuery() */
  readonly searchQuery = computed(() => this.filter());

  /** 全部 chunks 數量 */
  readonly totalChunks = computed(() => this.chunks().length);

  /** 設定搜尋關鍵字 */
  setSearch(q: string): void {
    this.filter.set(q);
  }

  // ── Computed ──────────────────────────────────────────
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
        (c.embed_text   ?? '').toLowerCase().includes(q) ||
        (c.case_id      ?? '').toLowerCase().includes(q);
      return matchDoc && matchQ;
    });
  });

  // ── 載入 session status ───────────────────────────────
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

  // ── 便利方法：status + chunks 一次載入（供 component 使用）──
  async loadSession(sessionId: string): Promise<void> {
    await this.loadStatus(sessionId);
    await this.tryLoadChunks(sessionId);
  }

  // ── 嘗試撈 chunks ────────────────────────────────────
  async tryLoadChunks(sessionId: string): Promise<void> {
    try {
      const data = await firstValueFrom(
        this.http.get<SessionChunksResponse>(
          `${environment.apiUrl}/sessions/${sessionId}/chunks`
        )
      );
      this.documents.set(data.documents);
      this.chunks.set(data.chunks);
    } catch (_) {
      // Worker 未完成，靜默忽略
    }
  }

  // ── Phase 5：整體預覽 API ────────────────────────────
  async loadFullText(sessionId: string, docId: string): Promise<void> {
    // 已有相同文件的快取就不重打
    if (this.fullText()?.doc_id === docId) return;

    this.fullTextLoading.set(true);
    this.fullText.set(null);
    try {
      const data = await firstValueFrom(
        this.http.get<FullTextResponse>(
          `${environment.apiUrl}/sessions/${sessionId}/documents/${docId}/full-text`
        )
      );
      this.fullText.set(data);
    } catch {
      this.fullText.set(null);
    } finally {
      this.fullTextLoading.set(false);
    }
  }

  // ── Polling ──────────────────────────────────────────
  startPolling(sessionId: string) {
    return interval(3000).pipe(
      switchMap(() =>
        this.http.get<SessionStatusResponse>(
          `${environment.apiUrl}/sessions/${sessionId}`
        )
      ),
      takeWhile(
        s => s.status === 'pending_preview' && this.chunks().length === 0,
        true
      ),
    ).subscribe(async s => {
      this.session.set(s);
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
    this.fullText.set(null);
    this.selectedDocId.set(null);
    this.filter.set('');
  }
}
