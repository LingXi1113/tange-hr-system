import {
  DEFAULT_TRACKING_STORAGE_KEY,
  createTrackingQueueStorage,
  getDefaultStorage,
} from './storage';
import {
  assertTrackingEnvironment,
  createTrackingSchemaPath,
  DEFAULT_TRACKING_ANONYMOUS_USER_STORAGE_KEY,
  DEFAULT_TRACKING_ENV_STORAGE_KEY,
  DEFAULT_TRACKING_ENVIRONMENT,
  DEFAULT_TRACKING_SCHEMA_STORAGE_KEY_PREFIX,
  joinUrl,
  resolveTrackingEndpoint,
  TRACKING_BATCH_PATH,
  TRACKING_ENV_PATH,
  TRACKING_TRACK_PATH,
} from './environment';
import type {
  BatchTrackingRequest,
  ResolvedTrackingConfig,
  SingleTrackingRequest,
  TrackingClient,
  TrackingClientOptions,
  TrackingEventKey,
  TrackingEventPayload,
  TrackingFetch,
  TrackingLogger,
  TrackingProjectSchemaInput,
  TrackingProjectSchemaRequest,
  TrackingProperties,
  TrackingScheduler,
  TrackOptions,
} from './types';
import { collectPageContext, getWindowRef, nowIsoString } from './utils';

const DEFAULT_BATCH_SIZE = 100;
const DEFAULT_FLUSH_INTERVAL = 2 * 60 * 1000;

function normalizeBatchSize(batchSize?: number) {
  if (!Number.isFinite(batchSize)) {
    return DEFAULT_BATCH_SIZE;
  }

  return Math.min(Math.max(Math.floor(batchSize ?? DEFAULT_BATCH_SIZE), 1), 100);
}

function getDefaultScheduler(): TrackingScheduler {
  return {
    setInterval(callback, ms) {
      const timerId = setInterval(() => {
        void callback();
      }, ms);

      const nodeTimer = timerId as unknown as { unref?: () => void };
      nodeTimer.unref?.();

      return timerId;
    },
    clearInterval(timerId) {
      clearInterval(timerId as number);
    },
  };
}

function createDefaultSchemaStorageKey(tenantId: string, projectId: string) {
  return `${DEFAULT_TRACKING_SCHEMA_STORAGE_KEY_PREFIX}:${encodeURIComponent(
    tenantId,
  )}:${encodeURIComponent(projectId)}`;
}

function normalizeTrackingId(value?: string) {
  return typeof value === 'string' ? value.trim() : '';
}

function createDefaultAnonymousUserId() {
  const randomUUID = globalThis.crypto?.randomUUID?.bind(globalThis.crypto);

  if (!randomUUID) {
    throw new Error('crypto.randomUUID is required to create anonymous user id.');
  }

  return randomUUID();
}

function resolveConfig(options: TrackingClientOptions): ResolvedTrackingConfig {
  const projectId = normalizeTrackingId(options.projectId);
  const tenantId = normalizeTrackingId(options.tenantId);
  const environment = options.environment ?? DEFAULT_TRACKING_ENVIRONMENT;
  assertTrackingEnvironment(environment);
  const endpoint = resolveTrackingEndpoint(options.endpoint);

  return {
    projectId,
    environment,
    schemaVersion: options.schemaVersion,
    tenantId,
    projectType: options.projectType,
    userId: options.userId,
    anonymousUser: options.anonymousUser ?? false,
    endpoint,
    batchEndpoint: joinUrl(endpoint, TRACKING_BATCH_PATH),
    trackEndpoint: joinUrl(endpoint, TRACKING_TRACK_PATH),
    envEndpoint: options.envEndpoint ?? TRACKING_ENV_PATH,
    schemaEndpoint: joinUrl(endpoint, createTrackingSchemaPath(tenantId, projectId)),
    autoPageView: options.autoPageView ?? false,
    autoPageLeave: options.autoPageLeave ?? false,
    batchSize: normalizeBatchSize(options.batchSize),
    flushInterval: options.flushInterval ?? DEFAULT_FLUSH_INTERVAL,
    storageKey: options.storageKey ?? DEFAULT_TRACKING_STORAGE_KEY,
    envStorageKey: options.envStorageKey ?? DEFAULT_TRACKING_ENV_STORAGE_KEY,
    schemaStorageKey:
      options.schemaStorageKey ?? createDefaultSchemaStorageKey(tenantId, projectId),
    anonymousUserStorageKey:
      options.anonymousUserStorageKey ?? DEFAULT_TRACKING_ANONYMOUS_USER_STORAGE_KEY,
  };
}

