import { Component, computed, input } from '@angular/core';

type BtnVariant = 'default' | 'primary' | 'rust' | 'ghost' | 'danger' | 'icon';
type BtnSize    = 'default' | 'sm';

@Component({
  selector: 'app-button',
  standalone: true,
  templateUrl: './button.component.html',
  // 不用 host style：CSP 只放行帶 nonce 的 <style>，style 屬性會被擋
  styles: [':host { display: contents; }'],
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
