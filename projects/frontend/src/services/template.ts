import { http, unwrap } from './http';

/** 流程模板 */
export interface TemplateStage {
  id?: number;
  stage_key: string;
  name: string;
  category: string;
  sort_order: number;
  lock_days: number;
  unprocessed_days: number;
  reminder_days_before: number;
  expiry_action: 'none' | 'eliminated' | 'abandoned' | 'talent_pool';
  deadline_basis: 'stage_entered' | 'planned_onboard_date';
  required: boolean;
  skippable: boolean;
  requires_interview: boolean;
  requires_feedback: boolean;
  auto_reminder: boolean;
  enter_talent_pool: boolean;
  reminder_type: string;
  optional_flag: boolean;
}

export interface PipelineTemplate {
  id: number;
  name: string;
  status: 'active' | 'disabled';
  remark: string;
  stage_rules_enabled: boolean;
  stage_count: number;
  created_at: string;
  updated_at: string;
  stages?: TemplateStage[];
}

export interface PagedData<T> {
  list: T[];
  total: number;
  page: number;
  page_size: number;
}

export async function fetchPipelineTemplates(page = 1, pageSize = 20): Promise<PagedData<PipelineTemplate>> {
  const resp = await http.get('/api/pipeline-templates', { params: { page, page_size: pageSize } });
  return unwrap<PagedData<PipelineTemplate>>(resp);
}

export async function fetchPipelineTemplate(id: number): Promise<PipelineTemplate> {
  const resp = await http.get(`/api/pipeline-templates/${id}`);
  return unwrap<PipelineTemplate>(resp);
}

export async function savePipelineTemplate(
  id: number | null,
  payload: { name: string; remark?: string; stage_rules_enabled?: boolean; stages: TemplateStage[] },
): Promise<PipelineTemplate> {
  const resp = id
    ? await http.put(`/api/pipeline-templates/${id}`, payload)
    : await http.post('/api/pipeline-templates', payload);
  return unwrap<PipelineTemplate>(resp);
}

export async function setPipelineTemplateStatus(id: number, status: 'active' | 'disabled') {
  const resp = await http.put(`/api/pipeline-templates/${id}/status`, { status });
  return unwrap(resp);
}

export async function deletePipelineTemplate(id: number) {
  const resp = await http.delete(`/api/pipeline-templates/${id}`);
  return unwrap(resp);
}

/** 阶段元数据（与后端 common/stages.py 对应） */
export const STAGE_META: { key: string; name: string; category: string; optional: boolean }[] = [
  { key: 'new_resume', name: '未处理简历', category: '开始', optional: false },
  { key: 'pending_screen', name: '业务复筛', category: '筛选', optional: false },
  { key: 'hr_screen_passed', name: 'HR筛选通过', category: '筛选', optional: false },
  { key: 'pending_interview', name: '待面试', category: '面试', optional: false },
  { key: 'interviewing', name: '面试阶段', category: '面试', optional: false },
  { key: 'interview_passed', name: '录用审批', category: '审批', optional: false },
  { key: 'offer_pending', name: '发送Offer', category: 'Offer', optional: false },
  { key: 'written_test', name: '笔试', category: '可选插入', optional: true },
  { key: 'assessment', name: '测评', category: '可选插入', optional: true },
  { key: 'interview_1', name: '一面', category: '面试', optional: false },
  { key: 'interview_2', name: '二面', category: '面试', optional: false },
  { key: 'interview_3', name: '三面', category: '面试', optional: false },
  { key: 're_interview', name: '复试', category: '可选插入', optional: true },
  { key: 'hr_interview', name: 'HR面试', category: '面试', optional: false },
  { key: 'background_check', name: '背调', category: '可选插入', optional: true },
  { key: 'offer_approval', name: '录用审批', category: '审批', optional: false },
  { key: 'offer', name: 'Offer', category: 'Offer', optional: false },
  { key: 'pending_onboard', name: '待入职', category: '入职', optional: false },
  { key: 'onboarded', name: '入职', category: '结束', optional: false },
  { key: 'custom', name: '自定义', category: '可选插入', optional: true },
];

export const REMINDER_OPTIONS = [
  { value: '', label: '不提醒' },
  { value: 'enter', label: '进入提醒' },
  { value: 'offer_expire', label: '过期提醒' },
  { value: 'onboard', label: '入职提醒' },
];

export const EXPIRY_ACTION_OPTIONS = [
  { value: 'none', label: '不处理' },
  { value: 'eliminated', label: '自动淘汰' },
  { value: 'abandoned', label: '自动放弃' },
  { value: 'talent_pool', label: '进入人才库' },
];

export const DEADLINE_BASIS_OPTIONS = [
  { value: 'stage_entered', label: '进入阶段起算' },
  { value: 'planned_onboard_date', label: '入职日期起算' },
];

/** 面试评价模板 */
export interface EvalBinding {
  id?: number;
  job_id: string;
  job_name: string;
  round: string;
}

export interface EvalTemplate {
  id: number;
  name: string;
  remark: string;
  dimension_names: string[];
  jobs: string[];
  rounds: string[];
  updated_at: string;
  dimensions?: { id: number; name: string; sort_order: number }[];
  bindings?: EvalBinding[];
}

export const INTERVIEW_ROUNDS = ['一面', '二面', '三面', 'HR面试', '复试'];

export async function fetchEvalTemplates(params: { keyword?: string; round?: string; page?: number } = {}) {
  const resp = await http.get('/api/eval-templates', { params });
  return unwrap<PagedData<EvalTemplate>>(resp);
}

export async function fetchEvalTemplate(id: number): Promise<EvalTemplate> {
  const resp = await http.get(`/api/eval-templates/${id}`);
  return unwrap<EvalTemplate>(resp);
}

export async function saveEvalTemplate(
  id: number | null,
  payload: { name: string; remark?: string; dimensions: string[]; bindings: EvalBinding[] },
): Promise<EvalTemplate> {
  const resp = id
    ? await http.put(`/api/eval-templates/${id}`, payload)
    : await http.post('/api/eval-templates', payload);
  return unwrap<EvalTemplate>(resp);
}

export async function deleteEvalTemplate(id: number) {
  const resp = await http.delete(`/api/eval-templates/${id}`);
  return unwrap(resp);
}
