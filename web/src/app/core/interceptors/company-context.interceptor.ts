import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { AuthService } from '../services/auth.service';
import { CompanyContextService } from '../services/company-context.service';
import { environment } from '../../../environments/environment';

export const companyContextInterceptor: HttpInterceptorFn = (req, next) => {
  const auth    = inject(AuthService);
  const context = inject(CompanyContextService);

  const isSuperAdmin   = auth.isSuperAdmin();
  const companyId      = context.activeCompanyId();
  const targetsOurApi  = req.url.startsWith(environment.apiUrl);

  console.log('[interceptor]', req.url, { isSuperAdmin, companyId, targetsOurApi });
  if (isSuperAdmin && companyId && targetsOurApi) {
    const updated = req.clone({
      params: req.params.set('company_id', companyId),
    });
    return next(updated);
  }

  return next(req);
};
