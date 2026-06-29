import { Component, inject, computed, signal, OnInit } from '@angular/core';
import { RouterLink } from '@angular/router';
import { HttpClient } from '@angular/common/http';
import { AuthService } from '../../core/services/auth.service';
import { environment } from '../../../environments/environment';

interface DashboardStats {
  pending_count: number;
  processing_count: number;
  doc_count: number;
  member_count: number | null;
}

@Component({
  selector: 'app-hub',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './hub.component.html',
  styleUrl: './hub.component.scss',
})
export class HubComponent implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly http = inject(HttpClient);

  readonly isAdmin = this.auth.isAdmin;
  readonly isSuperAdmin = this.auth.isSuperAdmin;
  readonly role = computed(() => this.auth.currentUser()?.role?.toUpperCase() ?? '');
  readonly displayName = computed(() =>
    this.auth.currentUser()?.company_name ??
    this.auth.currentUser()?.email?.split('@')[0] ??
    '訪客'
  );

  // ── Stats signals ──────────────────────────────────────────────────────
  readonly stats = signal<DashboardStats | null>(null);
  readonly statsLoading = signal(true);

  readonly pendingCount = computed(() => this.stats()?.pending_count ?? 0);
  readonly processingCount = computed(() => this.stats()?.processing_count ?? 0);
  readonly docCount = computed(() => this.stats()?.doc_count ?? 0);
  readonly memberCount = computed(() => this.stats()?.member_count ?? null);

  // ── Time helpers ───────────────────────────────────────────────────────
  readonly greet = computed(() => {
    const h = new Date().getHours();
    if (h < 6) return '深夜好';
    if (h < 12) return '早安';
    if (h < 18) return '午安';
    return '晚安';
  });

  readonly now = computed(() => {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  });

  // ── Cards（meta 改用真實數字）─────────────────────────────────────────
  readonly cards = computed(() => {
    const pending = this.pendingCount();
    const members = this.memberCount();
    const isSuper = this.isSuperAdmin();

    const base: Array<{
      key: string; n: string; title: string; sub: string;
      desc: string; meta: string; action: string; go: string; kind: string;
    }> = [];

      if (isSuper) {
        base.push({
          key: 'flow', n: '0', title: '三步驟流程', sub: '上傳 → 預覽 → 入向量',
          desc: '把 PDF / Word / CAD 工檔交給模型解析，審視確認後進入知識庫。',
          meta: pending > 0 ? `待確認 ${pending} 份` : '目前無待確認文件',
          action: '進入流程', go: '/upload', kind: 'rust',
        });
      }

      base.push({
        key: 'chat', n: '0', title: '對話', sub: '問你的知識庫',
        desc: '用自然語言提問，得到附上引用來源、可追溯原文的回答。',
        meta: `${this.docCount()} 個知識片段`,
        action: '開始對話', go: '/chat', kind: 'ink',
      });

      if (isSuper) {
        base.push({
          key: 'admin', n: '0', title: 'Sessions', sub: '文件處理紀錄',
          desc: '管理所有上傳 Session，審視 pending_preview 文件，執行確認或拒絕。',
          meta: pending > 0 ? `待確認 ${pending} 份` : '目前無待確認',
          action: '管理 Sessions', go: '/admin/sessions', kind: 'teal',
        });
      }

      if (this.isAdmin()) {
        base.push({
          key: 'users', n: '0', title: '使用者', sub: '人員 · 角色 · 權限',
          desc: '邀請成員、指派角色（company_admin / field_user）、管理存取權。',
          meta: members !== null ? `${members} 名成員` : '— 名成員',
          action: '管理使用者', go: '/admin/users', kind: 'mute',
        });
      }
    

    return base;
  });

  // ── Tips（依角色顯示；編號在 template 用 $index 連續重排）──────────────
  // 三步驟流程僅 superadmin 可進入，故該條提示只對 superadmin 顯示，
  // 避免 company_admin / field_user 看到無法使用的功能說明。
  readonly tips = computed(() => {
    const list: string[] = [
      '每個功能在 Header 都有對應的 tab，可以隨時切換而不會中斷目前的編輯。',
    ];
    if (this.isSuperAdmin()) {
      list.push('「三步驟流程」可以暫停、之後從預覽頁繼續，未確認的文件不會進入向量庫。');
    }
    list.push('所有對話都記錄在稽核中，並能追溯到引用的原文段落（Phase 3 開放）。');
    return list;
  });

  // ── Lifecycle ──────────────────────────────────────────────────────────
  ngOnInit(): void {
    this.loadStats();
  }

  private loadStats(): void {
    if (!this.auth.isLoggedIn()) {
      this.statsLoading.set(false);
      return;
    }

    this.http
      .get<DashboardStats>(`${environment.apiUrl}/dashboard/stats`)
      .subscribe({
        next: (data) => {
          this.stats.set(data);
          this.statsLoading.set(false);
        },
        error: () => {
          // 載入失敗 → 顯示 — 不崩壞畫面
          this.statsLoading.set(false);
        },
      });
  }
}
