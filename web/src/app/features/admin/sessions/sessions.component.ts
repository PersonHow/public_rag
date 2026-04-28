import { Component, inject, signal, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { RouterLink } from '@angular/router';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { SessionStatusResponse } from '../../../core/models';
import { ToastService } from '../../../core/notifications/toast.service';

@Component({
  selector: 'app-admin-sessions',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './sessions.component.html',
  styleUrl: './sessions.component.scss',
})
export class AdminSessionsComponent implements OnInit {
  private readonly http  = inject(HttpClient);
  private readonly toast = inject(ToastService);

  readonly sessions    = signal<SessionStatusResponse[]>([]);
  readonly loading     = signal(false);
  readonly apiError    = signal<string | null>(null);
  readonly pendingCount = () => this.sessions().filter(s => s.status === 'pending_preview').length;

  ngOnInit(): void { this.load(); }

  async load(): Promise<void> {
    this.loading.set(true);
    this.apiError.set(null);
    try {
      const res = await firstValueFrom(
        this.http.get<SessionStatusResponse[]>(`${environment.apiUrl}/sessions`)
      );
      this.sessions.set(Array.isArray(res) ? res : []);
    } catch (e: any) {
      const detail = e?.error?.detail ?? e?.message ?? '無法載入';
      this.apiError.set(detail);
      this.sessions.set([]);
    } finally {
      this.loading.set(false);
    }
  }
}
