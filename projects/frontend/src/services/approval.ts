import { http, unwrap } from './http';
import type { PagedData } from './template';

export interface ApprovalStep {
  key: string; name: string; role: string; approver_id: string; approver_name: string;
  status: string; reason: string; acted_at: string;
}

export interface ApprovalRecord {
  id: number; offer_id: number; candidate_id: number; candidate_name: string;
  job_id: number; job_name: string; position: string; salary: string; onboard_date: string;
  offer_status: string; status: string; current_step: string; current_step_name: string;
  steps: ApprovalStep[]; version: number; created_at: string; updated_at: string;
  deadline_at: string; overdue: boolean; days_remaining: number;
}

export async function fetchApprovals(params: Record<string, unknown> = {}) {
  const resp = await http.get('/api/approvals', { params });
  return unwrap<PagedData<ApprovalRecord>>(resp);
}

export async function approvalAction(id: number, payload: { action: 'approve' | 'reject'; version: number; reason?: string }) {
  const resp = await http.post(`/api/approvals/${id}/action`, payload);
  return unwrap<ApprovalRecord>(resp);
}
