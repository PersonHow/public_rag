import { Component, signal, ElementRef, ViewChild, AfterViewChecked, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../../environments/environment';
import { PageHeadComponent } from '../../shared/ui/page-head/page-head.component';

interface SourceItem {
  doc_filename: string;
  chunk_context: string;
  score: number;
  code_download_url: string | null;
}

interface QueryResponse {
  answer: string;
  sources: SourceItem[];
  elapsed_ms: number;
}

interface Message {
  id: number;
  role: 'user' | 'bot';
  text: string;
  sources?: SourceItem[];
  typing?: boolean;
}

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [FormsModule, PageHeadComponent],
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
})
export class ChatComponent implements AfterViewChecked {
  private readonly http = inject(HttpClient);

  @ViewChild('msgBox') msgBox!: ElementRef<HTMLDivElement>;

  private _idCounter = 0;
  readonly messages  = signal<Message[]>([
    { id: ++this._idCounter, role: 'bot', text: '您好！請問想查詢什麼加工參數、品質標準或工序規範？' },
  ]);
  readonly botTyping = signal(false);
  inputText = '';

  ngAfterViewChecked(): void {
    this._scrollToBottom();
  }

  async send(): Promise<void> {
    const text = this.inputText.trim();
    if (!text || this.botTyping()) return;
    this.inputText = '';

    this.messages.update(m => [...m, { id: ++this._idCounter, role: 'user', text }]);
    this.botTyping.set(true);

    const typingId = ++this._idCounter;
    this.messages.update(m => [...m, { id: typingId, role: 'bot', text: '', typing: true }]);

    try {
      const res = await firstValueFrom(
        this.http.post<QueryResponse>(`${environment.apiUrl}/query`, { question: text, top_k: 5 })
      );
      this.messages.update(m =>
        m.map(msg => msg.id === typingId
          ? { ...msg, text: res.answer, typing: false, sources: res.sources }
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

  private _scrollToBottom(): void {
    try {
      const el = this.msgBox?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    } catch {}
  }
}
