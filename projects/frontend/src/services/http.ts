import axios from 'axios';
import type { AxiosError, InternalAxiosRequestConfig } from 'axios';

import { msg } from '@/utils/message';

import { getAuthToken } from './authToken';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/';

if (API_BASE_URL !== '/') {
  throw new Error('VITE_API_BASE_URL must be "/" so requests stay same-origin and are forwarded by nginx.');
}

/** 业务错误：HTTP 200 但 code != 0。 */
export class BizError extends Error {
  code: number;

  constructor(code: number, msg: string) {
    super(msg);
    this.code = code;
  }
}

export interface ApiResponse<T = unknown> {
  code: number;
  msg: string;
  data: T;
}

export const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15_000,
  headers: {
    'Content-Type': 'application/json',
  },
});

http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const requestId = crypto.randomUUID();
  const token = getAuthToken();

  config.headers.set('X-Request-Id', requestId);

  if (token) {
    config.headers.set('X-Auth-Token', token);
  }

  return config;
});

function isPublicPath(url?: string) {
  if (!url) return false;
  return url.includes('/api/public/') || url.includes('/api/auth/mock-login') || url.includes('/api/auth/mock-users');
}

/** 未登录时跳转到登录页（公开页与登录相关请求除外）。 */
function redirectToLogin() {
  const hash = window.location.hash || '';
  if (hash.startsWith('#/login') || hash.startsWith('#/public/')) return;
  window.location.hash = '#/login';
}

http.interceptors.response.use(
  (response) => {
    const body = response.data as ApiResponse | undefined;
    // 统一业务错误处理：code != 0 时提示并抛出 BizError
    if (body && typeof body.code === 'number' && body.code !== 0) {
      if (body.code !== 401) {
        msg.error(body.msg || '操作失败');
      }
      throw new BizError(body.code, body.msg || '操作失败');
    }
    return response;
  },
  (error: AxiosError<ApiResponse>) => {
    const status = error.response?.status;
    const body = error.response?.data;
    if (status === 401) {
      if (!isPublicPath(error.config?.url)) {
        redirectToLogin();
      }
    } else {
      msg.error(body?.msg || `请求失败（${status ?? '网络错误'}）`);
    }
    return Promise.reject(error);
  },
);

/** 解包 {code,msg,data}，返回 data。 */
export function unwrap<T>(response: { data: ApiResponse<T> }): T {
  return response.data.data;
}

/** 需要 X-Auth-Token 的受保护文件下载，不能使用普通 window.location。 */
async function protectedBlob(url: string, params?: Record<string, unknown>) {
  const response = await http.get(url, { params, responseType: 'blob' });
  const blob = response.data as Blob;
  if (blob.type.includes('application/json')) {
    const body = JSON.parse(await blob.text()) as ApiResponse;
    throw new BizError(body.code || 500, body.msg || '文件请求失败');
  }
  return blob;
}

export async function downloadProtectedFile(url: string, filename: string, params?: Record<string, unknown>) {
  const blob = await protectedBlob(url, params);
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.click();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

export async function openProtectedFile(url: string, params?: Record<string, unknown>) {
  const blob = await protectedBlob(url, params);
  const objectUrl = URL.createObjectURL(blob);
  window.open(objectUrl, '_blank', 'noopener,noreferrer');
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000);
}
