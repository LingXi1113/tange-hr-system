import { http, unwrap } from './http';

export type ScreeningDecision = 'pass' | 'pending' | 'reject' | 'insufficient';
export type ScreeningReviewDecision = 'pass' | 'pending' | 'reject';

export interface ScreeningDimension {
  name: string;
  score: number;
  max_score: number;
  status: 'matched' | 'partial' | 'missing' | 'not_configured';
  matched: string[];
  missing: string[];
  evidence: string[];
}

export interface ScreeningRules {
  profile: 'tech' | 'product_ops' | 'sales';
  profile_name: string;
  min_education: string;
  min_work_years: number;
  required_skills: string[];
  preferred_skills: string[];
  hard_skills: string[];
  industry_tags: string[];
  pass_score: number;
  pending_score: number;
  weights: Record<string, number>;
}

export interface ScreeningResult {
  id: number;
  application_id: number | null;
  candidate_id: number;
  job_id: number | null;
  job_name: string;
  match_mode: 'application' | 'job_preview';
  profile: string;
  profile_name: string;
  match_template: string;
  match_template_name: string;
  score: number;
  decision: ScreeningDecision;
  decision_label: string;
  assessed_weight: number;
  dimensions: ScreeningDimension[];
  matched_items: string[];
  missing_items: string[];
  risk_items: string[];
  summary: string;
  rules: ScreeningRules;
  review_status: 'pending' | 'reviewed';
  review_decision: ScreeningReviewDecision | '';
  review_note: string;
  reviewer_id: string;
  reviewer_name: string;
  reviewed_at: string;
  route_action: '' | 'business_screen' | 'interview';
  route_label: string;
  routed_at: string;
  created_at: string;
}

export interface ScreeningProfile {
  key: string;
  name: string;
  base_profile: string;
  group: '通用模板' | '具体岗位';
  weights: Record<string, number>;
  items: Array<Record<string, unknown>>;
}

export async function fetchScreeningResult(applicationId: number) {
  const response = await http.get(`/api/applications/${applicationId}/screening-result`);
  return unwrap<ScreeningResult | null>(response);
}

export async function runScreening(applicationId: number) {
  const response = await http.post(`/api/applications/${applicationId}/screen`);
  return unwrap<ScreeningResult>(response);
}

export async function fetchScreeningProfiles() {
  const response = await http.get('/api/screening/profiles');
  return unwrap<ScreeningProfile[]>(response);
}

export async function previewCandidateJobMatch(
  candidateId: number,
  target: { job_id?: number; match_template?: string },
) {
  const response = await http.post(`/api/candidates/${candidateId}/job-match`, target);
  return unwrap<ScreeningResult>(response);
}

export async function reviewScreening(
  applicationId: number,
  decision: ScreeningReviewDecision,
  note = '',
) {
  const response = await http.post(`/api/applications/${applicationId}/screening-review`, {
    decision,
    note,
  });
  return unwrap<ScreeningResult>(response);
}
