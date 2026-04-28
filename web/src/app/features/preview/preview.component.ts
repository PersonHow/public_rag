import { Component, inject, signal, Input, OnInit, OnDestroy, computed } from '@angular/core';
import { RouterLink } from '@angular/router';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';
import { PreviewService } from './services/preview.service';
import { AuthService } from '../../core/auth/auth.service';
import { ToastService } from '../../core/notifications/toast.service';
import { Chunk, Document } from '../../core/models';

@Component({
  selector: 'app-preview',
  standalone: true,
  imports: [RouterLink, FormsModule],
  styles: [`
    /* ── Doc picker ─────────────────────────────────── */
    .mv-doc-picker {
      border: 2px solid var(--ink); background: var(--bg-2);
      box-shadow: 5px 5px 0 var(--ink); padding: 12px 16px; margin-bottom: 18px;
      position: relative;
    }
    .mv-doc-picker::before {
      content: "FILES_QUEUE"; position: absolute; top: -9px; left: 18px;
      background: var(--bg-2); padding: 0 8px;
      font-family: var(--font-mono); font-size: 9px; font-weight: 700;
      letter-spacing: .2em; color: var(--ink);
    }
    .doc-list-h { display: flex; gap: 10px; overflow-x: auto; padding: 4px 0 6px; }
    .doc-item {
      flex: 0 0 auto; min-width: 220px; border: 1.5px solid var(--ink) !important;
      background: var(--bg-2); padding: 10px 12px; cursor: pointer;
      display: flex; flex-direction: column; gap: 4px; box-shadow: 3px 3px 0 var(--ink);
      transition: transform .08s, box-shadow .08s;
    }
    .doc-item:hover { transform: translate(-1px,-1px); box-shadow: 4px 4px 0 var(--ink); }
    .doc-item.active { background: var(--ink) !important; color: var(--cream); box-shadow: 3px 3px 0 var(--rust) !important; }
    .doc-item .nm { font-family: var(--font-mono); font-weight: 700; font-size: 13px; display: flex; align-items: center; gap: 6px; }
    .doc-item .det { font-family: var(--font-mono); font-size: 10.5px; letter-spacing: .04em; color: var(--muted); }
    .doc-item.active .det { color: rgba(237,221,212,.6); }
    .flag-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--rust); flex-shrink: 0; }

    /* ── Filter bar ─────────────────────────────────── */
    .filter-bar {
      display: flex; gap: 8px; align-items: center; flex-wrap: wrap;
      padding: 10px 14px; border: 1.5px solid var(--ink); background: var(--cream);
      border-bottom: 2px solid var(--ink); margin-bottom: 14px;
      box-shadow: 3px 3px 0 var(--ink);
    }
    .filter-input {
      border: 1px solid var(--ink) !important; background: var(--bg-2) !important;
      padding: 6px 10px; font-size: 12px; width: 200px;
      font-family: var(--font-mono); box-shadow: inset 2px 2px 0 var(--line-2);
    }
    .filter-input:focus { border-color: var(--rust) !important; outline: none; }

    /* ── Chunk ──────────────────────────────────────── */
    .chunks-list { display: flex; flex-direction: column; gap: 12px; }
    .chunk {
      border: 1.5px solid var(--ink) !important; box-shadow: 3px 3px 0 var(--ink);
      background: var(--bg-2); transition: box-shadow .1s, transform .1s;
    }
    .chunk:hover { transform: translate(-1px,-1px); box-shadow: 4px 4px 0 var(--ink); }
    .chunk.low { border-color: var(--rust) !important; box-shadow: 3px 3px 0 var(--rust) !important; }
    .chunk-head {
      padding: 10px 14px; display: flex; align-items: center; gap: 8px;
      border-bottom: 1px solid var(--line-2);
    }
    .chunk-name { font-family: var(--font-mono); font-weight: 700; font-size: 13.5px; }
    .chunk-id {
      font-family: var(--font-mono); font-size: 9.5px; letter-spacing: .18em;
      background: var(--ink); color: var(--cream); padding: 2px 6px; border: 1.5px solid var(--ink);
    }
    .chunk-body { padding: 10px 14px; }
    .specs { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap: 10px; }
    .spec .l { font-family: var(--font-mono); font-size: 9.5px; color: var(--muted); letter-spacing: .1em; text-transform: uppercase; font-weight: 700; display: block; margin-bottom: 2px; }
    .spec .v { font-size: 13px; font-weight: 500; word-break: break-word; }
    .spec .v.empty { color: var(--muted); font-style: italic; font-weight: 400; }
    .embed-text {
      margin-top: 10px; padding: 8px 10px; background: var(--bg-3);
      border: 1px dashed var(--ink) !important; border-left: 3px solid var(--teal) !important;
      font-family: var(--font-mono); font-size: 11.5px; line-height: 1.6; color: rgba(40,61,59,.85);
    }
    .embed-text .lab { font-size: 9.5px; color: var(--muted); letter-spacing: .1em; text-transform: uppercase; display: block; margin-bottom: 3px; }
    .chunk-group-head {
      display: flex; align-items: center; gap: 8px; padding: 14px 4px 8px;
      font-family: var(--font-mono); font-size: 10.5px; letter-spacing: .08em;
      color: var(--muted); text-transform: uppercase;
    }
    .chunk-group-head .line { flex: 1; height: 1px; background: var(--line); }

    /* ── Confirm bar ────────────────────────────────── */
    .confirm-bar {
      position: sticky; bottom: 0;
      background: var(--bg-2); border-top: 2px solid var(--ink);
      box-shadow: 0 -5px 0 var(--ink), 0 -6px 0 var(--rust);
      margin: 24px -32px -80px; padding: 14px 32px;
      display: flex; align-items: center; gap: 12px;
    }
    .confirm-bar .info { flex: 1; display: flex; align-items: center; gap: 14px; font-size: 13px; }

    /* ── Status ─────────────────────────────────────── */
    .status-bar {
      padding: 12px 16px; margin-bottom: 18px;
      border: 2px solid var(--teal); box-shadow: 3px 3px 0 var(--teal);
      font-family: var(--font-mono); font-size: 12px; font-weight: 700;
      display: flex; align-items: center; gap: 12px;
    }
    .status-bar.confirmed { border-color: var(--ink); box-shadow: 3px 3px 0 var(--ink); }
    .status-bar.failed    { border-color: var(--rust); box-shadow: 3px 3px 0 var(--rust); }
  `],
  template: `
    <!-- Stepper -->
    <div class="stepper">
      <a class="step done" routerLink="/upload">
        <span class="num">✓</span>
        <div><div class="lab">STEP 01</div><div class="name">上傳資料</div></div>
      </a>
      <div class="bar done"></div>
      <button class="step active">
        <span class="num">02</span>
        <div><div class="lab">STEP 02</div><div class="name">預覽 / 確認</div></div>
      </button>
      <div class="bar" [class.done]="isConfirmed()"></div>
      <button class="step" [class.done]="isConfirmed()">
        <span class="num">{{ isConfirmed() ? '✓' : '03' }}</span>
        <div><div class="lab">STEP 03</div><div class="name">入向量</div></div>
      </button>
    </div>

    <!-- Page head -->
    <div style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:18px;flex-wrap:wrap;gap:12px">
      <div>
        <span class="px-stamp rust">STEP 02 / 03 · MIRROR VIEW</span>
        <h1 style="margin-top:8px;font-size:28px">預覽資料</h1>
        <p style="color:var(--muted);font-size:13px;margin:0">
          Session: <span style="font-family:var(--font-mono)">{{ sessionId }}</span>
        </p>
      </div>
      <div class="row">
        <span class="pill" [class.teal]="status()==='pending_preview'" [class.rust]="status()==='failed'" [class.ink]="status()==='confirmed'">
          {{ statusLabel() }}
        </span>
      </div>
    </div>

    <!-- Loading -->
    @if (svc.loading()) {
      <div style="text-align:center;padding:48px;font-family:var(--font-mono);color:var(--muted)">
        ⏳ 載入中…
      </div>
    }

    @if (svc.error()) {
      <div style="padding:18px;border:2px solid var(--rust);box-shadow:3px 3px 0 var(--rust);color:var(--rust);font-family:var(--font-mono)">
        ⚠ {{ svc.error() }}
      </div>
    }

    @if (!svc.loading() && !svc.error() && svc.session()) {

      <!-- Status bar for confirmed/failed -->
      @if (status() === 'confirmed') {
        <div class="status-bar confirmed">
          ✓ 此 Session 已確認，Chunks 已送入向量化 Pipeline
          <a class="btn sm" routerLink="/admin">查看 Sessions</a>
        </div>
      }
      @if (status() === 'failed') {
        <div class="status-bar failed">
          ✕ 此 Session 已拒絕
          <a class="btn rust sm" routerLink="/upload">重新上傳</a>
        </div>
      }

      <!-- Low confidence alert -->
      @if (svc.lowConfidenceCount() > 0) {
        <div style="padding:12px 16px;margin-bottom:18px;border:1.5px dashed var(--rust);background:rgba(196,69,54,.04);font-family:var(--font-mono);font-size:12px">
          ⚠ <strong>{{ svc.lowConfidenceCount() }} 份文件</strong> 含低信心欄位，請在確認前審視標示為 <span class="pill rust">LOW</span> 的 chunks。
        </div>
      }

      <!-- Doc picker -->
      <div class="mv-doc-picker">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
          <span class="px-label" style="margin:0">// FILES</span>
          <span class="px-mono" style="font-size:11px;color:var(--muted)">{{ svc.documents().length }} 份 · {{ svc.chunks().length }} chunks</span>
        </div>
        <div class="doc-list-h">
          <button class="doc-item" [class.active]="svc.selectedDocId() === null"
                  (click)="svc.selectedDocId.set(null)">
            <div class="nm">全部文件</div>
            <div class="det">{{ svc.chunks().length }} chunks</div>
          </button>
          @for (doc of svc.documents(); track doc.doc_id) {
            <button class="doc-item" [class.active]="svc.selectedDocId() === doc.doc_id"
                    (click)="svc.selectedDocId.set(doc.doc_id)">
              <div class="nm">
                @if (doc.has_low_confidence) { <span class="flag-dot"></span> }
                {{ doc.filename }}
              </div>
              <div class="det">{{ doc.doc_type.toUpperCase() }}</div>
            </button>
          }
        </div>
      </div>

      <!-- Filter bar -->
      <div class="filter-bar">
        <span class="px-label" style="margin:0">// SEARCH</span>
        <input class="filter-input" type="text" placeholder="搜尋 chunk…"
               [value]="svc.filter()" (input)="svc.filter.set($any($event.target).value)" />
        <span class="px-mono" style="font-size:11px;color:var(--muted);margin-left:auto">
          {{ svc.filteredChunks().length }} / {{ svc.chunks().length }} chunks
        </span>
      </div>

      <!-- Chunks -->
      <div class="chunks-list">
        @for (chunk of svc.filteredChunks(); track chunk.chunk_id) {
          <div class="chunk" [class.low]="isLowConf(chunk)">
            <div class="chunk-head">
              <span class="chunk-name">{{ chunk.product_name || chunk.case_id || '(unnamed)' }}</span>
              <span class="chunk-id">{{ chunk.chunk_id.slice(0,8) }}</span>
              @if (isLowConf(chunk)) {
                <span class="pill rust" style="margin-left:auto">LOW CONF</span>
              }
              <span class="px-mono" style="font-size:10px;color:var(--muted);margin-left:auto">
                {{ chunk.doc_type }}
              </span>
            </div>
            <div class="chunk-body">
              <div class="specs">
                @if (chunk.product_name) {
                  <div class="spec"><span class="l">Product</span><span class="v">{{ chunk.product_name }}</span></div>
                }
                @if (chunk.material) {
                  <div class="spec"><span class="l">材料</span><span class="v">{{ chunk.material }}</span></div>
                }
                @if (chunk.dimensions) {
                  <div class="spec"><span class="l">尺寸</span><span class="v">{{ chunk.dimensions }}</span></div>
                }
                @if (chunk.face) {
                  <div class="spec"><span class="l">Face</span><span class="v">{{ chunk.face }}</span></div>
                }
                @if (chunk.situation) {
                  <div class="spec"><span class="l">狀況</span><span class="v">{{ chunk.situation }}</span></div>
                }
                @if (chunk.action) {
                  <div class="spec"><span class="l">動作</span><span class="v">{{ chunk.action }}</span></div>
                }
                @if (chunk.reason) {
                  <div class="spec"><span class="l">原因</span><span class="v">{{ chunk.reason }}</span></div>
                }
                @if (chunk.applies_to) {
                  <div class="spec"><span class="l">適用範圍</span><span class="v">{{ chunk.applies_to }}</span></div>
                }
                @if (!hasAnyField(chunk)) {
                  <div class="spec"><span class="v empty">（無抽取欄位）</span></div>
                }
              </div>
              <div class="embed-text">
                <span class="lab">embed_text</span>
                {{ chunk.embed_text }}
              </div>
            </div>
          </div>
        }

        @if (svc.filteredChunks().length === 0 && !svc.loading()) {
          <div style="text-align:center;padding:48px;color:var(--muted);font-family:var(--font-mono)">
            無符合條件的 chunks
          </div>
        }
      </div>

      <!-- Confirm bar -->
      @if (svc.canConfirm() && isAdmin()) {
        <div class="confirm-bar">
          <div class="info">
            <span class="px-stamp">審視完畢？</span>
            <span style="color:var(--muted);font-size:12px">確認後 Chunks 將進入向量化 Pipeline，無法撤回。</span>
          </div>
          <button class="btn ghost sm" [disabled]="actionLoading()" (click)="onReject()">拒絕</button>
          <button class="btn rust" [disabled]="actionLoading()" (click)="onConfirm()">
            {{ actionLoading() ? '處理中…' : '✓ 確認資料歸屬' }}
          </button>
        </div>
      }
    }
  `,
})
export class PreviewComponent implements OnInit, OnDestroy {
  @Input() sessionId!: string;

