import { clearAuthToken, saveAuthToken } from './authToken';
import { http } from './http';

const EMBEDDED_TRACKING_FALLBACK_USER_STORAGE_KEY =
  'jahead_tracking_embedded_fallback_user_id';

export interface BackendUserProfile extends Record<string, unknown> {
  _id?: string;
  company_id?: string;
  company_user_id?: string;
  indi_user_id?: string;
  individual_user_id?: string;
  name?: string;
}

export interface BackendUser {
  company_id: string;
  company_user_id: string;
  individual_user_id: string;
  name: string;
  profile: BackendUserProfile;
}

export interface BackendResponse<T> {
  stat: 0 | 1;
  msg?: string;
  data?: T;
}

export interface SsoLoginResponse extends BackendResponse<BackendUser> {
  token?: string;
}

let cachedCurrentUser: BackendUser | undefined;

function normalizeUserId(value: unknown) {
  return typeof value === 'string' && value ? value : undefined;
}

export function resolveCompanyUserId(user?: BackendUser | null) {
  if (!user) {
    return undefined;
  }

  return normalizeUserId(user.company_user_id) ?? normalizeUserId(user.profile?.company_user_id);
}

export function getCachedCurrentUser() {
  return cachedCurrentUser;
}

export function getCachedCompanyUserId() {
  return resolveCompanyUserId(cachedCurrentUser);
}

export function getOrCreateEmbeddedTrackingFallbackUserId() {
  try {
    const cachedUserId = localStorage.getItem(EMBEDDED_TRACKING_FALLBACK_USER_STORAGE_KEY);

    if (cachedUserId) {
      return cachedUserId;
    }

    const userId = crypto.randomUUID();
    localStorage.setItem(EMBEDDED_TRACKING_FALLBACK_USER_STORAGE_KEY, userId);
    return userId;
  } catch {
    return crypto.randomUUID();
  }
}

export async function loginBySsoCode(code: string) {
  const response = await http.post<SsoLoginResponse>('/api/auth/sso/login', { code });
  const result = response.data;

  if (result.stat !== 1 || !result.data) {
    throw new Error(result.msg || 'SSO login failed.');
  }

  if (result.token) {
    saveAuthToken(result.token);
  }

  cachedCurrentUser = result.data;

  return result;
}

export async function logout() {
  try {
    await http.post<BackendResponse<null>>('/api/auth/logout');
  } finally {
    cachedCurrentUser = undefined;
    clearAuthToken();
  }
}
