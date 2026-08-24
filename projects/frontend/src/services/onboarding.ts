import { http, unwrap } from './http';
import type { PagedData } from './template';

export interface OnboardingItem {
  key: string; name: string; status: string; remark: string; updated_at: string; verified_at: string;
}

export interface OnboardingRecord {
  id: number; application_id: number; candidate_id: number; candidate_name: string;
  job_id: number; job_name: string; offer_id: number | null; planned_date: string;
  application_stage: string; status: string; checklist: OnboardingItem[];
  completed_count: number; total_count: number; notes: string; owner_id: string; owner_name: string;
  offer_position: string; version: number; created_at: string; updated_at: string;
}

export async function fetchOnboarding(params: Record<string, unknown> = {}) {
  const resp = await http.get('/api/onboarding', { params });
  return unwrap<PagedData<OnboardingRecord>>(resp);
}

export async function fetchOnboardingDetail(id: number) {
  const resp = await http.get(`/api/onboarding/${id}`);
  return unwrap<OnboardingRecord>(resp);
}

export async function startOnboarding(id: number, version: number) {
  const resp = await http.post(`/api/onboarding/${id}/start`, { version });
  return unwrap<OnboardingRecord>(resp);
}

export async function updateOnboardingItem(id: number, key: string, payload: { status: string; remark?: string; version: number }) {
  const resp = await http.post(`/api/onboarding/${id}/items/${key}`, payload);
  return unwrap<OnboardingRecord>(resp);
}

export async function completeOnboarding(id: number, version: number) {
  const resp = await http.post(`/api/onboarding/${id}/complete`, { version });
  return unwrap<OnboardingRecord>(resp);
}
