import { Component, input, output } from '@angular/core';

/** 密碼欄位的顯示／隱藏切換鈕，需放在 .password-wrap 內（樣式見 _global.scss）。 */
@Component({
  selector: 'app-password-toggle',
  standalone: true,
  templateUrl: './password-toggle.component.html',
  // 不用 host style：CSP 只放行帶 nonce 的 <style>，style 屬性會被擋
  styles: [':host { display: contents; }'],
})
export class PasswordToggleComponent {
  readonly visible = input(false);
  readonly toggled = output<void>();
}
