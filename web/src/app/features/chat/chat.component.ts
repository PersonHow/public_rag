import { Component, signal, ElementRef, ViewChild, AfterViewChecked } from '@angular/core';
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
  templateUrl: './chat.component.html',
  styleUrl: './chat.component.scss',
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
