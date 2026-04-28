import { Injectable, inject, signal, computed } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom, interval, switchMap, takeWhile } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
  SessionStatusResponse, SessionChunksResponse,
  Document, Chunk, ConfirmResponse
} from '../../../core/models';

@Injectable({ providedIn: 'root' })
export class PreviewService {
  private readonly http = inject(HttpClient);

  readonly session   = signal<SessionStatusResponse | null>(null);
  readonly documents = signal<Document[]>([]);
  readonly chunks    = signal<Chunk[]>([]);
  readonly loading   = signal(false);
  readonly error     = signal<string | null>(null);

  readonly selectedDocId     = signal<string | null>(null);
  readonly filter            = signal('');
  readonly groupBy           = signal<'case_id' | 'product_id'>('product_id');

  readonly lowConfidenceCount = computed(() =>
    this.documents().filter(d => d.has_low_confidence).length
  );

  readonly canConfirm = computed(() =>
    this.session()?.status === 'pending_preview'
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

  async loadSession(sessionId: string): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const [status, data] = await Promise.all([
        firstValueFrom(this.http.get<SessionStatusResponse>(`${environment.apiUrl}/sessions/${sessionId}`)),
        firstValueFrom(this.http.get<SessionChunksResponse>(`${environment.apiUrl}/sessions/${sessionId}/chunks`)),
      ]);
      this.session.set(status);
      this.documents.set(data.documents);
      this.chunks.set(data.chunks);
      if (data.documents.length > 0) {
        this.selectedDocId.set(data.documents[0].doc_id);
      }
    } catch (e: any) {
      this.error.set(e?.error?.detail ?? '載入失敗');
    } finally {
      this.loading.set(false);
    }
  }

  startPolling(sessionId: string) {
    return interval(3000).pipe(
      switchMap(() =>
        this.http.get<SessionStatusResponse>(`${environment.apiUrl}/sessions/${sessionId}`)
      ),
      takeWhile(s => s.status === 'pending_preview', true),
    ).subscribe(s => this.session.set(s));
  }

  async confirm(sessionId: string): Promise<ConfirmResponse> {
    const res = await firstValueFrom(
      this.http.post<ConfirmResponse>(`${environment.apiUrl}/sessions/${sessionId}/confirm`, {})
    );
    this.session.update(s => s ? { ...s, status: 'confirmed' } : s);
    return res;
  }

  async reject(sessionId: string): Promise<ConfirmResponse> {
    const res = await firstValueFrom(
      this.http.post<ConfirmResponse>(`${environment.apiUrl}/sessions/${sessionId}/reject`, {})
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
