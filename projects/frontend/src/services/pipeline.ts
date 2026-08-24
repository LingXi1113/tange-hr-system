import { http, unwrap } from './http';
import type { Application, LockInfo } from './candidate';

export interface BoardColumn {
  stage_key: string;
  name: string;
  category: string;
  job_id: number;
  job_name: string;
}

export interface BoardCard extends Application {
  stage_name: string;
  stay: string;
  lock: LockInfo | null;
}

export async function fetchBoard(params: { job_id?: number; requirement_id?: number }) {
  const resp = await http.get('/api/pipeline/board', { params });
  return unwrap<{ columns: BoardColumn[]; cards: BoardCard[] }>(resp);
}

export async function moveApplication(id: number, payload: { to_stage: string; reason: string; version: number }) {
  const resp = await http.post(`/api/applications/${id}/move`, payload);
  return unwrap<Application>(resp);
}

export async function eliminateApplication(id: number, reason: string, version: number) {
  const resp = await http.post(`/api/applications/${id}/eliminate`, { reason, version });
  return unwrap<Application>(resp);
}
