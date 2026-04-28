import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../../core/auth/auth.service';
import { ToastService } from '../../../core/notifications/toast.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule],
  styles: [`
    .login-wrap {
      min-height: 100vh; display: grid;
      grid-template-columns: 1.15fr 1fr;
      gap: 32px; padding: 60px;
      background: var(--bg); position: relative; overflow: hidden;
      align-items: stretch;
    }
    .login-bg-grid {
      position: absolute; inset: 0;
      background:
        linear-gradient(var(--ink) 1px, transparent 1px) 0 0/40px 40px,
        linear-gradient(90deg, var(--ink) 1px, transparent 1px) 0 0/40px 40px;
      opacity: .05; pointer-events: none;
    }
    .login-corner {
      position: absolute; padding: 18px 22px;
      display: flex; flex-direction: column; gap: 4px;
      z-index: 2; pointer-events: none;
    }
    .login-corner.tl { top: 0; left: 0; }
    .login-corner.tr { top: 0; right: 0; text-align: right; align-items: flex-end; }
    .login-corner.bl { bottom: 0; left: 0; }
    .login-corner.br { bottom: 0; right: 0; text-align: right; align-items: flex-end; }

    .login-hero {
      position: relative; z-index: 1;
      background: var(--bg-2);
      border: 2px solid var(--ink);
      box-shadow: 8px 8px 0 var(--ink);
      padding: 40px 44px;
      display: flex; flex-direction: column; justify-content: space-between; gap: 28px;
      min-height: 560px;
    }
    .login-hero::before {
      content: "SKVALVES · INTERNAL";
      position: absolute; top: -12px; left: 24px;
      background: var(--ink); color: var(--cream);
      font-family: var(--font-mono); font-size: 10px; font-weight: 700;
      letter-spacing: .18em; padding: 3px 10px; text-transform: uppercase;
    }
    .brand-dot.xl {
      width: 48px; height: 48px; background: var(--ink); position: relative; flex-shrink: 0;
      box-shadow: inset 0 0 0 8px var(--cream), inset 0 0 0 12px var(--rust), 4px 4px 0 var(--rust);
    }
    .brand-row.big { display: flex; gap: 16px; align-items: flex-start; }
    .hero-h1 {
      font-family: var(--font-mono); font-weight: 700;
      font-size: clamp(38px, 4.6vw, 64px);
      line-height: 1; letter-spacing: -.02em; color: var(--ink); margin: 0;
    }
    .hero-h1 em {
      font-style: normal; color: var(--rust); background: var(--cream);
      padding: 0 10px; border: 2px solid var(--rust); box-shadow: 4px 4px 0 var(--ink);
      display: inline-block; transform: rotate(-1.5deg); margin: 0 4px;
    }
    .hero-h1 .emph {
      color: var(--cream); background: var(--ink);
      padding: 0 12px; border: 2px solid var(--ink); box-shadow: 5px 5px 0 var(--rust);
      display: inline-block; transform: rotate(1deg);
    }
    .hero-foot { display: flex; gap: 8px; flex-wrap: wrap; }

    .login-form-col { position: relative; z-index: 1; display: flex; align-items: stretch; }
    .px-frame {
      position: relative; background: var(--bg-2); border: 2px solid var(--ink);
      padding: 30px 32px 28px; box-shadow: 8px 8px 0 var(--rust);
      width: 100%; display: flex; flex-direction: column; min-height: 560px; justify-content: center;
    }
    .px-frame-stamp {
      position: absolute; top: -12px; left: 24px;
      background: var(--ink); color: var(--cream);
      font-family: var(--font-mono); font-size: 10px; font-weight: 600; letter-spacing: .16em;
      padding: 3px 10px; text-transform: uppercase;
    }
    .login-grid { display: flex; flex-direction: column; gap: 14px; }
    .login-grid .field { margin: 0; }
    .login-grid .field input {
      width: 100%; padding: 10px 12px; font-size: 13px;
      border: 1px solid var(--ink); background: var(--bg-2);
      box-shadow: inset 2px 2px 0 rgba(40,61,59,.06);
      font-family: var(--font-mono);
    }
    .login-grid .field input:focus {
      border-color: var(--rust); outline: none; box-shadow: 0 0 0 2px var(--rust);
    }
    .login-hint { display: flex; flex-direction: column; gap: 4px; font-family: var(--font-mono); font-size: 11.5px; color: var(--ink); }
    .login-hint .px-label { display: inline-block; margin: 0 6px 0 0; color: var(--rust); }
    .login-foot {
      margin-top: 18px; text-align: center;
      font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .18em; color: var(--muted);
      text-transform: uppercase; display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;
    }
    @media (max-width: 880px) {
      .login-wrap { grid-template-columns: 1fr; padding: 60px 24px; }
      .login-corner { display: none; }
    }
  `],
  template: `
    <div class="login-wrap">
      <div class="login-bg-grid"></div>

      <div class="login-corner tl">
        <div class="px-mono" style="font-size:10px;letter-spacing:.2em">SYS / public-llm</div>
        <div class="px-mono" style="font-size:10px;letter-spacing:.2em;color:var(--muted)">v4.0.0 · build 2026.04</div>
      </div>
      <div class="login-corner tr">
        <div class="px-mono" style="font-size:10px;letter-spacing:.2em;color:var(--muted)">STATUS</div>
        <div class="px-mono" style="font-size:10px;letter-spacing:.2em;color:var(--teal)">▣ SECURE</div>
      </div>
      <div class="login-corner bl">
        <div class="px-mono" style="font-size:10px;letter-spacing:.2em;color:var(--muted)">SOC2 · ISO27001</div>
      </div>
      <div class="login-corner br">
        <div class="px-mono" style="font-size:10px;letter-spacing:.2em;color:var(--muted)">RoHS · REACH</div>
      </div>

      <!-- Left hero -->
      <div class="login-hero">
        <div class="brand-row big">
          <div class="brand-dot xl"></div>
          <div>
            <div class="px-section-num" style="border-top:0;font-size:10px">SYS / 01</div>
            <div class="px-mono" style="font-size:11px;letter-spacing:.2em;color:var(--muted);margin-top:6px">INTERNAL · MULTI-TENANT LLM</div>
          </div>
        </div>
        <h1 class="hero-h1">
          把公司的<em>知識</em><br/>
          變成隨手可問的<br/>
          <span class="emph">同事</span>
        </h1>
        <div class="hero-foot">
          <span class="px-stamp">RAG 知識庫</span>
          <span class="px-stamp">多租戶資料隔離</span>
          <span class="px-stamp">流向可審計</span>
        </div>
      </div>

      <!-- Right form -->
      <div class="login-form-col">
        <div class="px-frame">
          <div class="px-frame-stamp">SIGN IN · 01</div>
          <h2 class="px-mono" style="font-size:22px;font-weight:700;margin:6px 0 2px">登入</h2>
          <p class="px-tag-small" style="margin-bottom:14px">USE YOUR COMPANY E-MAIL</p>

          <div class="px-rule"></div>

          <form (ngSubmit)="onSubmit()" class="login-grid" autocomplete="off">
            <label class="field">
              <span class="px-label">// EMAIL</span>
              <input type="email" [(ngModel)]="email" name="email" placeholder="you@company.com" required />
            </label>
            <label class="field">
              <span class="px-label">// PASSWORD</span>
              <input type="password" [(ngModel)]="password" name="password" placeholder="••••••••" required />
            </label>
            <button class="btn rust px-btn" type="submit" [disabled]="loading()">
              {{ loading() ? '登入中…' : '[ 登入 ▸ ]' }}
            </button>
          </form>

          <div class="px-rule"></div>

          @if (errorMsg()) {
            <div style="color:var(--rust);font-family:var(--font-mono);font-size:12px;margin-bottom:10px">
              ⚠ {{ errorMsg() }}
            </div>
          }
        </div>
      </div>
    </div>
  `,
})
export class LoginComponent {
  private readonly auth   = inject(AuthService);
  private readonly router = inject(Router);
  private readonly toast  = inject(ToastService);

  email    = '';
  password = '';
  loading  = signal(false);
  errorMsg = signal('');

  async onSubmit(): Promise<void> {
    if (!this.email || !this.password) return;
    this.loading.set(true);
    this.errorMsg.set('');
    try {
      await this.auth.login(this.email, this.password);
      this.toast.success(`歡迎回來！`);
      this.router.navigate(['/hub']);
    } catch (err: any) {
      const msg = err?.error?.detail ?? '帳號或密碼錯誤';
      this.errorMsg.set(msg);
    } finally {
      this.loading.set(false);
    }
  }
}
