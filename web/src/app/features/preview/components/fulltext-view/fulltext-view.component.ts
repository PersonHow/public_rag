import { Component, Input } from '@angular/core';
import { FullTextResponse, FullTextChunk } from '../../../../shared/models';

export interface ProductSection {
  productName: string;
  productId:   string | null;
  material:    string | null;
  dimensions:  string | null;
  items:       FullTextChunk[];
}

@Component({
  selector: 'app-fulltext-view',
  standalone: true,
  imports: [],
  templateUrl: './fulltext-view.component.html',
  styleUrl: './fulltext-view.component.scss',
})
export class FulltextViewComponent {
  @Input({ required: true }) fullText!: FullTextResponse;

  /**
   * 核心邏輯：
   * 1. 按 chunk_index 排序
   * 2. 多數決 product_name（修正 Gemini 推斷不一致）
   * 3. 出現 ≤1 次的少數名稱 → 歸入多數決名稱
   * 4. 回傳 ProductSection[]
   */
  get sections(): ProductSection[] {
    if (!this.fullText?.chunks?.length) return [];

    // Step 1：排序
    const sorted = [...this.fullText.chunks].sort(
      (a, b) => (a.chunk_index ?? 0) - (b.chunk_index ?? 0)
    );

    // Step 2：統計各 product_name 出現次數
    const nameCount = new Map<string, number>();
    for (const c of sorted) {
      const name = (c.product_name ?? '').trim();
      if (name) nameCount.set(name, (nameCount.get(name) ?? 0) + 1);
    }

    // Step 3：多數決
    const majorityName = nameCount.size > 0
      ? [...nameCount.entries()].sort((a, b) => b[1] - a[1])[0][0]
      : null;

    // Step 4：分組
    const sectionMap = new Map<string, ProductSection>();

    for (const chunk of sorted) {
      const rawName = (chunk.product_name ?? '').trim();
      const key = (nameCount.get(rawName) ?? 0) <= 1 && majorityName
        ? majorityName
        : (rawName || majorityName || '（未指定產品）');

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
}
