export const APP_NAME = 'Skvalves';

export const PAGINATION = {
  defaultPageSize: 20,
  pageSizeOptions: [10, 20, 50],
} as const;

export const UPLOAD = {
  maxFileSizeMb: 50,
  acceptedMimeTypes: ['application/pdf', 'image/png', 'image/jpeg'],
} as const;

export const LOCAL_STORAGE_KEYS = {
  token: 'sk_token',
  companyId: 'sk_company_id',
} as const;
