import { Component, input } from '@angular/core';

@Component({
  selector: 'app-page-head',
  standalone: true,
  templateUrl: './page-head.component.html',
  styleUrl: './page-head.component.scss',
})
export class PageHeadComponent {
  readonly stamp      = input('');
  readonly stampColor = input<'rust' | 'teal' | ''>('');
  readonly title      = input.required<string>();
  readonly desc       = input('');
}
