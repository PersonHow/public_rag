import { Component, signal, ElementRef, ViewChild, AfterViewChecked, inject, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { PageHeadComponent } from '../../shared/components/page-head/page-head.component';
import { ButtonComponent } from '../../shared/components/button/button.component';
import { AuthService } from '../../core/services/auth.service';
import { CompanyContextService } from '../../core/services/company-context.service';

interface SourceItem {
  doc_filename: string;
  chunk_context: string;
  score: number;
  code_download_url: string | null;
  code_filename: string | null;
}

interface QueryResponse {
  answer: string;
  sources: SourceItem[];
  elapsed_ms: number;
}

interface DownloadItem {
  filename: string;
  url: string;
}

interface Message {
  id: number;
  role: 'user' | 'bot';
  text: string;
  downloads?: DownloadItem[];
  typing?: boolean;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [FormsModule, PageHeadComponent, ButtonComponent],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
})
export class ChatComponent implements AfterViewChecked {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly ctx  = inject(CompanyContextService);

  @ViewChild('msgBox') msgBox!: ElementRef<HTMLDivElement>;

  readonly isSuperAdmin     = this.auth.isSuperAdmin;
  readonly activeCompanyId  = this.ctx.activeCompanyId;
  readonly activeCompany    = this.ctx.activeCompany;

  // superadmin 已選租戶時顯示租戶名，否則提示需選擇
  readonly tenantHint = computed(() => {
    if (!this.isSuperAdmin()) return null;
    const co = this.activeCompany();
    return co ? co.name : null;
  });

  private _idCounter = 0;
  readonly messages  = signal<Message[]>([
    { id: ++this._idCounter, role: 'bot', text: '您好！請問想查詢什麼建議工法、品質標準或工序規範？' },
  ]);
  readonly botTyping = signal(false);
  inputText = '';

  ngAfterViewChecked(): void {
    this._scrollToBottom();
  }

  async send(): Promise<void> {
    const text = this.inputText.trim();
    if (!text || this.botTyping()) return;

    // superadmin 必須先在頂部選擇租戶
    if (this.isSuperAdmin() && !this.activeCompanyId()) {
      this.messages.update(m => [...m, {
        id: ++this._idCounter,
        role: 'bot',
        text: '⚠️ 請先在頂部選擇要查詢的租戶（TENANT 下拉選單）。',
      }]);
      return;
    }

    this.inputText = '';
    this.messages.update(m => [...m, { id: ++this._idCounter, role: 'user', text }]);
    this.botTyping.set(true);

    const typingId = ++this._idCounter;
    this.messages.update(m => [...m, { id: typingId, role: 'bot', text: '', typing: true }]);

    try {
      // superadmin 帶 ?company_id= query param；其他角色 company_id 從 JWT 取，不需帶
      const url = this.isSuperAdmin()
        ? `${environment.apiUrl}/query?company_id=${this.activeCompanyId()}`
        : `${environment.apiUrl}/query`;

      // 近幾輪對話（排除打字中與初始問候），供後端把追問補成獨立問句
      const history = this.messages()
        .filter(m => !m.typing && m.text)
        .slice(-7, -1)            // 不含剛 push 進去的本次提問
        .map(m => ({ role: m.role === 'user' ? 'user' : 'bot', text: m.text }));

      const res = await firstValueFrom(
        this.http.post<QueryResponse>(url, { question: text, top_k: 5, history })
      );
      const downloads = this._extractDownloads(res.sources);
      this.messages.update(m =>
        m.map(msg => msg.id === typingId
          ? { ...msg, text: res.answer, typing: false, downloads }
          : msg
        )
      );
    } catch {
      this.messages.update(m =>
        m.map(msg => msg.id === typingId
          ? { ...msg, text: '查詢失敗，請確認登入狀態或稍後再試。', typing: false }
          : msg
        )
      );
    } finally {
      this.botTyping.set(false);
    }
  }

  onEnter(event: Event): void {
    if (!(event as KeyboardEvent).shiftKey) {
      event.preventDefault();
      this.send();
    }
  }

  // 只取「真的能下載」的 TAP/NC 程式檔，依檔名去重（同產品多 chunk 會重複）
  private _extractDownloads(sources: SourceItem[]): DownloadItem[] {
    const seen = new Set<string>();
    const out: DownloadItem[] = [];
    for (const s of sources ?? []) {
      if (!s.code_download_url || !s.code_filename) continue;
      if (seen.has(s.code_filename)) continue;
      seen.add(s.code_filename);
      out.push({ filename: s.code_filename, url: s.code_download_url });
    }
    return out;
  }

  private _scrollToBottom(): void {
    try {
      const el = this.msgBox?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    } catch {}
  }
}
