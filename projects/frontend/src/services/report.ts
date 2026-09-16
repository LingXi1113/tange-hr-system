import { http, unwrap } from './http';

export interface ReportFilters {
  date_from?: string;
  date_to?: string;
  job_id?: number;
  dept_id?: string;
  owner_id?: string;
  source?: string;
  requirement_status?: string;
  job_status?: string;
  template_id?: number;
  requirement_id?: number;
  job_date_from?: string;
  job_date_to?: string;
  interviewer_name?: string;
  interviewer_dept?: string;
  resume_status?: string;
  headhunter_supplier?: string;
  portal_plan?: string;
}

export interface JobProgressReport {
  summary: {
    received: number;
    recommended: number;
    scheduled: number;
    interviewed: number;
    offered: number;
    pending_onboard: number;
    onboarded: number;
    regularized: number;
    active_jobs: number;
    completion_rate: number;
    onboarding_cycle: number;
  };
  rankings: Record<string, { name: string; value: number }[]>;
  rows: {
    job_id: number;
    job_name: string;
    owner_id: string;
    owner_name: string;
    dept_id: string;
    dept_name: string;
    location: string;
    job_type: string;
    status: string;
    headcount: number;
    completion_rate: number;
    onboarding_cycle: number;
    received: number;
    recommended: number;
    scheduled: number;
    interviewed: number;
    offered: number;
    pending_onboard: number;
    onboarded: number;
    regularized: number;
  }[];
}

export interface ChannelEffectReport {
  summary: {
    active_channels: number;
    applications: number;
    offers: number;
    pending_onboard: number;
    onboarded: number;
    onboarding_cycle: number;
  };
  rows: {
    source: string;
    applications: number;
    candidates: number;
    interviews: number;
    offers: number;
    onboarded: number;
    interview_rate: number;
    offer_rate: number;
    onboard_rate: number;
  }[];
  attrition: { name: string; value: number }[];
}

export interface StageFunnelReport {
  total: number;
  stage_funnel: {
    stage_key: string;
    name: string;
    count: number;
    previous_rate: number;
    overall_rate: number;
  }[];
  interview_funnel: {
    name: string;
    count: number;
    previous_rate: number;
    overall_rate: number;
  }[];
  current_stages: {
    stage_key: string;
    name: string;
    count: number;
  }[];
}

export interface InterviewerEfficiencyReport {
  summary: {
    recommended: number;
    feedback: number;
    feedback_rate: number;
    attended: number;
    interview_feedback: number;
    interview_feedback_rate: number;
  };
  rows: {
    name: string;
    recommended: number;
    feedback: number;
    passed: number;
    failed: number;
    held: number;
    no_feedback: number;
    attended: number;
    interview_feedback: number;
    feedback_rate: number;
    interview_feedback_rate: number;
    pass_rate: number;
    feedback_hours: number;
  }[];
}

export interface TalentProfileReport {
  total: number;
  gender: { name: string; value: number }[];
  work_experience: { name: string; value: number }[];
  age: { name: string; value: number }[];
  highest_education: { name: string; value: number }[];
  channel_type: { name: string; value: number }[];
  graduation_school: { name: string; value: number }[];
  latest_employer: { name: string; value: number }[];
  profession: { name: string; value: number }[];
}

export interface RequirementReport {
  summary: Record<string, number>;
  rows: {
    id: number; code: string; name: string; dept_name: string; status: string;
    headcount: number; due_date: string; job_count: number; candidate_count: number; overdue: boolean;
  }[];
}

export interface FunnelReport {
  total: number;
  stage_counts: { stage_key: string; name: string; count: number }[];
  rows: { stage_key: string; name: string; count: number }[];
}

export interface ChannelReport {
  total: number;
  rows: {
    source: string; applications: number; candidates: number; interviews: number;
    offers: number; onboarded: number; interview_rate: number; offer_rate: number; onboard_rate: number;
  }[];
}

export interface CycleReport {
  sample_count: number;
  metrics: {
    avg_recruitment_days: number;
    avg_screening_days: number;
    avg_interview_days: number;
    avg_offer_to_onboard_days: number;
  };
}

function params(filters: ReportFilters) {
  return Object.fromEntries(Object.entries(filters).filter(([, value]) => value !== undefined && value !== null && value !== ''));
}

export async function fetchRequirementsReport() {
  const resp = await http.get('/api/reports/requirements');
  return unwrap<RequirementReport>(resp);
}

export async function fetchFunnelReport(filters: ReportFilters) {
  const resp = await http.get('/api/reports/funnel', { params: params(filters) });
  return unwrap<FunnelReport>(resp);
}

export async function fetchChannelReport(filters: ReportFilters) {
  const resp = await http.get('/api/reports/channels', { params: params(filters) });
  return unwrap<ChannelReport>(resp);
}

export async function fetchCycleReport(filters: ReportFilters) {
  const resp = await http.get('/api/reports/cycle', { params: params(filters) });
  return unwrap<CycleReport>(resp);
}

export async function fetchJobProgressReport(filters: ReportFilters) {
  const resp = await http.get('/api/reports/job-progress', { params: params(filters) });
  return unwrap<JobProgressReport>(resp);
}

export async function fetchChannelEffectReport(filters: ReportFilters) {
  const resp = await http.get('/api/reports/channel-effect', { params: params(filters) });
  return unwrap<ChannelEffectReport>(resp);
}

export async function fetchStageFunnelReport(filters: ReportFilters) {
  const resp = await http.get('/api/reports/stage-funnel', { params: params(filters) });
  return unwrap<StageFunnelReport>(resp);
}

export async function fetchInterviewerEfficiencyReport(filters: ReportFilters) {
  const resp = await http.get('/api/reports/interviewer-efficiency', { params: params(filters) });
  return unwrap<InterviewerEfficiencyReport>(resp);
}

export async function fetchTalentProfileReport(filters: ReportFilters) {
  const resp = await http.get('/api/reports/talent-profile', { params: params(filters) });
  return unwrap<TalentProfileReport>(resp);
}

export async function downloadReport(type: string, filters: ReportFilters) {
  const resp = await http.get('/api/reports/export', {
    params: { type, ...params(filters) },
    responseType: 'blob',
  });
  const url = URL.createObjectURL(resp.data);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `hr-report-${type}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}
