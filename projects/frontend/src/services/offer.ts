import { http, unwrap } from './http';
import type { PagedData } from './template';

export interface OfferFileMeta {
  id: string;
  originalName: string;
  size: number;
  mimeType: string;
  url: string;
}

export interface Offer {
  id: number;
  candidate_id: number;
  candidate_name: string;
  job_id: number;
  job_name: string;
  application_id: number;
  dept: string;
  position: string;
  onboard_date: string;
  location: string;
  salary: string;
  probation: string;
  contract_term: string;
  benefits: string;
  valid_until: string;
  remark: string;
  status: string;
  response_reason: string;
  sent_at: string;
  responded_at: string;
  file: OfferFileMeta | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export const OFFER_STATUS_TEXT: Record<string, string> = {
  draft: '草稿', pending_send: '待发送', sent: '已发送', accepted: '已接受',
  rejected: '已拒绝', expired: '已过期', withdrawn: '已撤回',
};

export const OFFER_STATUS_COLOR: Record<string, string> = {
  draft: 'default', pending_send: 'gold', sent: 'processing', accepted: 'success',
  rejected: 'error', expired: 'warning', withdrawn: 'purple',
};

export async function fetchOffers(params: Record<string, unknown> = {}) {
  const resp = await http.get('/api/offers', { params });
  return unwrap<PagedData<Offer>>(resp);
}

export async function fetchOffer(id: number) {
  const resp = await http.get(`/api/offers/${id}`);
  return unwrap<Offer>(resp);
}

export async function saveOffer(id: number | null, payload: Record<string, unknown>) {
  const resp = id
    ? await http.put(`/api/offers/${id}`, payload)
    : await http.post('/api/offers', payload);
  return unwrap<Offer>(resp);
}

export async function offerAction(
  id: number,
  payload: { action: string; version: number; reason?: string },
) {
  const resp = await http.post(`/api/offers/${id}/status`, payload);
  return unwrap<Offer>(resp);
}

export async function uploadOfferFile(id: number, file: File) {
  const form = new FormData();
  form.append('file', file);
  const resp = await http.post(`/api/offers/${id}/file`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return unwrap<Offer>(resp);
}

/** 预览/下载地址（同源，走登录态 Cookie；后端签名/代理，不暴露密钥） */
export function offerPreviewUrl(id: number) {
  return `/api/offers/${id}/preview`;
}

export function offerDownloadUrl(id: number) {
  return `/api/offers/${id}/download`;
}
