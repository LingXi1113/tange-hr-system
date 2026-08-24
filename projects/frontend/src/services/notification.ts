import { http, unwrap } from './http';
import type { PagedData } from './template';

export interface NotificationItem {
  id: number;
  scene: string;
  title: string;
  content: string;
  biz_type: string;
  biz_id: string;
  route: string;
  read_at: string;
  unread: boolean;
  created_at: string;
}

export const NOTIFICATION_SCENE_TEXT: Record<string, string> = {
  new_candidate: '新候选人',
  interview_remind: '面试提醒',
  feedback_pending: '反馈待填写',
  offer_expiring: 'Offer即将过期',
  stale_candidate: '长期未跟进',
  requirement_overdue: '需求逾期',
};

export async function fetchNotifications(params: Record<string, unknown> = {}) {
  const resp = await http.get('/api/notifications', { params });
  return unwrap<PagedData<NotificationItem>>(resp);
}

export async function fetchUnreadCount() {
  const resp = await http.get('/api/notifications/unread-count');
  return unwrap<{ count: number }>(resp);
}

export async function markNotificationRead(id: number) {
  const resp = await http.post(`/api/notifications/${id}/read`);
  return unwrap(resp);
}

export async function markAllNotificationsRead() {
  const resp = await http.post('/api/notifications/read-all');
  return unwrap<{ marked: number }>(resp);
}
