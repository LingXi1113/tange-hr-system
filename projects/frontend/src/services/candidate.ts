import { http, unwrap } from './http';
import type { PagedData } from './template';

export interface ApplicationInfo {
  id: number;
  job_name: string;
  current_stage: string;
  status: string;
}

export interface LockInfo {
  stage_key: string;
  start_at: string;
  end_at: string;
}

export interface CandidateRow {
  id: number;
  name: string;
  gender: string;
  phone: string;
  email: string;
  city: string;
  tags: string;
  source: string;
  owner_name: string;
  current_stage: string;
  created_at: string;
  version: number;
  latest_application: ApplicationInfo | null;
  lock: LockInfo | null;
}

export interface Application extends ApplicationInfo {
  candidate_id: number;
  candidate_name: string;
  job_id: number;
  source: string;
  owner_name: string;
  business_screener_id?: string;
  business_screener_name?: string;
  stage_entered_at: string;
  eliminate_reason: string;
  expected_salary: string;
  onboard_time: string;
  interview_round?: string;
  version: number;
}

export interface CandidateDetail extends CandidateRow {
  education: { school?: string; major?: string; degree?: string; graduate_at?: string }[];
  work_experience: { company?: string; position?: string; start?: string; end?: string; desc?: string }[];
  remark: string;
  attachments: { id: number; file_name: string; file_type: string; parse_status: string; created_at: string }[];
  applications: Application[];
  screening_records: {
    type: 'stage' | 'recommendation' | 'interview_reschedule';
    category: 'recommendation' | 'interview' | 'offer';
    title: string;
    from_stage: string;
    to_stage: string;
    operator_name: string;
    detail: string;
    created_at: string;
  }[];
}

export async function fetchCandidates(params: Record<string, unknown> = {}) {
  const resp = await http.get('/api/candidates', { params });
  return unwrap<PagedData<CandidateRow>>(resp);
}

export async function fetchCandidate(id: number) {
  const resp = await http.get(`/api/candidates/${id}`);
  return unwrap<CandidateDetail>(resp);
}

export interface DeliveryAnalysis {
  summary: {
    total_deliveries: number;
    highest_stage: string;
    interviews: number;
    evaluated_interviews: number;
    passed_interviews: number;
    interview_pass_rate: number;
  };
  applications: (Application & {
    created_at: string;
    stage_name: string;
    highest_stage_name: string;
    transitions: {
      from_stage: string;
      to_stage: string;
      to_stage_name: string;
      reason: string;
      operator_name: string;
      created_at: string;
    }[];
    interviews: {
      id: number;
      round: string;
      status: string;
      interviewer_name: string;
      start_at: string;
      conclusion: string;
    }[];
  })[];
  activities: {
    id: string;
    kind: 'resume' | 'operation';
    title: string;
    detail: string;
    operator_name: string;
    job_name: string;
    created_at: string;
  }[];
}

export async function fetchDeliveryAnalysis(id: number) {
  const resp = await http.get(`/api/candidates/${id}/delivery-analysis`);
  return unwrap<DeliveryAnalysis>(resp);
}

export interface DuplicateResult {
  duplicated: boolean;
  duplicates?: CandidateRow[];
  candidate?: CandidateRow;
}

export async function saveCandidate(id: number | null, payload: Record<string, unknown>) {
  const resp = id
    ? await http.put(`/api/candidates/${id}`, payload)
    : await http.post('/api/candidates', payload);
  return unwrap<DuplicateResult>(resp);
}

export async function deleteCandidate(id: number, hard = true) {
  const resp = await http.delete(`/api/candidates/${id}`, { params: { confirm: 1, hard: hard ? 1 : 0 } });
  return unwrap(resp);
}

export async function assignJob(candidateId: number, jobId: number, source = 'manual') {
  const resp = await http.post(`/api/candidates/${candidateId}/applications`, {
    job_id: jobId, source,
  });
  return unwrap<Application>(resp);
}

export async function assignBusinessScreener(applicationId: number, businessScreenerId: string, version: number) {
  const resp = await http.post(`/api/applications/${applicationId}/assign-business`, {
    business_screener_id: businessScreenerId, version,
  });
  return unwrap<Application>(resp);
}

export async function directInterview(applicationId: number, version: number) {
  const resp = await http.post(`/api/applications/${applicationId}/direct-interview`, { version });
  return unwrap<Application>(resp);
}

export async function enterNextInterview(applicationId: number, version: number) {
  const resp = await http.post(`/api/applications/${applicationId}/next-interview`, { version });
  return unwrap<Application>(resp);
}

export async function fetchTransitions(applicationId: number) {
  const resp = await http.get(`/api/applications/${applicationId}/transitions`);
  return unwrap<{ from_stage: string; to_stage: string; reason: string; operator_name: string; created_at: string }[]>(resp);
}

export async function unlockApplication(applicationId: number, reason: string) {
  const resp = await http.post(`/api/applications/${applicationId}/unlock`, { reason });
  return unwrap(resp);
}

export async function importCandidates(file: File) {
  const form = new FormData();
  form.append('file', file);
  const resp = await http.post('/api/candidates/import', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return unwrap<{ success_count: number; duplicates: { row: number; name: string }[]; errors: { row: number; msg: string }[] }>(resp);
}

export async function parseResumeUpload(file: File) {
  const form = new FormData();
  form.append('file', file);
  const resp = await http.post('/api/resume/parse-upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return unwrap<{
    file_name: string;
    parse_status: 'system' | 'failed';
    fields: {
      name: string;
      gender: string;
      phone: string;
      email: string;
      city: string;
      education: { school?: string; major?: string; degree?: string; graduate_at?: string }[];
      work_experience: { company?: string; position?: string; start?: string; end?: string; desc?: string }[];
    };
    message: string;
  }>(resp);
}

export async function uploadResume(file: File, candidateId?: number) {
  const form = new FormData();
  form.append('file', file);
  if (candidateId) form.append('candidate_id', String(candidateId));
  const resp = await http.post('/api/resume/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return unwrap<{ attachment_id: number; file_name: string }>(resp);
}

export async function parseResume(attachmentId: number) {
  const resp = await http.post('/api/resume/parse', { attachment_id: attachmentId });
  return unwrap<{
    parse_status: string;
    fields: {
      name?: string;
      gender?: string;
      phone?: string;
      email?: string;
      city?: string;
      education?: { school?: string; major?: string; degree?: string; graduate_at?: string }[];
      work_experience?: { company?: string; position?: string; start?: string; end?: string; desc?: string }[];
    };
    message: string;
  }>(resp);
}
