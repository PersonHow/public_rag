import { Component, inject, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { AuthService } from '../../core/auth/auth.service';

@Component({
  selector: 'app-hub',
  standalone: true,
  imports: [RouterLink],
  templateUrl: './hub.component.html',
  styleUrl: './hub.component.scss',
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
