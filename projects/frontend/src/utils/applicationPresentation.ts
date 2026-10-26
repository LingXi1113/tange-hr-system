import type { Application } from '@/services/candidate';

const SOURCE_TEXT: Record<string, string> = {
  manual: 'HR录入', public: '公开投递', interview_arrangement: '面试安排',
  hr_direct_offer: 'HR直发Offer', import: '批量导入', job_change: 'HR更换职位',
};

export function applicationStatus(application: Pick<Application, 'status' | 'current_stage'>) {
  if (application.status === 'eliminated') return { label: '已淘汰', color: 'error' };
  if (application.status === 'onboarded') return { label: '已入职', color: 'success' };
  if (application.status === 'pending_onboard') return { label: '待入职', color: 'cyan' };
  if (application.status !== 'in_progress') return { label: '已归档', color: 'default' };
  if (/interview/.test(application.current_stage)) return { label: '面试中', color: 'blue' };
  return { label: '进行中', color: 'processing' };
}

export function deliverySource(source: string) { return SOURCE_TEXT[source] || source || '来源未填写'; }
