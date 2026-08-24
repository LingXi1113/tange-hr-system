import { http, unwrap } from './http';
import type { SwitchableUser } from './user';

export interface MockUsersResponse {
  enabled: boolean;
  users: SwitchableUser[];
}

/** 登录页可选 Mock 用户列表（免登录；生产关闭 Mock 后 enabled=false）。 */
export async function fetchMockUsers(): Promise<MockUsersResponse> {
  const resp = await http.get('/api/auth/mock-users');
  return unwrap<MockUsersResponse>(resp);
}
