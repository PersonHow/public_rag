import { Component, input } from '@angular/core';

@Component({
  selector: 'app-status-badge',
  standalone: true,
  templateUrl: './status-badge.component.html',
})
export class StatusBadgeComponent {
  readonly label = input.required<string>();
  readonly color = input<'teal' | 'rust' | 'ink' | 'wine' | ''>('');
}
