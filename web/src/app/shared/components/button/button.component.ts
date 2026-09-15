import { Component, computed, input } from '@angular/core';

type BtnVariant = 'default' | 'primary' | 'rust' | 'ghost' | 'danger' | 'icon';
type BtnSize    = 'default' | 'sm';

@Component({
  selector: 'app-button',
  standalone: true,
  templateUrl: './button.component.html',
  host: { style: 'display:contents' },
})
export class ButtonComponent {
  readonly variant  = input<BtnVariant>('default');
  readonly size     = input<BtnSize>('default');
  readonly disabled = input(false);
  readonly type     = input<'button' | 'submit' | 'reset'>('button');

  protected readonly classes = computed(() => {
    if (this.variant() === 'icon') return 'icon-btn';
    return [
      'btn',
      this.variant() !== 'default' ? this.variant() : '',
      this.size()    !== 'default' ? this.size()    : '',
    ].filter(Boolean).join(' ');
  });
}
