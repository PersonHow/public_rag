export const API_BASE = '/api';

export const API_ROUTES = {
  auth: {
    login: `${API_BASE}/auth/login`,
    logout: `${API_BASE}/auth/logout`,
    me: `${API_BASE}/auth/me`,
  },
  sessions: `${API_BASE}/sessions`,
  documents: `${API_BASE}/documents`,
  companies: `${API_BASE}/companies`,
  users: `${API_BASE}/users`,
} as const;
