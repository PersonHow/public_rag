import { Component, inject, signal, computed, ElementRef, ViewChild } from '@angular/core';
import { RouterLink } from '@angular/router';
import { UploadService } from './services/upload.service';
import { UploadJob } from '../../core/models';
import { AuthService } from '../../core/auth/auth.service';
import { ToastService } from '../../core/notifications/toast.service';
import { StepperComponent } from '../../shared/ui/stepper/stepper.component';
import { PageHeadComponent } from '../../shared/ui/page-head/page-head.component';

@Component({
  selector: 'app-upload',
  standalone: true,
  imports: [RouterLink, StepperComponent, PageHeadComponent],
  templateUrl: './upload.component.html',
  styleUrl: './upload.component.scss',
})
export class UploadComponent {
  readonly uploadSvc = inject(UploadService);
  private readonly toast  = inject(ToastService);
  private readonly auth   = inject(AuthService);

  readonly isDragOver = signal(false);
  readonly queue = this.uploadSvc.queue;

  readonly uploadingCount = computed(() => this.queue().filter(j => j.status === 'uploading').length);
  readonly doneCount      = computed(() => this.queue().filter(j => j.status === 'done').length);
  readonly errorCount     = computed(() => this.queue().filter(j => j.status === 'error').length);

  onFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (!input.files?.length) return;
    this.uploadFiles(input.files);
    input.value = '';
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.isDragOver.set(false);
    if (event.dataTransfer?.files?.length) {
      this.uploadFiles(event.dataTransfer.files);
    }
  }

  uploadFiles(files: FileList): void {
    if (!this.auth.isAdmin()) {
      this.toast.error('只有管理員可以上傳文件');
      return;
    }
    Array.from(files).forEach(f => {
      if (f.size > 50 * 1024 * 1024) {
        this.toast.error(`${f.name} 超過 50MB 限制`);
        return;
      }
      this.uploadSvc.upload(f);
    });
  }

  fileExt(name: string): string {
    const ext = name.split('.').pop()?.toLowerCase() ?? '';
    return ['pdf','docx','tap','nc','dxf'].includes(ext) ? ext : 'default';
  }

  formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
  }
}
