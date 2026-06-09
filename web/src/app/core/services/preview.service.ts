import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import {
  SessionStatusResponse, SessionChunksResponse,
  Document, Chunk, ChunkPatch, ConfirmResponse, FullTextResponse
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

  /** 是否全為不產生 chunks 的程式/圖檔類型（tap / nc / dxf / unknown） */
  readonly isCodeFileOnly = computed(() => {
    const docs = this.documents();
    if (docs.length === 0) return false;
    return docs.every(d => ['tap', 'nc', 'dxf', 'unknown'].includes(d.doc_type));
  });

  readonly canConfirm = computed(() =>
    this.session()?.status === 'pending_preview' &&
    (this.chunks().length > 0 || this.isCodeFileOnly())
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

  /**
   * 靜默刷新（輪詢用）：不翻轉 loading 旗標，避免整頁 spinner 每次輪詢都閃爍。
   * 失敗時靜默忽略，不覆蓋既有畫面。
   */
  async refreshSilent(sessionId: string): Promise<void> {
    try {
      const status = await firstValueFrom(
        this.http.get<SessionStatusResponse>(
          `${environment.apiUrl}/sessions/${sessionId}`
        )
      );
      this.session.set(status);
    } catch {
      return;
    }
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

  // ── v2：預覽階段 inline 編輯單一 chunk ─────────────────
  async patchChunk(sessionId: string, chunkId: string, patch: ChunkPatch): Promise<Chunk> {
    const updated = await firstValueFrom(
      this.http.patch<Chunk>(
        `${environment.apiUrl}/sessions/${sessionId}/chunks/${chunkId}`,
        patch
      )
    );
    this.chunks.update(arr =>
      arr.map(c => c.chunk_id === chunkId ? { ...c, ...updated } : c)
    );
    // 同步整體預覽快取，讓 fulltext-view 重新分組
    // Chunk / FullTextChunk 的 optionality 不同（null vs undefined），用 unknown 轉接
    this.fullText.update(ft => ft ? {
      ...ft,
      chunks: ft.chunks.map(c =>
        c.chunk_id === chunkId
          ? ({ ...c, ...updated } as unknown as typeof c)
          : c
      ),
    } : ft);
    return updated;
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
