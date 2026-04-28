import { Component, signal, computed, ElementRef, ViewChild, AfterViewChecked } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface Message {
  id: number;
  role: 'user' | 'bot';
  text: string;
  citations?: string[];
  typing?: boolean;
}

const MOCK_RESPONSES: Array<{ trigger: RegExp; answer: string; citations: string[] }> = [
  {
    trigger: /TM-7842|後座墊/,
    answer: 'TM-7842 後座墊組件採用射出成型工法，材料為 ABS PA-757。一般工差 ±0.05 mm，關鍵點 ±0.02 mm。尺寸 240×165×38 mm，重量 215 g。已通過 RoHS 與 REACH 認證。',
    citations: ['TM-7842 主規格', '工差控制', '認證與測試'],
  },
  {
    trigger: /採購|簽核|PO/,
    answer: '單筆超過 50,000 NTD 的採購需經部門主管與財務長雙重簽核。新供應商須填寫 CGS-04 審查表，約 14 個工作天完成審查。',
    citations: ['簽核門檻', '新供應商審查'],
  },
  {
    trigger: /CNC|Lathe|刀具/,
    answer: 'CNC-Lathe-22 使用 T0101 外徑車刀，G96 恆表面速度模式，表面速度 180 m/min，最大主軸轉速 2400 rpm。',
    citations: ['機台與刀具 (c3-1)'],
  },
];

@Component({
  selector: 'app-chat',
  standalone: true,
  imports: [FormsModule],
  styles: [`
    :host { display: flex; flex-direction: column; height: calc(100vh - 120px); }
    .chat-wrap { display: grid; grid-template-rows: 1fr auto; flex: 1; overflow: hidden; }
    .messages { overflow: auto; padding: 8px 0; display: flex; flex-direction: column; gap: 14px; }
    .msg { display: flex; gap: 10px; max-width: 740px; }
    .msg.me { margin-left: auto; flex-direction: row-reverse; }
    .av {
      width: 30px; height: 30px; display: grid; place-items: center;
      flex-shrink: 0; font-size: 11px; font-weight: 700;
      border: 1.5px solid var(--ink); box-shadow: 2px 2px 0 var(--ink);
      font-family: var(--font-mono);
    }
    .msg.me .av { background: var(--rust); color: var(--cream); }
    .msg.bot .av { background: var(--teal); color: var(--cream); }
    .bubble {
      padding: 10px 14px; font-size: 13.5px; line-height: 1.65;
      background: var(--bg-2); border: 1.5px solid var(--ink);
      box-shadow: 3px 3px 0 var(--ink); font-family: var(--font);
    }
    .msg.me .bubble { background: var(--ink); color: var(--cream); box-shadow: 3px 3px 0 var(--rust); }
    .citations { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
    .cite {
      font-family: var(--font-mono); font-size: 11px; font-weight: 700;
      background: var(--cream); border: 1.5px solid var(--rust) !important; color: var(--rust);
      padding: 4px 10px; box-shadow: 2px 2px 0 var(--ink) !important; cursor: pointer;
      letter-spacing: .04em;
    }
    .cite:hover { background: var(--bg-2); }
    .typing-dots { display: inline-flex; gap: 3px; align-items: center; height: 14px; }
    .typing-dots span { width: 5px; height: 5px; border-radius: 50%; background: var(--muted); animation: tdot 1.2s infinite; }
    .typing-dots span:nth-child(2) { animation-delay: .15s; }
    .typing-dots span:nth-child(3) { animation-delay: .3s; }
    @keyframes tdot { 0%,80%,100%{opacity:.3;transform:translateY(0)} 40%{opacity:1;transform:translateY(-3px)} }

    .composer {
      border: 2px solid var(--ink) !important; box-shadow: 4px 4px 0 var(--ink) !important;
      background: var(--bg-2); padding: 8px; display: flex; gap: 8px;
      align-items: flex-end; margin-top: 14px;
    }
    .composer textarea {
      flex: 1; border: 0; outline: none; resize: none; font-size: 14px;
      padding: 6px 8px; min-height: 24px; max-height: 140px; background: transparent;
      color: inherit; font-family: inherit;
    }
    .mock-banner {
      background: var(--cream); border: 1.5px dashed var(--ink);
      padding: 8px 14px; margin-bottom: 14px;
      font-family: var(--font-mono); font-size: 11px; color: var(--ink);
      display: flex; align-items: center; gap: 8px;
    }
  `],
  template: `
    <div style="margin-bottom:18px">
      <span class="px-stamp rust">MOCK · PHASE 3</span>
      <h1 style="margin-top:8px;font-size:28px">對話</h1>
      <p style="color:var(--muted);font-size:13px;margin:0">詢問知識庫中的文件內容（Chat API Phase 3 後接通，現為模擬回應）</p>
    </div>

    <div class="mock-banner">
      <span class="pill rust">MOCK</span>
      目前為模擬模式，回應來自靜態資料。Phase 3 接通 <code>/chat/completions</code> 後即為真實 RAG 回答。
    </div>

    <div class="chat-wrap">
      <div class="messages" #msgBox>
        @for (msg of messages(); track msg.id) {
          <div class="msg" [class.me]="msg.role==='user'" [class.bot]="msg.role==='bot'">
            <div class="av">{{ msg.role === 'user' ? 'U' : 'AI' }}</div>
            <div>
              <div class="bubble">
                @if (msg.typing) {
                  <div class="typing-dots">
                    <span></span><span></span><span></span>
                  </div>
                } @else {
                  {{ msg.text }}
                }
              </div>
              @if (msg.citations?.length) {
                <div class="citations">
                  @for (c of msg.citations; track c) {
                    <button class="cite">§ {{ c }}</button>
                  }
                </div>
              }
            </div>
          </div>
        }
      </div>

      <div class="composer">
        <textarea [(ngModel)]="inputText" rows="1" placeholder="詢問知識庫… (Enter 送出)"
                  (keydown.enter)="onEnter($event)">
        </textarea>
        <button class="btn primary sm" (click)="send()" [disabled]="!inputText.trim() || botTyping()">
          送出 ▸
        </button>
      </div>
    </div>
  `,
})
export class ChatComponent implements AfterViewChecked {
  @ViewChild('msgBox') msgBox!: ElementRef<HTMLDivElement>;

  private _idCounter = 0;
  readonly messages  = signal<Message[]>([
    { id: ++this._idCounter, role: 'bot', text: '您好！請問想查詢什麼？可以試試詢問「TM-7842 的尺寸」或「採購簽核規定」。' },
  ]);
  readonly botTyping = signal(false);
  inputText = '';

  ngAfterViewChecked(): void {
    this._scrollToBottom();
  }

  send(): void {
    const text = this.inputText.trim();
    if (!text || this.botTyping()) return;
    this.inputText = '';

    this.messages.update(m => [...m, { id: ++this._idCounter, role: 'user', text }]);
    this.botTyping.set(true);

    const typingId = ++this._idCounter;
    this.messages.update(m => [...m, { id: typingId, role: 'bot', text: '', typing: true }]);

    setTimeout(() => {
      const found = MOCK_RESPONSES.find(r => r.trigger.test(text));
      const answer = found
        ? found.answer
        : '這個問題目前知識庫中找不到相關資料，請確認已上傳並確認相關文件。';
      const citations = found?.citations ?? [];

      this.messages.update(m =>
        m.map(msg => msg.id === typingId
          ? { ...msg, text: answer, typing: false, citations }
          : msg
        )
      );
      this.botTyping.set(false);
    }, 900 + Math.random() * 600);
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