function createBatchRequest(
  config: ResolvedTrackingConfig,
  events: TrackingEventPayload[],
): BatchTrackingRequest {
  return {
    project_id: config.projectId,
    schema_version: config.schemaVersion,
    tenant_id: config.tenantId,
    user_id: config.userId,
    environment: config.environment,
    events,
  };
}

function createSingleRequest(
  config: ResolvedTrackingConfig,
  event: TrackingEventPayload,
): SingleTrackingRequest {
  return {
    ...event,
    project_id: config.projectId,
    schema_version: config.schemaVersion,
    tenant_id: config.tenantId,
    user_id: config.userId,
    environment: config.environment,
  };
}

function createSchemaRequest(
  config: ResolvedTrackingConfig,
  schema: TrackingProjectSchemaInput,
): TrackingProjectSchemaRequest {
  return {
    tenant_id: config.tenantId,
    project_id: config.projectId,
    project_name: schema.project_name,
    schema_version: schema.schema_version,
    timezone: schema.timezone,
    events: schema.events,
  };
}

function createTrackingDiagnostics(config: ResolvedTrackingConfig): TrackingProperties {
  const missingFields: string[] = [];

  if (!config.projectId) {
    missingFields.push('project_id');
  }

  if (!config.tenantId) {
    missingFields.push('company_id');
  }

  if (!config.userId) {
    missingFields.push('user_id');
  }

  return {
    tracking_project_id_missing: !config.projectId,
    tracking_company_id_missing: !config.tenantId,
    tracking_user_id_missing: !config.userId,
    tracking_missing_fields: missingFields.join(','),
  };
}

