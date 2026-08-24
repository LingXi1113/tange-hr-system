import { http, unwrap } from './http';
import type { PagedData } from './template';

export interface PoolEntry {
  id: number;
  candidate_id: number;
  candidate_name: string;
  phone: string;
  email: string;
  category: string;
  tags: string[];
  source: string;
  source_text: string;
  reason: string;
  recommended_job_id: number | null;
  recommended_job_name: string;
  last_contact_at: string;
  status: string;
  created_at: string;
}

export const POOL_SOURCE_TEXT: Record<string, string> = {
  elimination_added: '淘汰加入', offer_rejected: 'Offer拒绝加入',
  manual: '手动加入', batch_import: '批量导入', archived: '流程归档',
};

export async function fetchPool(params: Record<string, unknown> = {}) {
  const resp = await http.get('/api/talent-pool', { params });
  return unwrap<PagedData<PoolEntry>>(resp);
}

export async function addToPool(payload: {
  candidate_id?: number; candidate_ids?: number[];
  category?: string; tags?: string[]; source?: string; reason?: string;
  recommended_job_id?: number | null;
}) {
  const resp = await http.post('/api/talent-pool', payload);
  return unwrap<{ added: PoolEntry[]; duplicates: { candidate_id: number; msg: string }[]; missing: unknown[] }>(resp);
}

export async function updatePoolEntry(id: number, payload: Record<string, unknown>) {
  const resp = await http.put(`/api/talent-pool/${id}`, payload);
  return unwrap<PoolEntry>(resp);
}

export async function removeFromPool(id: number) {
  const resp = await http.delete(`/api/talent-pool/${id}`, { params: { confirm: 1 } });
  return unwrap(resp);
}

export async function batchRemoveFromPool(entryIds: number[]) {
  const resp = await http.post('/api/talent-pool/batch-remove', { entry_ids: entryIds });
  return unwrap<{ removed: number }>(resp);
}

export async function batchPoolTags(entryIds: number[], tags: string[], mode: 'replace' | 'append') {
  const resp = await http.post('/api/talent-pool/batch-tags', { entry_ids: entryIds, tags, mode });
  return unwrap<{ updated: number }>(resp);
}

export async function activatePoolEntry(id: number, jobId: number) {
  const resp = await http.post(`/api/talent-pool/${id}/activate`, { job_id: jobId });
  return unwrap<{ application_id: number; entry: PoolEntry }>(resp);
}