  readonly svc   = inject(PreviewService);
  private readonly auth  = inject(AuthService);
  private readonly toast = inject(ToastService);

  readonly isAdmin      = this.auth.isAdmin;
  readonly actionLoading = signal(false);
  readonly status       = computed(() => this.svc.session()?.status ?? '');
  readonly isConfirmed  = computed(() => this.status() === 'confirmed');

  private _pollSub?: Subscription;

  readonly statusLabel = computed(() => {
    const m: Record<string, string> = {
      pending_preview: '等待確認', confirmed: '已確認',
      processing: '處理中', done: '完成', failed: '已拒絕',
    };
    return m[this.status()] ?? this.status();
  });

  async ngOnInit(): Promise<void> {
    await this.svc.loadSession(this.sessionId);
    if (this.svc.session()?.status === 'pending_preview') {
      this._pollSub = this.svc.startPolling(this.sessionId);
    }
  }

  ngOnDestroy(): void {
    this._pollSub?.unsubscribe();
    this.svc.reset();
  }

  async onConfirm(): Promise<void> {
    this.actionLoading.set(true);
    try {
      const res = await this.svc.confirm(this.sessionId);
      this.toast.success(res.message);
    } catch (e: any) {
      this.toast.error(e?.error?.detail ?? '確認失敗');
    } finally {
      this.actionLoading.set(false);
    }
  }

  async onReject(): Promise<void> {
    if (!confirm('確定要拒絕此 Session？文件需重新上傳。')) return;
    this.actionLoading.set(true);
    try {
      const res = await this.svc.reject(this.sessionId);
      this.toast.success(res.message);
    } catch (e: any) {
      this.toast.error(e?.error?.detail ?? '拒絕失敗');
    } finally {
      this.actionLoading.set(false);
    }
  }

  isLowConf(chunk: Chunk): boolean {
    const doc = this.svc.documents().find(d => d.doc_id === chunk.doc_id);
    return doc?.has_low_confidence === true;
  }

  hasAnyField(c: Chunk): boolean {
    return !!(c.product_name || c.material || c.dimensions || c.face ||
              c.situation || c.action || c.reason || c.applies_to);
  }
}
