import { Component, Input, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { FullTextResponse, FullTextChunk, ChunkPatch } from '../../../../shared/models';
import { PreviewService } from '../../../../core/services/preview.service';
import { ToastService } from '../../../../core/services/toast.service';

export interface ProductSection {
  productName: string;
  productId:   string | null;
  material:    string | null;
  dimensions:  string | null;
  items:       FullTextChunk[];
}

/** v2：整體預覽可 inline 編輯的欄位（與 ChunkPatch 允許欄位子集） */
export type FTEditableField = 'product_name' | 'situation' | 'action' | 'reason';

@Component({
  selector: 'app-fulltext-view',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './fulltext-view.component.html',
  styleUrl: './fulltext-view.component.scss',
})
export class FulltextViewComponent {
  @Input({ required: true }) fullText!: FullTextResponse;
  /** v2：editable 為 true 時開放 inline 編輯，需搭配 sessionId。 */
  @Input() sessionId = '';
  @Input() editable = false;

  private readonly svc   = inject(PreviewService);
  private readonly toast = inject(ToastService);

  readonly editingChunkId = signal<string | null>(null);
  readonly editingField   = signal<FTEditableField | null>(null);
  readonly draftValue     = signal<string>('');
  readonly saving         = signal(false);

  /**
   * 核心邏輯：
   * 1. 按 chunk_index 排序
   * 2. 多數決 product_name（讀模式：吸收偶發的少數名稱，修正 Gemini 推斷不一致）
   * 3. **編輯模式**：不吸收，尊重每條 chunk 的 product_name，避免使用者改完後又被多數決吃掉
   * 4. 回傳 ProductSection[]
   */
  get sections(): ProductSection[] {
    if (!this.fullText?.chunks?.length) return [];

    const sorted = [...this.fullText.chunks].sort(
      (a, b) => (a.chunk_index ?? 0) - (b.chunk_index ?? 0)
    );

    const nameCount = new Map<string, number>();
    for (const c of sorted) {
      const name = (c.product_name ?? '').trim();
      if (name) nameCount.set(name, (nameCount.get(name) ?? 0) + 1);
    }
    const majorityName = nameCount.size > 0
      ? [...nameCount.entries()].sort((a, b) => b[1] - a[1])[0][0]
      : null;

    const sectionMap = new Map<string, ProductSection>();

    for (const chunk of sorted) {
      const rawName = (chunk.product_name ?? '').trim();
      const key = this.editable
        ? (rawName || '（未指定產品）')
        : ((nameCount.get(rawName) ?? 0) <= 1 && majorityName
            ? majorityName
            : (rawName || majorityName || '（未指定產品）'));

      if (!sectionMap.has(key)) {
        sectionMap.set(key, {
          productName: key,
          productId:   chunk.product_id  ?? null,
          material:    chunk.material    ?? null,
          dimensions:  chunk.dimensions  ?? null,
          items:       [],
        });
      }
      sectionMap.get(key)!.items.push(chunk);
    }

    return Array.from(sectionMap.values());
  }

  /** 給「歸類」editor 的 datalist 自動完成清單。 */
  get knownProductNames(): string[] {
    const names = new Set<string>();
    for (const c of this.fullText?.chunks ?? []) {
      const n = (c.product_name ?? '').trim();
      if (n) names.add(n);
    }
    return Array.from(names);
  }

  isEditing(chunkId: string, field: FTEditableField): boolean {
    return this.editingChunkId() === chunkId && this.editingField() === field;
  }

  beginEdit(chunk: FullTextChunk, field: FTEditableField): void {
    if (!this.editable || this.saving()) return;
    this.editingChunkId.set(chunk.chunk_id);
    this.editingField.set(field);
    this.draftValue.set(((chunk as unknown as Record<string, unknown>)[field] as string | undefined) ?? '');
  }

  cancelEdit(): void {
    this.editingChunkId.set(null);
    this.editingField.set(null);
    this.draftValue.set('');
  }

  async saveEdit(originalValue: string | undefined | null): Promise<void> {
    const field   = this.editingField();
    const chunkId = this.editingChunkId();
    if (!field || !chunkId || this.saving()) return;

    const before = (originalValue ?? '').trim();
    const after  = this.draftValue().trim();

    // 沒改 → 直接收掉，不打 API
    if (before === after) {
      this.cancelEdit();
      return;
    }

    this.saving.set(true);
    try {
      const patch: ChunkPatch = { [field]: after } as ChunkPatch;
      await this.svc.patchChunk(this.sessionId, chunkId, patch);
      this.toast.success('已更新');
      this.cancelEdit();
    } catch (e: unknown) {
      const detail = (e as { error?: { detail?: unknown } })?.error?.detail;
      this.toast.error(typeof detail === 'string' ? detail : '更新失敗');
      // 失敗：保留編輯態，draftValue 仍是使用者輸入
    } finally {
      this.saving.set(false);
    }
  }

  onInputKeydown(ev: KeyboardEvent, originalValue: string | undefined | null): void {
    if (ev.key === 'Enter') {
      ev.preventDefault();
      this.saveEdit(originalValue);
    } else if (ev.key === 'Escape') {
      ev.preventDefault();
      this.cancelEdit();
    }
  }

  onTextareaKeydown(ev: KeyboardEvent, originalValue: string | undefined | null): void {
    if (ev.key === 'Escape') {
      ev.preventDefault();
      this.cancelEdit();
    } else if (ev.key === 'Enter' && (ev.metaKey || ev.ctrlKey)) {
      ev.preventDefault();
      this.saveEdit(originalValue);
    }
  }
}
