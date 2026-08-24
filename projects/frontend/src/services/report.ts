import { http, unwrap } from './http';

export interface ReportFilters {
  date_from?: string;
  date_to?: string;
  job_id?: number;
  dept_id?: string;
  owner_id?: string;
  source?: string;
  requirement_status?: string;
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
