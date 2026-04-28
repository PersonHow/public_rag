import { Component, inject, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-hub',
  standalone: true,
  imports: [RouterLink],
  styles: [`
    .hub-greet {
      font-family: var(--font-mono); font-weight: 700;
      font-size: clamp(36px, 4.5vw, 56px);
      line-height: 1; letter-spacing: -.02em; color: var(--ink); margin: 14px 0 12px;
    }
    .hub-greet .emph {
      color: var(--cream); background: var(--ink);
      padding: 0 12px; border: 2px solid var(--ink); box-shadow: 5px 5px 0 var(--rust);
      display: inline-block; transform: rotate(-1deg); font-style: normal;
    }
    .hub-head { display: grid; grid-template-columns: 1.4fr 1fr; gap: 32px; align-items: end; margin-bottom: 18px; }
    .hub-sub { font-family: var(--font-mono); font-size: 11.5px; color: var(--ink); display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 0; }
    .hub-sub strong { font-weight: 700; color: var(--rust); }
    .hub-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .hub-stat { background: var(--bg-2); border: 2px solid var(--ink); box-shadow: 4px 4px 0 var(--ink); padding: 14px 16px; display: flex; flex-direction: column; gap: 6px; }

    .hub-section-head { display: flex; align-items: baseline; gap: 14px; margin: 8px 0 16px; flex-wrap: wrap; }
    .hub-section-title { font-family: var(--font-mono); font-weight: 700; font-size: 22px; letter-spacing: -.005em; color: var(--ink); margin: 0; }
    .hub-section-meta { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: .18em; color: var(--muted); text-transform: uppercase; margin-left: auto; }

    .hub-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 18px; margin-bottom: 32px; }
    .hub-grid-4 { grid-template-columns: repeat(4, 1fr); }

    .hub-card {
      background: var(--bg-2); border: 2px solid var(--ink);
      box-shadow: 6px 6px 0 var(--ink);
      padding: 22px; display: flex; flex-direction: column; gap: 10px;
      text-align: left; cursor: pointer; color: var(--ink); text-decoration: none;
      transition: transform .08s, box-shadow .08s;
      position: relative; min-height: 240px;
    }
    .hub-card:hover { transform: translate(-2px,-2px); box-shadow: 8px 8px 0 var(--ink); }
    .hub-card:active { transform: translate(2px,2px); box-shadow: 2px 2px 0 var(--ink); }
    .hub-rust { box-shadow: 6px 6px 0 var(--rust); background: linear-gradient(180deg, var(--bg-2) 0%, var(--cream) 100%); }
    .hub-rust:hover { box-shadow: 8px 8px 0 var(--rust); }
    .hub-ink { box-shadow: 6px 6px 0 var(--rust); background: var(--ink); color: var(--cream); }
    .hub-ink:hover { box-shadow: 8px 8px 0 var(--rust); }
    .hub-teal { box-shadow: 6px 6px 0 var(--teal); }
    .hub-teal:hover { box-shadow: 8px 8px 0 var(--teal); }

    .hub-card-top { display: flex; justify-content: space-between; align-items: center; }
    .hub-card-title { font-family: var(--font-mono); font-weight: 700; font-size: 26px; letter-spacing: -.01em; line-height: 1.1; margin-top: 4px; }
    .hub-card-sub { font-family: var(--font-mono); font-size: 11.5px; letter-spacing: .12em; color: var(--muted); text-transform: uppercase; }
    .hub-ink .hub-card-sub { color: rgba(237,221,212,.7); }
    .hub-card-desc { font-size: 13px; line-height: 1.55; color: var(--ink); flex: 1; border-top: 1.5px dashed var(--ink); padding-top: 10px; margin-top: 6px; }
    .hub-ink .hub-card-desc { color: rgba(237,221,212,.85); border-top-color: rgba(237,221,212,.4); }
    .hub-card-foot { display: flex; justify-content: space-between; align-items: flex-end; margin-top: auto; padding-top: 8px; gap: 12px; flex-wrap: wrap; }
    .hub-card-meta { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: .06em; color: var(--muted); }
    .hub-ink .hub-card-meta { color: rgba(237,221,212,.6); }
    .hub-card-cta {
      font-family: var(--font-mono); font-weight: 700; font-size: 11.5px;
      letter-spacing: .08em; text-transform: uppercase;
      background: var(--ink); color: var(--cream);
      padding: 6px 12px; border: 1.5px solid var(--ink); box-shadow: 2px 2px 0 var(--rust);
    }
    .hub-ink .hub-card-cta { background: var(--rust); box-shadow: 2px 2px 0 var(--cream); }

    .hub-tips { display: grid; grid-template-columns: repeat(3,1fr); gap: 14px; border-top: 2px dashed var(--ink); padding-top: 24px; }
    .hub-tip { display: flex; flex-direction: column; gap: 8px; }
    .hub-tip p { margin: 0; font-size: 12.5px; line-height: 1.55; color: var(--ink); }

    @media (max-width: 1100px) { .hub-grid-4 { grid-template-columns: repeat(2,1fr); } }
    @media (max-width: 880px) { .hub-head { grid-template-columns: 1fr; } .hub-tips { grid-template-columns: 1fr; } }
    @media (max-width: 680px) { .hub-grid, .hub-grid-4 { grid-template-columns: 1fr; } }
  `],
  template: `
    <div class="hub-head">
      <div>
        <span class="px-stamp rust">PUBLIC_LLM · v4.0.0</span>
        <h1 class="hub-greet">{{ greet() }}，<span class="emph">{{ displayName() }}</span></h1>
        <p class="hub-sub">
          <span class="px-label" style="display:inline">// ROLE</span>
          <strong>{{ role() }}</strong>
          <span style="color:var(--muted)">·</span>
          <span class="px-label" style="display:inline">// SESSION</span>
          <strong>{{ now() }}</strong>
        </p>
      </div>
      <div class="hub-stats">
        <div class="hub-stat">
          <div class="px-bignum rust">2</div>
          <div class="px-label">待確認</div>
        </div>
        <div class="hub-stat">
          <div class="px-bignum">—</div>
          <div class="px-label">處理中</div>
        </div>
        <div class="hub-stat">
          <div class="px-bignum teal">—</div>
          <div class="px-label">知識庫文件</div>
        </div>
      </div>
    </div>

    <div class="px-rule"></div>

    <div class="hub-section-head">
      <span class="px-section-num">SELECT / 0{{ cards().length }}</span>
      <h2 class="hub-section-title">選擇要進入的功能</h2>
      <span class="hub-section-meta">{{ isAdmin() ? 'ADMIN VIEW' : 'MEMBER VIEW' }}</span>
    </div>

    <div class="hub-grid" [class.hub-grid-4]="cards().length === 4">
      @for (c of cards(); track c.key) {
        <a class="hub-card hub-{{ c.kind }}" [routerLink]="c.go">
          <div class="hub-card-top">
            <span class="px-section-num">{{ c.n }} / 0{{ cards().length }}</span>
          </div>
          <div class="hub-card-title">{{ c.title }}</div>
          <div class="hub-card-sub">{{ c.sub }}</div>
          <div class="hub-card-desc">{{ c.desc }}</div>
          <div class="hub-card-foot">
            <span class="hub-card-meta">{{ c.meta }}</span>
            <span class="hub-card-cta">{{ c.action }} ▸</span>
          </div>
        </a>
      }
    </div>

    <div class="hub-tips">
      <div class="hub-tip">
        <span class="px-stamp">TIP / 01</span>
        <p>每個功能在 Header 都有對應的 tab，可以隨時切換而不會中斷目前的編輯。</p>
      </div>
      <div class="hub-tip">
        <span class="px-stamp">TIP / 02</span>
        <p>「三步驟流程」可以暫停、之後從預覽頁繼續，未確認的文件不會進入向量庫。</p>
      </div>
      <div class="hub-tip">
        <span class="px-stamp">TIP / 03</span>
        <p>所有對話都記錄在稽核中，並能追溯到引用的原文段落（Phase 3 開放）。</p>
      </div>
    </div>
  `,
})
export class HubComponent {
  private readonly auth = inject(AuthService);

