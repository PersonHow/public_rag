import { Component, Input, inject, signal } from '@angular/core';
import { SlicePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Chunk, ChunkPatch } from '../../../../shared/models';
import { PreviewService } from '../../../../core/services/preview.service';
import { ToastService } from '../../../../core/services/toast.service';
import { SpecTableComponent } from '../../../../shared/components/spec-table/spec-table.component';

export interface ChunkGroup {
  productName: string;
  material: string | null;
  dimensions: string | null;
  docType: string;
  chunks: Chunk[];
}

/** v2：可在預覽階段 inline 編輯的欄位（與後端 ChunkPatch 允許欄位的子集）。 */
export type InlineEditableField =
  | 'product_name'
  | 'material'
  | 'dimensions'
  | 'situation'
  | 'action'
  | 'reason'
  | 'embed_text';

@Component({
  selector: 'app-chunk-card',
  standalone: true,
  imports: [SlicePipe, FormsModule, SpecTableComponent],
  templateUrl: './chunk-card.component.html',
  styleUrl: './chunk-card.component.scss',
})
export class ChunkCardComponent {
  @Input({ required: true }) group!: ChunkGroup;
  @Input({ required: true }) sessionId!: string;
  /** 只有 session.status === 'pending_preview' 時 parent 才會傳 true。 */
  @Input() editable = false;

  private readonly svc   = inject(PreviewService);
  private readonly toast = inject(ToastService);

  // 輪播 + embed_text 摺疊狀態，每張卡片獨立
  readonly carouselIdx   = signal(0);
  readonly embedExpanded = signal(false);

  // ── 編輯狀態 ───────────────────────────────────────────
  readonly editingField = signal<InlineEditableField | null>(null);
  readonly draftValue   = signal<string>('');
  readonly saving       = signal(false);
  /** 記下開始編輯時的 chunk_id，避免 group/active 重排導致 PATCH 錯對象。 */
  private editingChunkId: string | null = null;

  get active(): Chunk {
    return this.group.chunks[this.carouselIdx()];
  }

  // ── 卡片導覽 ───────────────────────────────────────────
  prev(): void {
    if (this.editingField()) this.cancelEdit();
    const t = this.group.chunks.length;
    this.carouselIdx.update(i => (i - 1 + t) % t);
  }

  next(): void {
    if (this.editingField()) this.cancelEdit();
    const t = this.group.chunks.length;
    this.carouselIdx.update(i => (i + 1) % t);
  }

  toggleEmbed(): void {
    if (this.editingField() === 'embed_text') return;
    this.embedExpanded.update(v => !v);
  }

  // ── 編輯 ───────────────────────────────────────────────
  beginEdit(field: InlineEditableField): void {
    if (!this.editable || this.saving()) return;
    const chunk = this.active;
    this.editingChunkId = chunk.chunk_id;
    this.draftValue.set((chunk[field] ?? '') as string);
    this.editingField.set(field);
    if (field === 'embed_text') this.embedExpanded.set(true);
  }

  cancelEdit(): void {
    this.editingField.set(null);
    this.draftValue.set('');
    this.editingChunkId = null;
  }

  async saveEdit(): Promise<void> {
    const field = this.editingField();
    const chunkId = this.editingChunkId;
    if (!field || !chunkId || this.saving()) return;

    const orig = this.group.chunks.find(c => c.chunk_id === chunkId);
    if (!orig) { this.cancelEdit(); return; }

    const before = ((orig[field] ?? '') as string).trim();
    const after  = this.draftValue().trim();

    // 沒改 → 直接收掉，不打 API
    if (before === after) {
      this.cancelEdit();
      return;
    }

    // embed_text 不可清空（後端也會擋，前端先擋以免無謂往返）
    if (field === 'embed_text' && !after) {
      this.toast.error('embed_text 不可為空');
      return;
    }

    this.saving.set(true);
    try {
      const patch: ChunkPatch = { [field]: after } as ChunkPatch;
      await this.svc.patchChunk(this.sessionId, chunkId, patch);
      this.toast.success('已更新');
      this.cancelEdit();
    } catch (e: any) {
      const detail = e?.error?.detail;
      const msg = typeof detail === 'string' ? detail : '更新失敗';
      this.toast.error(msg);
      // 失敗：保持編輯態，draftValue 仍是使用者輸入，可再試或 Escape 取消
    } finally {
      this.saving.set(false);
    }
  }

  onInputKeydown(ev: KeyboardEvent): void {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      this.saveEdit();
    } else if (ev.key === 'Escape') {
      ev.preventDefault();
      this.cancelEdit();
    }
  }

  onTextareaKeydown(ev: KeyboardEvent): void {
    if (ev.key === 'Escape') {
      ev.preventDefault();
      this.cancelEdit();
    } else if (ev.key === 'Enter' && (ev.metaKey || ev.ctrlKey)) {
      ev.preventDefault();
      this.saveEdit();
    }
  }
}
