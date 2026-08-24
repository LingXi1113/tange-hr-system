import { http, unwrap } from './http';
import type { PagedData } from './template';

export interface AuditLog {
  id: number; biz_type: string; biz_id: string; action: string;
  operator_id: string; operator_name: string; detail: string; created_at: string;
}

export async function fetchAuditLogs(params: Record<string, unknown> = {}) {
  const resp = await http.get('/api/audit-logs', { params });
  return unwrap<PagedData<AuditLog>>(resp);
}