async function sendBatch({
  config,
  events,
  fetcher,
  keepalive,
}: {
  config: ResolvedTrackingConfig;
  events: TrackingEventPayload[];
  fetcher: TrackingFetch;
  keepalive?: boolean;
}) {
  const response = await fetcher(config.batchEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    keepalive,
    body: JSON.stringify(createBatchRequest(config, events)),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
}

async function sendSingle({
  config,
  event,
  fetcher,
}: {
  config: ResolvedTrackingConfig;
  event: TrackingEventPayload;
  fetcher: TrackingFetch;
}) {
  const response = await fetcher(config.trackEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(createSingleRequest(config, event)),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
}

async function sendSchema({
  config,
  schema,
  fetcher,
}: {
  config: ResolvedTrackingConfig;
  schema: TrackingProjectSchemaInput;
  fetcher: TrackingFetch;
}) {
  const response = await fetcher(config.schemaEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(createSchemaRequest(config, schema)),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
}

function resolveAnonymousUserId({
  config,
  storage,
  createAnonymousUserId,
}: {
  config: ResolvedTrackingConfig;
  storage: Storage;
  createAnonymousUserId: () => string;
}) {
  const cachedUserId = storage.getItem(config.anonymousUserStorageKey);

  if (cachedUserId) {
    return cachedUserId;
  }

  const userId = createAnonymousUserId();
  storage.setItem(config.anonymousUserStorageKey, userId);
  return userId;
}

function readCachedSchemaVersion({
  config,
  storage,
}: {
  config: ResolvedTrackingConfig;
  storage: Storage;
}) {
  const raw = storage.getItem(config.schemaStorageKey);

  if (!raw) {
    return undefined;
  }

  try {
    const parsed = JSON.parse(raw) as { schema_version?: unknown };

    if (typeof parsed.schema_version === 'string') {
      return parsed.schema_version;
    }
    storage.removeItem(config.schemaStorageKey);
  } catch {
    storage.removeItem(config.schemaStorageKey);
  }

  return undefined;
}

function isSchemaCached({
  config,
  storage,
  schema,
}: {
  config: ResolvedTrackingConfig;
  storage: Storage;
  schema: TrackingProjectSchemaInput;
}) {
  return readCachedSchemaVersion({ config, storage }) === schema.schema_version;
}

function writeCachedSchema({
  config,
  storage,
  schema,
}: {
  config: ResolvedTrackingConfig;
  storage: Storage;
  schema: TrackingProjectSchemaInput;
}) {
  storage.setItem(config.schemaStorageKey, JSON.stringify(schema));
}

function readCachedEnvironment({
  config,
  storage,
}: {
  config: ResolvedTrackingConfig;
  storage: Storage;
}) {
  const cachedEnvironment = storage.getItem(config.envStorageKey);

  if (!cachedEnvironment) {
    return undefined;
  }

  try {
    assertTrackingEnvironment(cachedEnvironment);
    return cachedEnvironment;
  } catch {
    storage.removeItem(config.envStorageKey);
    return undefined;
  }
}

function writeCachedEnvironment({
  config,
  storage,
}: {
  config: ResolvedTrackingConfig;
  storage: Storage;
}) {
  storage.setItem(config.envStorageKey, config.environment);
}

function setDefaultEnvironment(config: ResolvedTrackingConfig) {
  config.environment = DEFAULT_TRACKING_ENVIRONMENT;
}

async function resolveRemoteEnvironment({
  config,
  storage,
  fetcher,
}: {
  config: ResolvedTrackingConfig;
  storage: Storage;
  fetcher: TrackingFetch;
}) {
  const cachedEnvironment = readCachedEnvironment({ config, storage });

  if (cachedEnvironment) {
    config.environment = cachedEnvironment;
    return;
  }

  try {
    const response = await fetcher(config.envEndpoint, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    const body = (await response.json()) as { env_name?: unknown };

    if (typeof body.env_name !== 'string') {
      throw new Error('Tracking env_name is required.');
    }

    assertTrackingEnvironment(body.env_name);
    config.environment = body.env_name;
    writeCachedEnvironment({ config, storage });
  } catch {
    setDefaultEnvironment(config);
  }
}

function buildEventPayload({
  eventKey,
  properties,
  options,
  config,
  windowRef,
}: {
  eventKey: TrackingEventKey;
  properties: TrackingProperties;
  options?: TrackOptions;
  config: ResolvedTrackingConfig;
  windowRef?: Window;
}): TrackingEventPayload {
  const pageContext = collectPageContext(windowRef);

  return {
    event_key: eventKey,
    event_time: options?.eventTime ?? nowIsoString(),
    page_url: options?.pageUrl ?? pageContext.page_url,
    page_path: options?.pagePath ?? pageContext.page_path,
    page_title: options?.pageTitle ?? pageContext.page_title,
    referrer: options?.referrer ?? pageContext.referrer,
    device_type: pageContext.device_type,
    os: pageContext.os,
    browser: pageContext.browser,
    user_agent: pageContext.user_agent,
    language: pageContext.language,
    screen_width: pageContext.screen_width,
    screen_height: pageContext.screen_height,
    properties: {
      ...properties,
      ...createTrackingDiagnostics(config),
      environment: config.environment,
    },
  };
}

function warn(logger: TrackingLogger, message: string, error: unknown) {
  logger.warn(`[event-tracking] ${message}`, error);
}

export function createTrackingClient(options: TrackingClientOptions): TrackingClient {
  const config = resolveConfig(options);
  const windowRef = getWindowRef(options.windowRef);
  const storage = options.storage ?? getDefaultStorage(windowRef);
  const queue = createTrackingQueueStorage({
    storage,
    storageKey: config.storageKey,
  });
  const fetcher = options.fetcher ?? fetch;
  const scheduler = options.scheduler ?? getDefaultScheduler();
  const logger = options.logger ?? console;
  const createAnonymousUserId = options.createAnonymousUserId ?? createDefaultAnonymousUserId;
  const cleanupCallbacks: Array<() => void> = [];
  const pageStartTime = Date.now();
  let timerId: unknown;
  let destroyed = false;
  let flushing = false;
  let environmentReadyPromise: Promise<void> | undefined;
  const shouldResolveRemoteEnvironment = options.environment === undefined;

  const ensureEnvironmentReady = () => {
    if (!shouldResolveRemoteEnvironment) {
      return Promise.resolve();
    }

    if (!environmentReadyPromise) {
      environmentReadyPromise = resolveRemoteEnvironment({
        config,
        storage,
        fetcher,
      }).catch((error) => {
        environmentReadyPromise = undefined;
        throw error;
      });
    }

    return environmentReadyPromise;
  };

  const ensureUserIdReady = () => {
    if (config.userId) {
      return Promise.resolve();
    }

    if (config.projectType === 'embedded' || config.anonymousUser) {
      try {
        config.userId = resolveAnonymousUserId({
          config,
          storage,
          createAnonymousUserId,
        });
      } catch (error) {
        warn(
          logger,
          config.projectType === 'embedded'
            ? 'embedded app did not provide userId; fallback user id resolve failed; continue without user_id.'
            : 'anonymous user id resolve failed; continue without user_id.',
          error,
        );
      }
    }

    return Promise.resolve();
  };

  const flushQueue = async ({ keepalive = false } = {}) => {
    if (destroyed || flushing) {
      return;
    }

    flushing = true;

    try {
      await ensureEnvironmentReady();
      await ensureUserIdReady();

      while (true) {
        const events = queue.read();

        if (events.length === 0) {
          return;
        }

        const batch = events.slice(0, config.batchSize);
        const remaining = events.slice(config.batchSize);
        queue.write(remaining);

        try {
          await sendBatch({ config, events: batch, fetcher, keepalive });
        } catch (error) {
          queue.write([...batch, ...queue.read()]);
          throw error;
        }
      }
    } finally {
      flushing = false;
    }
  };

  const client: TrackingClient = {
    async track(eventKey, properties = {}, trackOptions) {
      if (destroyed) {
        return;
      }

      await ensureEnvironmentReady();
      await ensureUserIdReady();

      const event = buildEventPayload({
        eventKey,
        properties,
        options: trackOptions,
        config,
        windowRef,
      });
      const events = queue.append(event);

      if (events.length >= config.batchSize) {
        await client.flush();
      }
    },
    async trackImmediately(eventKey, properties = {}, trackOptions) {
      if (destroyed) {
        return;
      }

      await ensureEnvironmentReady();
      await ensureUserIdReady();

      const event = buildEventPayload({
        eventKey,
        properties,
        options: trackOptions,
        config,
        windowRef,
      });

      await sendSingle({ config, event, fetcher });
    },
    async syncSchema(schema) {
      if (destroyed) {
        return;
      }

      if (isSchemaCached({ config, storage, schema })) {
        return;
      }

      await sendSchema({ config, schema, fetcher });
      writeCachedSchema({ config, storage, schema });
    },
    async pageView(properties = {}) {
      await client.track('page_view', properties);
    },
    async pageLeave(properties = {}) {
      const duration = Math.max(Date.now() - pageStartTime, 0);

      await client.track('page_leave', {
        ...properties,
        duration_ms: duration,
      });
    },
    async flush() {
      await flushQueue();
    },
    destroy() {
      destroyed = true;

      if (timerId !== undefined) {
        scheduler.clearInterval(timerId);
        timerId = undefined;
      }

      for (const cleanup of cleanupCallbacks) {
        cleanup();
      }
      cleanupCallbacks.length = 0;
    },
    getConfig() {
      return { ...config };
    },
  };

  if (config.flushInterval > 0) {
    timerId = scheduler.setInterval(
      () => client.flush().catch((error) => warn(logger, 'flush failed.', error)),
      config.flushInterval,
    );
  }

  if (config.autoPageView) {
    void client.pageView().catch((error) => warn(logger, 'auto page_view failed.', error));
  }

  void ensureEnvironmentReady().catch((error) =>
    warn(logger, 'environment resolve failed.', error),
  );
  void ensureUserIdReady().catch((error) => warn(logger, 'user id resolve failed.', error));

  if (windowRef?.addEventListener) {
    const handlePageLeave = () => {
      const flushOnLeave = config.autoPageLeave
        ? client.pageLeave().then(() => flushQueue({ keepalive: true }))
        : flushQueue({ keepalive: true });

      void flushOnLeave.catch((error) => warn(logger, 'page lifecycle flush failed.', error));
    };

    windowRef.addEventListener('pagehide', handlePageLeave);
    windowRef.addEventListener('beforeunload', handlePageLeave);
    cleanupCallbacks.push(() => {
      windowRef.removeEventListener('pagehide', handlePageLeave);
      windowRef.removeEventListener('beforeunload', handlePageLeave);
    });
  }

  return client;
}
