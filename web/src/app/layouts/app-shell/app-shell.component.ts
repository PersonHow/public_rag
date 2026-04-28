import { Component, inject, computed } from '@angular/core';
import { RouterOutlet, Router, RouterLink, RouterLinkActive } from '@angular/router';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  templateUrl: './app-shell.component.html',
  styleUrl: './app-shell.component.scss',
})
export class AppShellComponent {
  private readonly auth   = inject(AuthService);
  private readonly router = inject(Router);

  readonly isAdmin    = this.auth.isAdmin;
  readonly email      = computed(() => this.auth.currentUser()?.email ?? '—');
  readonly role       = computed(() => this.auth.currentUser()?.role ?? '');
  readonly companyId  = computed(() => this.auth.currentUser()?.company_id ?? '—');
  readonly avatarChar = computed(() => (this.auth.currentUser()?.email?.[0] ?? '?').toUpperCase());

  logout(): void { this.auth.logout(); }
}
