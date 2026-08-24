export type TrackingEnvironment = 'dev' | 'gray' | 'prod';

export type TrackingProjectType = 'embedded' | (string & {});

export type TrackingEventKey =
  | 'page_view'
  | 'page_leave'
  | 'click'
  | 'form_submit'
  | 'custom'
  | (string & {});

export interface TrackingProperties {
  [key: string]: unknown;
}

export interface TrackingEventPayload {
  project_id?: string;
  schema_version?: string;
  tenant_id?: string;
  user_id?: string;
  event_key: string;
  event_time: string;
  page_url?: string;
  page_path?: string;
  page_title?: string;
  referrer?: string;
  device_type?: string;
  os?: string;
  browser?: string;
  user_agent?: string;
  language?: string;
  screen_width?: number;
  screen_height?: number;
  properties: TrackingProperties;
}

export interface BatchTrackingRequest {
  project_id: string;
  schema_version?: string;
  tenant_id: string;
  user_id?: string;
  environment: TrackingEnvironment;
  events: TrackingEventPayload[];
}

export interface SingleTrackingRequest extends TrackingEventPayload {
  project_id: string;
  schema_version?: string;
  tenant_id: string;
  user_id?: string;
  environment: TrackingEnvironment;
}

export type TrackingPropertyType = 'string' | 'number' | 'boolean' | 'datetime';

export interface TrackingPropertySchema {
  type: TrackingPropertyType;
  name?: string;
  description?: string;
  unit?: string;
  required?: boolean;
  sensitive?: boolean;
}

export interface TrackingEventDefinition {
  event_key: string;
  event_type: string;
  event_name: string;
  description?: string;
  source?: string;
  properties_schema?: Record<string, TrackingPropertySchema>;
}

export interface TrackingProjectSchemaInput {
  project_name?: string;
  schema_version: string;
  timezone?: string;
  events: TrackingEventDefinition[];
}

export interface TrackingProjectSchemaRequest extends TrackingProjectSchemaInput {
  tenant_id: string;
  project_id: string;
}

export type TrackingFetch = (
  input: string | URL | Request,
  init?: RequestInit,
) => Promise<Response>;

export interface TrackingScheduler {
  setInterval: (callback: () => void | Promise<void>, ms: number) => unknown;
  clearInterval: (timerId: unknown) => void;
}

export interface TrackingLogger {
  warn: (...args: unknown[]) => void;
}

export interface TrackingClientOptions {
  projectId?: string;
  environment?: TrackingEnvironment;
  schemaVersion?: string;
  tenantId?: string;
  projectType?: TrackingProjectType;
  userId?: string;
  anonymousUser?: boolean;
  /**
   * Tracking service base URL, for example:
   * https://aicoding-event-tracking.tangees.com
   */
  endpoint?: string;
  envEndpoint?: string;
  autoPageView?: boolean;
  autoPageLeave?: boolean;
  batchSize?: number;
  flushInterval?: number;
  storage?: Storage;
  storageKey?: string;
  envStorageKey?: string;
  schemaStorageKey?: string;
  anonymousUserStorageKey?: string;
  createAnonymousUserId?: () => string;
  fetcher?: TrackingFetch;
  scheduler?: TrackingScheduler;
  windowRef?: Window;
  logger?: TrackingLogger;
}

export interface ResolvedTrackingConfig {
  projectId: string;
  environment: TrackingEnvironment;
  schemaVersion?: string;
  tenantId: string;
  projectType?: TrackingProjectType;
  userId?: string;
  anonymousUser: boolean;
  endpoint: string;
  batchEndpoint: string;
  trackEndpoint: string;
  schemaEndpoint: string;
  envEndpoint: string;
  autoPageView: boolean;
  autoPageLeave: boolean;
  batchSize: number;
  flushInterval: number;
  storageKey: string;
  envStorageKey: string;
  schemaStorageKey: string;
  anonymousUserStorageKey: string;
}

export interface TrackOptions {
  eventTime?: string;
  pageUrl?: string;
  pagePath?: string;
  pageTitle?: string;
  referrer?: string;
}

export interface TrackingClient {
  track: (
    eventKey: TrackingEventKey,
    properties?: TrackingProperties,
    options?: TrackOptions,
  ) => Promise<void>;
  trackImmediately: (
    eventKey: TrackingEventKey,
    properties?: TrackingProperties,
    options?: TrackOptions,
  ) => Promise<void>;
  syncSchema: (schema: TrackingProjectSchemaInput) => Promise<void>;
  pageView: (properties?: TrackingProperties) => Promise<void>;
  pageLeave: (properties?: TrackingProperties) => Promise<void>;
  flush: () => Promise<void>;
  destroy: () => void;
  getConfig: () => ResolvedTrackingConfig;
}
