import type { TrackingEnvironment } from './types';

export const TRACKING_BATCH_PATH = '/api/v1/events/batch';
export const TRACKING_TRACK_PATH = '/api/v1/events/track';
export const TRACKING_ENV_PATH = '/env';
export const TRACKING_SCHEMA_PATH_TEMPLATE =
  '/api/v1/tenants/{tenant_id}/projects/{project_id}/tracking-schema';
export const DEFAULT_TRACKING_ENDPOINT = 'https://aicoding-event-tracking.tangees.com';
export const DEFAULT_TRACKING_ENVIRONMENT: TrackingEnvironment = 'dev';
export const DEFAULT_TRACKING_ENV_STORAGE_KEY = 'jahead_tracking_environment';
export const DEFAULT_TRACKING_ANONYMOUS_USER_STORAGE_KEY = 'jahead_tracking_anonymous_user_id';
export const DEFAULT_TRACKING_SCHEMA_STORAGE_KEY_PREFIX = 'jahead_tracking_schema';

const supportedEnvironments = new Set(['dev', 'gray', 'prod']);

export function assertTrackingEnvironment(
  environment: string,
): asserts environment is TrackingEnvironment {
  if (!supportedEnvironments.has(environment)) {
    throw new Error(`Unsupported tracking environment: ${environment}`);
  }
}

export function joinUrl(rootUrl: string, path: string) {
  const normalizedBase = rootUrl.replace(/\/+$/, '');
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;

  if (!normalizedBase) {
    return normalizedPath;
  }

  return `${normalizedBase}${normalizedPath}`;
}

export function resolveTrackingEndpoint(endpoint?: string) {
  return (endpoint ?? DEFAULT_TRACKING_ENDPOINT).replace(/\/+$/, '');
}

export function createTrackingSchemaPath(tenantId: string, projectId: string) {
  return `/api/v1/tenants/${encodeURIComponent(
    tenantId,
  )}/projects/${encodeURIComponent(projectId)}/tracking-schema`;
}
