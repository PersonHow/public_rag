import { Injectable, inject, signal } from '@angular/core';
import { HttpClient, HttpEventType } from '@angular/common/http';
import { environment } from '../../../environments/environment';
import { UploadJob, UploadResponse } from '../../shared/models';

@Injectable({ providedIn: 'root' })
export class UploadService {
  private readonly http = inject(HttpClient);
  readonly queue = signal<UploadJob[]>([]);

  upload(file: File): void {
    const job: UploadJob = {
      id: crypto.randomUUID(),
      name: file.name,
      size: file.size,
      pct: 0,
      status: 'uploading',
    };
    this.queue.update(q => [...q, job]);

    const form = new FormData();
    form.append('file', file);

    this.http.post<UploadResponse>(`${environment.apiUrl}/upload`, form, {
      reportProgress: true,
      observe: 'events',
    }).subscribe({
      next: event => {
        if (event.type === HttpEventType.UploadProgress && event.total) {
          const pct = Math.round(100 * event.loaded / event.total);
          this._update(job.id, { pct });
        } else if (event.type === HttpEventType.Response && event.body) {
          this._update(job.id, { pct: 100, status: 'done', sessionId: event.body.session_id });
        }
      },
      error: err => {
        const msg = err?.error?.detail ?? '上傳失敗';
        this._update(job.id, { status: 'error', errorMsg: msg });
      },
    });
  }

  removeJob(id: string): void {
    this.queue.update(q => q.filter(j => j.id !== id));
  }

  private _update(id: string, patch: Partial<UploadJob>): void {
    this.queue.update(q => q.map(j => j.id === id ? { ...j, ...patch } : j));
  }
}
