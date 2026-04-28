import { Component, inject, signal, OnInit } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
interface UserRow {
  user_id: string;
  email: string;
  role: string;
  is_active: boolean;
  company_id: string | null;
}

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [],
  templateUrl: './users.component.html',
  styleUrl: './users.component.scss',
})
export class AdminUsersComponent implements OnInit {
  private readonly http = inject(HttpClient);

  readonly users    = signal<UserRow[]>([]);
  readonly loading  = signal(false);
  readonly apiError = signal<string | null>(null);

  ngOnInit(): void { this.load(); }

  async load(): Promise<void> {
    this.loading.set(true);
    this.apiError.set(null);
    try {
      const res = await firstValueFrom(
        this.http.get<UserRow[]>(`${environment.apiUrl}/admin/users`)
      );
      this.users.set(Array.isArray(res) ? res : []);
    } catch (e: any) {
      this.apiError.set(e?.error?.detail ?? '無法載入使用者');
      this.users.set([]);
    } finally {
      this.loading.set(false);
    }
  }
}
