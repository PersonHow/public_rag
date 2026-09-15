import { HttpInterceptorFn } from '@angular/common/http';
import { environment } from '../../../environments/environment';

// access_token 改放 httpOnly cookie，JS 無法（也不該）讀取。
// 對自家 API 的請求一律帶上 cookie；同源走 proxy 時本就會帶，withCredentials 為防呆。
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  if (!req.url.startsWith(environment.apiUrl)) return next(req);
  return next(req.clone({ withCredentials: true }));
};
