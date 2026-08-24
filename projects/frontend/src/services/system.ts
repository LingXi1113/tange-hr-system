import { http, unwrap } from './http';

/** 系统参数 */
export interface SystemParams {
  lock_days_default: Record<string, number>;
  onboarding_checklist_default: string[];
}

export async function fetchSystemParams(): Promise<SystemParams> {
  const resp = await http.get('/api/system/params');
  return unwrap<SystemParams>(resp);
}

export async function updateSystemParams(items: { key: string; value: unknown }[]) {
  const resp = await http.put('/api/system/params', { items });
  return unwrap(resp);
}

/** 字典 */
export interface DictItem {
  id: number;
  type: string;
  code: string;
  name: string;
  enabled: boolean;
  sort: number;
}

export const DICT_TYPE_OPTIONS = [
  { value: 'source_channel', label: '来源渠道' },
  { value: 'request_type', label: '需求类型' },
  { value: 'job_level', label: '职级' },
  { value: 'eliminate_reason', label: '淘汰原因' },
  { value: 'pool_category', label: '人才库分类' },
  { value: 'job_type', label: '职位类型' },
];

export async function fetchDicts(type: string): Promise<DictItem[]> {
  const resp = await http.get('/api/system/dicts', { params: { type } });
  return unwrap<DictItem[]>(resp);
}

export async function createDict(payload: { type: string; code: string; name: string }) {
  const resp = await http.post('/api/system/dicts', payload);
  return unwrap<DictItem>(resp);
}

export async function updateDict(id: number, payload: Partial<Pick<DictItem, 'name' | 'enabled' | 'sort'>>) {
  const resp = await http.put(`/api/system/dicts/${id}`, payload);
  return unwrap<DictItem>(resp);
}

/** Offer 审批人配置 */
export interface ApproverRef {
  user_id: string;
  name: string;
}

export interface OfferApproverConfig {
  org_approver: ApproverRef;
  gm: ApproverRef;
  chairman: ApproverRef;
  offer_sender: ApproverRef;
  updated_at: string;
}

export async function fetchOfferApprovers(): Promise<OfferApproverConfig> {
  const resp = await http.get('/api/system/offer-approvers');
  return unwrap<OfferApproverConfig>(resp);
}

export async function updateOfferApprovers(payload: {
  org_approver_id: string;
  gm_id: string;
  chairman_id: string;
  offer_sender_id: string;
}) {
  const resp = await http.put('/api/system/offer-approvers', payload);
  return unwrap<OfferApproverConfig>(resp);
}

/** 平台成员（审批人/负责人选择） */
export interface PlatformUser {
  user_id: string;
  name: string;
  role: string;
  role_name: string;
  dept_name: string;
}

export async function fetchPlatformUsers(keyword = ''): Promise<PlatformUser[]> {
  const resp = await http.get('/api/platform/users', { params: { keyword } });
  return unwrap<PlatformUser[]>(resp);
}


/** 平台部门树（Mock 平台） */
export interface PlatformDepartment {
  dept_id: string;
  name: string;
  parent_id: string;
}

export async function fetchDepartments(): Promise<PlatformDepartment[]> {
  const resp = await http.get('/api/platform/departments');
  return unwrap<PlatformDepartment[]>(resp);
}