  readonly isAdmin = this.auth.isAdmin;
  readonly role    = computed(() => this.auth.currentUser()?.role?.toUpperCase() ?? '');
  readonly displayName = computed(() => this.auth.currentUser()?.email?.split('@')[0] ?? '訪客');

  readonly greet = computed(() => {
    const h = new Date().getHours();
    if (h < 6) return '深夜好';
    if (h < 12) return '早安';
    if (h < 18) return '午安';
    return '晚安';
  });

  readonly now = computed(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;
  });

  readonly cards = computed(() => {
    const base = [
      {
        key: 'flow', n: '01', title: '三步驟流程', sub: '上傳 → 預覽 → 入向量',
        desc: '把 PDF / Word / CAD 工檔交給模型解析，審視確認後進入知識庫。',
        meta: '待確認 2 份', action: '進入流程', go: '/upload', kind: 'rust',
      },
      {
        key: 'chat', n: '02', title: '對話', sub: '問你的知識庫',
        desc: '用自然語言提問，得到附上引用來源、可追溯原文的回答。',
        meta: '— 則對話', action: '開始對話', go: '/chat', kind: 'ink',
      },
    ];
    if (this.isAdmin()) {
      base.push(
        {
          key: 'admin', n: '03', title: 'Sessions', sub: '文件處理紀錄',
          desc: '管理所有上傳 Session，審視 pending_preview 文件，執行確認或拒絕。',
          meta: '待確認 2 份', action: '管理 Sessions', go: '/admin', kind: 'teal',
        },
        {
          key: 'users', n: '04', title: '使用者', sub: '人員 · 角色 · 權限',
          desc: '邀請成員、指派角色（company_admin / field_user）、管理存取權。',
          meta: '— 名成員', action: '管理使用者', go: '/admin/users', kind: 'mute',
        },
      );
    }
    return base;
  });
}
