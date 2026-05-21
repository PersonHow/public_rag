import { Component, Input, signal } from '@angular/core';
import { SlicePipe } from '@angular/common';
import { Chunk } from '../../../../shared/models';

export interface ChunkGroup {
  productName: string;
  material: string | null;
  dimensions: string | null;
  docType: string;
  chunks: Chunk[];
}

@Component({
  selector: 'app-chunk-card',
  standalone: true,
  imports: [SlicePipe],
  templateUrl: './chunk-card.component.html',
  styleUrl: './chunk-card.component.scss',
})
export class ChunkCardComponent {
  @Input({ required: true }) group!: ChunkGroup;

  // 輪播與展開狀態各自獨立於每張卡片
  readonly carouselIdx   = signal(0);
  readonly embedExpanded = signal(false);

  get active(): Chunk {
    return this.group.chunks[this.carouselIdx()];
  }

  prev(): void {
    const t = this.group.chunks.length;
    this.carouselIdx.update(i => (i - 1 + t) % t);
  }

  next(): void {
    const t = this.group.chunks.length;
    this.carouselIdx.update(i => (i + 1) % t);
  }

  toggleEmbed(): void {
    this.embedExpanded.update(v => !v);
  }
}
