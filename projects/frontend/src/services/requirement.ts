import { http, unwrap } from './http';
import type { PagedData } from './template';

export interface Requirement {
  id: number;
  name: string;
  dept_id: string;
  dept_name: string;
  headcount: number;
  request_type: string;
  priority: string;
  due_date: string;
  owner_id: string;
  owner_name: string;
  reason: string;
  requirements: string;
  remark: string;
  status: string;
  job_id?: number | null;
  created_at: string;
  updated_at: string;
}

export interface RequirementDetail extends Requirement {
  jobs: { id: number; name: string; code: string; status: string; headcount: number }[];
  candidate_stats: { total: number; stage_distribution: Record<string, number> };
  operation_logs: { action: string; operator_name: string; detail: string; created_at: string }[];
}

export const REQ_STATUS_TEXT: Record<string, string> = {
  draft: '草稿', pending_confirm: '待确认', recruiting: '招聘中',
  paused: '暂停', completed: '已完成', closed: '已关闭',
};

export async function fetchRequirements(params: Record<string, unknown> = {}) {
  const resp = await http.get('/api/requirements', { params });
  return unwrap<PagedData<Requirement>>(resp);
}

export async function fetchRequirement(id: number) {
  const resp = await http.get(`/api/requirements/${id}`);
  return unwrap<RequirementDetail>(resp);
}

export async function saveRequirement(id: number | null, payload: Record<string, unknown>) {
  const resp = id
    ? await http.put(`/api/requirements/${id}`, payload)
    : await http.post('/api/requirements', payload);
  return unwrap<Requirement>(resp);
}

export async function requirementAction(id: number, action: string) {
  const resp = await http.post(`/api/requirements/${id}/${action}`);
  return unwrap<Requirement>(resp);
}
