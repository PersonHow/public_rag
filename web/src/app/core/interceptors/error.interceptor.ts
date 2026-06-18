import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';
import { ToastService } from '../services/toast.service';
import { AuthService } from '../services/auth.service';

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const toast = inject(ToastService);
  const auth  = inject(AuthService);

  const isLoginRequest = req.url.endsWith('/auth/login');

  return next(req).pipe(
    catchError(err => {
      if (isLoginRequest) {
        return throwError(() => err);
      }
      if (err.status === 401) {
        auth.logout();
        toast.error('登入已過期，請重新登入');
      } else if (err.status === 403) {
        toast.error('權限不足');
      } else if (err.status >= 500) {
        toast.error(`伺服器錯誤 (${err.status})`);
      } else if (err.status === 0) {
        toast.error('無法連線到後端，請確認服務是否啟動');
      }
      return throwError(() => err);
    })
  );
};
