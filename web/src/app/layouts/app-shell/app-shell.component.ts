import { Component, inject, computed, OnInit } from '@angular/core';
import { RouterOutlet, RouterLink, RouterLinkActive } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../core/services/auth.service';
import { CompanyContextService } from '../../core/services/company-context.service';
import { ButtonComponent } from '../../shared/components/button/button.component';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, FormsModule, ButtonComponent],
  templateUrl: './app-shell.component.html',
  styleUrl: './app-shell.component.scss',
})
export class AppShellComponent implements OnInit {
  private readonly auth = inject(AuthService);
  readonly ctx = inject(CompanyContextService);

  readonly isAdmin = this.auth.isAdmin;
  readonly isSuperAdmin = this.auth.isSuperAdmin;
  readonly email = computed(() => this.auth.currentUser()?.email ?? '—');
  readonly role = computed(() => this.auth.currentUser()?.role ?? '');
  readonly companyId = computed(() => this.auth.currentUser()?.company_id ?? '—');
  readonly companyName = computed(() => this.auth.currentUser()?.company_name ?? this.auth.currentUser()?.company_id ?? '—');
  readonly avatarChar = computed(() => (this.auth.currentUser()?.email?.[0] ?? '?').toUpperCase());

  readonly headerSelected = computed(() => {

    const isSuper = this.isSuperAdmin();
    const isAdmin = this.isAdmin();

    const selected: Array<{
      sectionNum: string; title: string; go: string
    }> = [];

    if (isSuper) {
      selected.push({
        sectionNum: '0', title: '三步驟流程', go: '/upload'
      })
    }

    selected.push({
      sectionNum: '0', title: '對話', go: '/chat'
    })

    if (isSuper) {
      selected.push({
        sectionNum: '0', title: 'Sessions', go: '/admin/sessions'
      })
    }
    
    if (isAdmin){
      selected.push({
        sectionNum: '0', title: '使用者', go: '/admin/users'
      })
    }

    if (isSuper) {
      selected.push({
        sectionNum: '0', title: '租戶', go: '/admin/companies'
      })
    }

    return selected;
  });

  async ngOnInit(): Promise<void> {
    // 先確認 cookie session 仍有效，避免 sessionStorage 有身分但 token 已過期的卡住狀態
    await this.auth.validateSession();
    if (this.isSuperAdmin()) {
      await this.ctx.loadCompanies();
    }
  }

  onCompanyChange(value: string): void {
    this.ctx.select(value || null);
  }

  logout(): void { this.auth.logout(); }
}
