import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  message: string;
  kind: 'success' | 'error' | '';
}

@Injectable({ providedIn: 'root' })
export class ToastService {
  private _counter = 0;
  readonly toasts = signal<Toast[]>([]);

  show(message: string, kind: Toast['kind'] = ''): void {
    const id = ++this._counter;
    this.toasts.update(t => [...t, { id, message, kind }]);
    setTimeout(() => this._dismiss(id), 2400);
  }

  success(message: string): void { this.show(message, 'success'); }
  error(message: string):   void { this.show(message, 'error'); }

  private _dismiss(id: number): void {
    this.toasts.update(t => t.filter(x => x.id !== id));
  }
}
