import { http, unwrap } from './http';
import type { PagedData } from './template';

export interface Interview {
  id: number;
  candidate_id: number;
  candidate_name: string;
  job_id: number;
  job_name: string;
  application_id: number;
  round: string;
  type: string;
  start_at: string;
  end_at: string;
  location: string;
  meeting_link: string;
  interviewer_name: string;
  interviewer_contact: string;
  template_id: number | null;
  remark: string;
  status: string;
  version: number;
  has_feedback?: boolean;
  feedback_conclusion?: string;
  feedback_skip_eval?: boolean;
  feedback?: InterviewFeedback | null;
  reschedule_history: { from_start: string; to_start: string; reason: string; operator_name: string; at: string }[];
  created_at: string;
}

export interface InterviewFeedback {
  id: number;
  interview_id: number;
  dimension_scores: { name: string; score: number }[];
  conclusion: string;
  comment: string;
  risk_note: string;
  suggested_salary: string;
  evaluator_name: string;
  skip_eval: boolean;
  version: number;
  created_at: string;
}

export const INTERVIEW_STATUS_TEXT: Record<string, string> = {
  pending: '待安排', invited: '已邀请', confirmed: '已确认',
  completed: '已完成', cancelled: '已取消', rescheduled: '已改期',
};

export const INTERVIEW_TYPE_TEXT: Record<string, string> = {
  onsite: '现场', video: '视频', phone: '电话',
};

export const INTERVIEW_ROUND_OPTIONS = ['一面', '二面', '三面', 'HR面试', '复试'];

export async function fetchInterviews(params: Record<string, unknown> = {}) {
  const resp = await http.get('/api/interviews', { params });
  return unwrap<PagedData<Interview>>(resp);
}

export async function fetchInterview(id: number) {
  const resp = await http.get(`/api/interviews/${id}`);
  return unwrap<Interview>(resp);
}

export async function saveInterview(id: number | null, payload: Record<string, unknown>) {
  const resp = id
    ? await http.put(`/api/interviews/${id}`, payload)
    : await http.post('/api/interviews', payload);
  return unwrap<Interview>(resp);
}

export async function interviewAction(id: number, action: string, version: number) {
  const resp = await http.post(`/api/interviews/${id}/status`, { action, version });
  return unwrap<Interview>(resp);
}

export async function rescheduleInterview(id: number, payload: { start_at: string; end_at: string; reason: string; version: number }) {
  const resp = await http.post(`/api/interviews/${id}/reschedule`, payload);
  return unwrap<Interview>(resp);
}

export async function completeInterview(id: number, skipEval: boolean, version: number) {
  const resp = await http.post(`/api/interviews/${id}/complete`, { skip_eval: skipEval, version });
  return unwrap<Interview>(resp);
}

export async function saveFeedback(id: number, payload: Record<string, unknown>) {
  const resp = await http.post(`/api/interviews/${id}/feedback`, payload);
  return unwrap<InterviewFeedback>(resp);
}

export async function applyConclusion(id: number, payload: { version: number; reason?: string }) {
  const resp = await http.post(`/api/interviews/${id}/apply-conclusion`, payload);
  return unwrap<{ action: string; application: { id: number; current_stage: string; status: string } }>(resp);
}
