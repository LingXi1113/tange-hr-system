import { http, unwrap } from './http';

export interface DashboardTodoItem {
  key: string;
  title: string;
  count: number;
  route: string;
}

export interface DashboardActivity {
  id: number;
  biz_type: string;
  biz_id: string;
  action: string;
  operator_name: string;
  detail: string;
  created_at: string;
}

export interface DashboardSummary {
  todos: Record<string, number>;
  todo_items: DashboardTodoItem[];
  overview: Record<string, number>;
  funnel: { stage_key: string; name: string; count: number }[];
  notification_unread: number;
  recent_activities: DashboardActivity[];
  generated_at: string;
}

export async function fetchDashboardSummary() {
  const resp = await http.get('/api/dashboard/summary');
  return unwrap<DashboardSummary>(resp);
}
