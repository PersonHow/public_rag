import { Routes } from '@angular/router';
import { authGuard } from './core/auth/auth.guard';
import { adminGuard } from './core/auth/role.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'hub' },

  // ── Public (auth-shell) ─────────────────────────────────
  {
    path: '',
    loadComponent: () =>
      import('./layouts/auth-shell/auth-shell.component').then(m => m.AuthShellComponent),
    children: [
      {
        path: 'login',
        loadComponent: () =>
          import('./features/auth/login/login.component').then(m => m.LoginComponent),
      },
    ],
  },

  // ── Protected (app-shell) ───────────────────────────────
  {
    path: '',
    canMatch: [authGuard],
    loadComponent: () =>
      import('./layouts/app-shell/app-shell.component').then(m => m.AppShellComponent),
    children: [
      {
        path: 'hub',
        loadComponent: () =>
          import('./features/hub/hub.component').then(m => m.HubComponent),
      },
      {
        path: 'upload',
        loadComponent: () =>
          import('./features/upload/upload.component').then(m => m.UploadComponent),
      },
      {
        path: 'preview/:sessionId',
        loadComponent: () =>
          import('./features/preview/preview.component').then(m => m.PreviewComponent),
      },
      {
        path: 'chat',
        loadComponent: () =>
          import('./features/chat/chat.component').then(m => m.ChatComponent),
      },
      {
        path: 'admin',
        canMatch: [adminGuard],
        loadComponent: () =>
          import('./features/admin/sessions/sessions.component').then(m => m.AdminSessionsComponent),
      },
      {
        path: 'admin/users',
        canMatch: [adminGuard],
        loadComponent: () =>
          import('./features/admin/users/users.component').then(m => m.AdminUsersComponent),
      },
    ],
  },

  { path: '**', redirectTo: 'hub' },
];
