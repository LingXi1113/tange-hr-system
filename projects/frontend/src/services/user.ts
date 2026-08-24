import { useSyncExternalStore } from 'react';

import { clearAuthToken, saveAuthToken } from './authToken';
import { http, unwrap } from './http';

export interface SwitchableUser {
  user_id: string;
  name: string;
  role: string;
  role_name: string;
  dept_name?: string;
}

export interface CurrentUser {
  user_id: string;
  name: string;
  role: string;
  role_name: string;
  roles: string[];
  dept_id: string;
  dept_name: string;
  company_id: string;
  mock_mode: boolean;
  switchable_users?: SwitchableUser[];
  token?: string;
}

export interface UserState {
  user: CurrentUser | null;
  initialized: boolean;
}

let state: UserState = { user: null, initialized: false };
const listeners = new Set<() => void>();

function setState(next: UserState) {
  state = next;
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void) {
  listeners.add(fn);
  return () => {
    listeners.delete(fn);
  };
}

function getSnapshot(): UserState {
  return state;
}

export async function fetchCurrentUser(): Promise<CurrentUser | null> {
  try {
    const resp = await http.get('/api/auth/me');
    setState({ user: unwrap<CurrentUser>(resp), initialized: true });
  } catch {
    setState({ user: null, initialized: true });
  }
  return state.user;
}

export async function mockLogin(user_id: string): Promise<CurrentUser> {
  const resp = await http.post('/api/auth/mock-login', { user_id });
  const user = unwrap<CurrentUser>(resp);
  if (user.token) saveAuthToken(user.token);
  setState({ user, initialized: true });
  return user;
}

export async function switchUser(user_id: string): Promise<CurrentUser> {
  const resp = await http.post('/api/auth/switch-user', { user_id });
  const user = unwrap<CurrentUser>(resp);
  if (user.token) saveAuthToken(user.token);
  setState({ user, initialized: true });
  return user;
}

export async function logout() {
  try {
    await http.post('/api/auth/logout');
  } finally {
    clearAuthToken();
    setState({ user: null, initialized: true });
  }
}

export function useCurrentUser(): UserState {
  return useSyncExternalStore(subscribe, getSnapshot);
}
