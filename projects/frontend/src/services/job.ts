import { http, unwrap } from './http';
import type { PagedData } from './template';

export interface Job {
  id: number;
  code: string;
  name: string;
  dept_id: string;
  dept_name: string;
  location: string;
  job_type: string;
  level: string;
  report_to: string;
  headcount: number;
  salary_range: string;
  description: string;
  qualification: string;
  skill_tags: string;
  template_id: number | null;
  channels: string;
  interview_rounds: string[];
  status: string;
  requirement_id: number | null;
  owner_id: string;
  owner_name: string;
  public_token: string;
  public_url: string;
  stage_configs?: StageConfig[];
  application_count?: number;
  created_at: string;
  updated_at: string;
}

export interface StageConfig {
  stage_key: string;
  enabled: boolean;
  required: boolean;
  after_key: string;
}

export const JOB_STATUS_TEXT: Record<string, string> = {
  draft: '草稿', pending_publish: '待发布', recruiting: '招聘中', paused: '暂停招聘', closed: '已关闭',
};

export async function fetchJobs(params: Record<string, unknown> = {}) {
  const resp = await http.get('/api/jobs', { params });
  return unwrap<PagedData<Job>>(resp);
}

export async function fetchJob(id: number) {
  const resp = await http.get(`/api/jobs/${id}`);
  return unwrap<Job>(resp);
}

export async function saveJob(id: number | null, payload: Record<string, unknown>) {
  const resp = id
    ? await http.put(`/api/jobs/${id}`, payload)
    : await http.post('/api/jobs', payload);
  return unwrap<Job>(resp);
}

export async function jobAction(id: number, action: string) {
  const resp = await http.post(`/api/jobs/${id}/status`, { action });
  return unwrap<Job>(resp);
}

export async function copyJob(id: number) {
  const resp = await http.post(`/api/jobs/${id}/copy`);
  return unwrap<Job>(resp);
}

export interface PublicJob {
  name: string;
  location: string;
  job_type: string;
  level: string;
  headcount: number;
  salary_range: string;
  description: string;
  qualification: string;
  skill_tags: string;
  dept_name: string;
  status: string;
  accepting: boolean;
}

export async function fetchPublicJob(token: string) {
  const resp = await http.get(`/api/public/jobs/${token}`);
  return unwrap<PublicJob>(resp);
}

export async function applyPublicJob(token: string, form: FormData) {
  const resp = await http.post(`/api/public/jobs/${token}/apply`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return unwrap<{
    candidate_id: number;
    application_id: number;
    resume_parse_status: '' | 'system' | 'failed';
    resume_fields: {
      name: string;
      phone: string;
      email: string;
      city: string;
      education: { school?: string; major?: string; degree?: string; graduate_at?: string }[];
    };
  }>(resp);
}
