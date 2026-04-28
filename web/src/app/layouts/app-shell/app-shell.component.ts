import { Component, inject, computed } from '@angular/core';
import { RouterOutlet, Router, RouterLink, RouterLinkActive } from '@angular/router';
import { NgClass } from '@angular/common';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterOutlet, NgClass, RouterLink, RouterLinkActive],
  styles: [`
    :host { display: flex; flex-direction: column; min-height: 100vh; }

    .topbar {
      height: auto; min-height: 60px; padding: 10px 22px; gap: 18px;
      background: var(--bg-2);
      border: 0; border-bottom: 2px solid var(--ink);
      box-shadow: 0 5px 0 var(--ink), 0 6px 0 var(--rust);
      background-image: repeating-linear-gradient(45deg, var(--bg-2) 0 8px, var(--bg-3) 8px 9px);
      display: flex; align-items: center; flex-wrap: wrap;
      position: sticky; top: 0; z-index: 30;
    }
    .tb-brand {
      background: transparent; border: 0; cursor: pointer;
      display: flex; align-items: center; gap: 10px; font-size: 14px;
      border-right: 1px solid var(--ink); padding: 0 18px 0 0; color: var(--ink);
      font-family: inherit;
    }
    .tb-tenant {
      display: flex; align-items: center; gap: 8px;
      border-right: 1px solid var(--ink); padding-right: 18px;
    }
    .tb-nav { display: flex; gap: 10px; flex-wrap: wrap; }
    .px-tab {
      background: transparent; border: 1.5px solid transparent;
      padding: 8px 14px; font-family: var(--font-mono); font-size: 12px; font-weight: 700;
      color: var(--ink); text-transform: uppercase; letter-spacing: .04em;
      display: flex; align-items: center; gap: 10px; cursor: pointer;
    }
    .px-tab:hover { background: var(--bg-3); border-color: var(--ink); box-shadow: 2px 2px 0 var(--ink); }
    .px-tab.active {
      background: var(--ink); color: var(--cream); border-color: var(--ink);
      box-shadow: 3px 3px 0 var(--rust);
    }
    .px-section-num.small { border-top: 0; padding-top: 0; font-size: 8.5px; color: inherit; opacity: .7; }
    .px-tab-text { display: flex; flex-direction: column; gap: 0; line-height: 1.1; }
    .tb-spacer { flex: 1; }
    .px-icon-btn {
      width: 34px; height: 34px; border: 1px solid var(--ink); background: var(--bg-2);
      display: grid; place-items: center; cursor: pointer; color: var(--ink);
      box-shadow: 2px 2px 0 var(--ink); position: relative;
    }
    .px-icon-btn:hover { background: var(--cream); transform: translate(-1px,-1px); box-shadow: 3px 3px 0 var(--ink); }
    .px-dot { position: absolute; top: 5px; right: 5px; width: 6px; height: 6px; background: var(--rust); border: 1px solid var(--ink); }
    .tb-me { display: flex; align-items: center; gap: 8px; border-left: 1px solid var(--ink); padding-left: 14px; }
    .px-avatar {
      width: 30px; height: 30px; background: var(--rust); color: var(--cream);
      display: grid; place-items: center; font-family: var(--font-mono); font-weight: 700; font-size: 12px;
      border: 1px solid var(--ink); box-shadow: 2px 2px 0 var(--ink);
    }
    .me-meta { font-size: 11px; line-height: 1.2; }
    .me-meta .nm { font-weight: 600; font-family: var(--font-mono); }
    .me-meta .rl { font-family: var(--font-mono); font-size: 9.5px; color: var(--muted); text-transform: uppercase; letter-spacing: .08em; }
    .main-content { flex: 1; overflow: auto; padding: 28px 32px 80px; max-width: 1400px; width: 100%; margin: 0 auto; }
    @media (max-width: 980px) {
      .topbar { flex-wrap: wrap; gap: 10px; }
      .tb-tenant, .tb-brand { border-right: 0; padding-right: 0; }
      .tb-nav { order: 5; width: 100%; border-top: 1px dashed var(--ink); padding-top: 8px; }
    }
    @media (max-width: 720px) { .main-content { padding: 18px; } }
  `],
  template: `
    <header class="topbar">
      <button class="tb-brand" routerLink="/hub">
        <div class="brand-dot small"></div>
        <span class="px-mono">PUBLIC_LLM</span>
        <span class="px-tag-small">v4.0</span>
      </button>

      <div class="tb-tenant">
        <span class="px-label">// TENANT</span>
        <span class="px-mono" style="font-size:12px">{{ companyId() }}</span>
      </div>

      <nav class="tb-nav">
        <a class="px-tab" routerLink="/upload" routerLinkActive="active">
          <span class="px-tab-text">
            <span class="px-section-num small">01</span>
            <span>三步驟流程</span>
          </span>
        </a>
        <a class="px-tab" routerLink="/chat" routerLinkActive="active">
          <span class="px-tab-text">
            <span class="px-section-num small">02</span>
            <span>對話</span>
          </span>
        </a>
        @if (isAdmin()) {
          <a class="px-tab" routerLink="/admin" routerLinkActive="active">
            <span class="px-tab-text">
              <span class="px-section-num small">03</span>
              <span>Sessions</span>
            </span>
          </a>
          <a class="px-tab" routerLink="/admin/users" routerLinkActive="active">
            <span class="px-tab-text">
              <span class="px-section-num small">04</span>
              <span>使用者</span>
            </span>
          </a>
        }
      </nav>

      <div class="tb-spacer"></div>

      <div class="tb-me">
        <div class="px-avatar">{{ avatarChar() }}</div>
        <div class="me-meta">
          <div class="nm">{{ email() }}</div>
          <div class="rl">{{ role() }}</div>
        </div>
        <button class="px-icon-btn" (click)="logout()" title="登出">
          <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
            <polyline points="16 17 21 12 16 7"/>
            <line x1="21" y1="12" x2="9" y2="12"/>
          </svg>
        </button>
      </div>
    </header>

    <div class="main-content">
      <router-outlet />
    </div>
  `,
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
