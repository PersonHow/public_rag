import { Component, inject, computed, OnInit } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../core/services/auth.service';
import { CompanyContextService } from '../../core/services/company-context.service';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, FormsModule],
  templateUrl: './app-shell.component.html',
  styleUrl: './app-shell.component.scss',
})
export class AppShellComponent implements OnInit {
  private readonly auth = inject(AuthService);
  readonly ctx            = inject(CompanyContextService);

  readonly isAdmin      = this.auth.isAdmin;
  readonly isSuperAdmin = this.auth.isSuperAdmin;
  readonly email        = computed(() => this.auth.currentUser()?.email ?? '—');
  readonly role         = computed(() => this.auth.currentUser()?.role ?? '');
  readonly companyId    = computed(() => this.auth.currentUser()?.company_id ?? '—');
  readonly companyName  = computed(() => this.auth.currentUser()?.company_name ?? this.auth.currentUser()?.company_id ?? '—');
  readonly avatarChar   = computed(() => (this.auth.currentUser()?.email?.[0] ?? '?').toUpperCase());
  
  

  async ngOnInit(): Promise<void> {
    if (this.isSuperAdmin()) {
      await this.ctx.loadCompanies();
    }
  }

  onCompanyChange(value: string): void {
    this.ctx.select(value || null);
  }

  logout(): void { this.auth.logout(); }
}
