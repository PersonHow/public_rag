import { Pipe, PipeTransform } from '@angular/core';

@Pipe({ name: 'truncateId', standalone: true })
export class TruncateIdPipe implements PipeTransform {
  transform(value: string, length = 8): string {
    return value.slice(0, length) + '…';
  }
}
