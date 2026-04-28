import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { NgFor, NgClass } from '@angular/common';
import { ToastService } from './core/notifications/toast.service';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, NgFor, NgClass],
  template: `
    <router-outlet />
    <div class="toast-host">
      @for (t of toast.toasts(); track t.id) {
        <div class="toast" [ngClass]="t.kind">{{ t.message }}</div>
      }
    </div>
  `,
})
export class AppComponent {
  readonly toast = inject(ToastService);
}
