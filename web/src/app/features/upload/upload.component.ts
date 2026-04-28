import { Component, inject, signal, computed, ElementRef, ViewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Router } from '@angular/router';
import { UploadService } from './services/upload.service';
import { UploadJob } from '../../core/models';
import { AuthService } from '../../core/auth/auth.service';
import { ToastService } from '../../core/notifications/toast.service';

@Component({
  selector: 'app-upload',
  standalone: true,
  imports: [RouterLink],
  styles: [`
    .dropzone {
      border: 2px dashed var(--ink); padding: 48px 24px; text-align: center;
      background: var(--bg-2); cursor: pointer; transition: all .15s ease;
      box-shadow: 4px 4px 0 var(--ink);
    }
    .dropzone:hover, .dropzone.over {
      border-color: var(--rust); background: rgba(196,69,54,.04);
      box-shadow: 4px 4px 0 var(--rust);
    }
    .dropzone h3 { font-family: var(--font-mono); font-size: 18px; margin: 12px 0 4px; font-weight: 700; }
    .dropzone p { margin: 0; color: var(--muted); font-size: 13px; }
    .dropzone .types { margin-top: 12px; display: flex; justify-content: center; gap: 6px; flex-wrap: wrap; }

    .queue { margin-top: 22px; display: flex; flex-direction: column; gap: 8px; }
    .queue-item {
      display: grid; grid-template-columns: 48px 1fr auto auto;
      gap: 14px; align-items: center; padding: 14px 16px;
      background: var(--bg-2); border: 1px solid var(--ink);
      box-shadow: 2px 2px 0 var(--ink); position: relative;
    }
    .queue-item.is-failed {
      border-color: var(--rust) !important; box-shadow: 3px 3px 0 var(--rust) !important;
    }
    .queue-item.is-failed::before {
      content: ""; position: absolute; left: 0; top: 0; width: 6px; height: 100%;
      background: repeating-linear-gradient(0deg, var(--rust) 0 6px, var(--ink) 6px 12px);
    }
    .file-ico {
      width: 42px; height: 42px; display: grid; place-items: center;
      font-family: var(--font-mono); font-size: 10px; font-weight: 700;
    }
    .file-ico.pdf  { background: rgba(196,69,54,.14); color: var(--rust); }
    .file-ico.docx { background: rgba(25,114,120,.14); color: var(--teal); }
    .file-ico.tap, .file-ico.nc { background: rgba(119,46,37,.14); color: var(--wine); }
    .file-ico.dxf  { background: rgba(40,61,59,.12); color: var(--ink); }
    .file-ico.default { background: rgba(40,61,59,.08); color: var(--muted); }
    .q-meta { min-width: 0; }
    .q-name {
      font-family: var(--font-mono); font-weight: 700; font-size: 13px;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
      display: flex; align-items: center; gap: 4px;
    }
    .q-sub { font-family: var(--font-mono); font-size: 10.5px; color: var(--muted); letter-spacing: .04em; text-transform: uppercase; margin-top: 2px; }
    .err-detail {
      margin-top: 10px; padding: 10px 12px;
      border: 1.5px dashed var(--rust); background: rgba(196,69,54,.04);
      font-family: var(--font-mono); font-size: 11.5px; line-height: 1.55;
    }
    .err-code {
      background: var(--rust); color: var(--cream); padding: 2px 8px;
      font-size: 10px; font-weight: 700; letter-spacing: .1em;
      border: 1.5px solid var(--ink); box-shadow: 2px 2px 0 var(--ink);
    }
    .actions-cell { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
    .status-cell { min-width: 80px; text-align: right; }

    .stat-row { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; margin-bottom: 22px; }
    @media (max-width: 920px) { .stat-row { grid-template-columns: repeat(2,1fr); } }

    .info-card { margin-top: 18px; padding: 14px 18px; }
    .info-card ol { margin: 0; padding-left: 18px; color: var(--muted); font-size: 13px; line-height: 1.85; }
  `],
  template: `
    <!-- Stepper -->
    <div class="stepper">
      <button class="step active">
        <span class="num">01</span>
        <div><div class="lab">STEP 01</div><div class="name">上傳資料</div></div>
      </button>
      <div class="bar"></div>
      <button class="step" [routerLink]="[]">
        <span class="num">02</span>
        <div><div class="lab">STEP 02</div><div class="name">預覽 / 確認</div></div>
      </button>
      <div class="bar"></div>
      <button class="step">
        <span class="num">03</span>
        <div><div class="lab">STEP 03</div><div class="name">入向量</div></div>
      </button>
    </div>

    <!-- Page head -->
    <div class="page-head" style="display:flex;align-items:flex-end;justify-content:space-between;margin-bottom:22px;flex-wrap:wrap;gap:12px">
      <div>
        <span class="px-stamp rust">STEP 01 / 03 · INGEST</span>
        <h1 style="margin-top:8px;font-size:28px;font-weight:700">上傳資料</h1>
        <p style="color:var(--muted);font-size:13.5px;margin:0">把 PDF、Word、CAD 工檔交給模型解析。處理完成後會出現可確認的預覽。</p>
      </div>
      <div class="row">
        <button class="btn primary" (click)="fileInput.click()">
          ↑ 選擇檔案
        </button>
        <input #fileInput type="file" multiple style="display:none"
               accept=".pdf,.docx,.tap,.nc,.dxf"
               (change)="onFileChange($event)" />
      </div>
    </div>

    <!-- Stats -->
    <div class="stat-row">
      <div class="stat"><div class="lab">上傳中</div><div class="v">{{ uploadingCount() }}</div></div>
      <div class="stat"><div class="lab">已完成</div><div class="v" style="color:var(--teal)">{{ doneCount() }}</div></div>
      <div class="stat"><div class="lab">失敗</div><div class="v" style="color:var(--rust)">{{ errorCount() }}</div></div>
      <div class="stat accent"><div class="lab">限制</div><div class="v">50 MB</div></div>
    </div>

    <!-- Drop zone -->
    <div class="dropzone" [class.over]="isDragOver()"
         (dragover)="$event.preventDefault(); isDragOver.set(true)"
         (dragleave)="isDragOver.set(false)"
         (drop)="onDrop($event)"
         (click)="fileInput.click()">
      <h3>拖拉檔案到這裡</h3>
      <p>或點擊上方「選擇檔案」按鈕。每次可選多個檔案。</p>
      <div class="types">
        <span class="pill">PDF</span>
        <span class="pill">DOCX</span>
        <span class="pill">TAP / NC</span>
        <span class="pill">DXF</span>
      </div>
    </div>

    <!-- Queue -->
    @if (queue().length > 0) {
      <div class="queue">
        @for (job of queue(); track job.id) {
          <div class="queue-item" [class.is-failed]="job.status === 'error'">
            <div class="file-ico {{ fileExt(job.name) }}">{{ fileExt(job.name).toUpperCase() }}</div>
            <div class="q-meta">
              <div class="q-name">
                {{ job.name }}
                @if (job.status === 'done') {
                  <span class="pill teal" style="margin-left:4px">完成</span>
                }
                @if (job.status === 'error') {
                  <span class="pill rust" style="margin-left:4px">失敗</span>
                }
              </div>
              <div class="q-sub">{{ formatSize(job.size) }}</div>
              @if (job.status === 'uploading') {
                <div class="progress-track" style="margin-top:8px">
                  <div class="progress-bar" [style.width.%]="job.pct"></div>
                </div>
              }
              @if (job.status === 'error') {
                <div class="err-detail">
                  <span class="err-code">ERR</span>
                  <span style="margin-left:8px;font-weight:600">{{ job.errorMsg }}</span>
                </div>
              }
            </div>
            <div class="status-cell">
              @if (job.status === 'uploading') {
                <span class="px-mono" style="font-size:12px">{{ job.pct }}%</span>
              }
            </div>
            <div class="actions-cell">
              @if (job.status === 'done' && job.sessionId) {
                <a class="btn primary sm" [routerLink]="['/preview', job.sessionId]">預覽 ▸</a>
              }
              <button class="btn ghost sm" (click)="uploadSvc.removeJob(job.id)">✕</button>
            </div>
          </div>
        }
      </div>
    }

    <!-- Info -->
    <div class="card info-card" style="margin-top:28px">
      <div class="row" style="gap:10px;margin-bottom:10px">
        <span class="pill teal dot">處理流程</span>
        <h3 style="margin:0;font-size:15px;font-weight:700">上傳後會發生什麼？</h3>
      </div>
      <ol>
        <li>檔案上傳到租戶獨立的儲存空間（GCS）</li>
        <li>進入 RAG pipeline：文件解析 → 欄位抽取 → Chunk 分組</li>
        <li>產出 <strong style="color:var(--ink)">Mirror View 預覽</strong>，可審視模型抽取是否正確</li>
        <li>管理員「確認」後，Chunks 才進入向量庫，可被 Chat 引用</li>
      </ol>
    </div>
  `,
})
export class UploadComponent {
  readonly uploadSvc = inject(UploadService);
  private readonly toast  = inject(ToastService);
  private readonly auth   = inject(AuthService);

  readonly isDragOver = signal(false);
  readonly queue = this.uploadSvc.queue;

  readonly uploadingCount = computed(() => this.queue().filter(j => j.status === 'uploading').length);
  readonly doneCount      = computed(() => this.queue().filter(j => j.status === 'done').length);
  readonly errorCount     = computed(() => this.queue().filter(j => j.status === 'error').length);

  onFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files?.length) return;
    this.uploadFiles(input.files);
    input.value = '';
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
    if (event.dataTransfer?.files?.length) {
      this.uploadFiles(event.dataTransfer.files);
    }
  }

  uploadFiles(files: FileList): void {
    if (!this.auth.isAdmin()) {
      this.toast.error('只有管理員可以上傳文件');
      return;
    }
    Array.from(files).forEach(f => {
      if (f.size > 50 * 1024 * 1024) {
        this.toast.error(`${f.name} 超過 50MB 限制`);
        return;
      }
      this.uploadSvc.upload(f);
    });
  }

  fileExt(name: string): string {
    const ext = name.split('.').pop()?.toLowerCase() ?? '';
    return ['pdf','docx','tap','nc','dxf'].includes(ext) ? ext : 'default';
  }

  formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }
}
