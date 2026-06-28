import { Component, computed, input } from '@angular/core';

interface SpecRow {
  label: string;
  values: string[];
}

/**
 * 把 chunk.specs（JSON 物件序列化字串，常見於工程圖面抽取）渲染成規格表。
 * key → 左欄欄位名，value（字串或字串陣列）→ 右欄。無法解析成物件時原樣顯示。
 */
@Component({
  selector: 'app-spec-table',
  standalone: true,
  templateUrl: './spec-table.component.html',
  styleUrl: './spec-table.component.scss',
})
export class SpecTableComponent {
  readonly specs = input<string | null>(null);

  readonly rows = computed<SpecRow[]>(() => {
    const raw = this.specs();
    if (!raw) return [];
    let obj: unknown;
    try { obj = JSON.parse(raw); } catch { return []; }
    if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return [];
    return Object.entries(obj as Record<string, unknown>)
      .filter(([, v]) => v !== null && v !== undefined && v !== '')
      .map(([label, v]) => ({
        label,
        values: Array.isArray(v)
          ? v.map(x => String(x)).filter(s => s.trim())
          : [String(v)],
      }))
      .filter(r => r.values.length > 0);
  });

  /** 不是合法的 JSON 物件時，回傳原始字串供原樣顯示。 */
  readonly fallback = computed<string | null>(() => {
    const raw = this.specs();
    if (!raw) return null;
    return this.rows().length === 0 ? raw : null;
  });
}
