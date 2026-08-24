import { createTrackingClient } from './trackingClient';
import type { TrackingClient, TrackingClientOptions } from './types';

let activeClient: TrackingClient | undefined;

function requireTrackingClient() {
  if (!activeClient) {
    throw new Error('Tracking client has not been initialized.');
  }

  return activeClient;
}

export const tracking = {
  init(options: TrackingClientOptions) {
    activeClient?.destroy();
    activeClient = createTrackingClient(options);
    return activeClient;
  },
  track(...args: Parameters<TrackingClient['track']>): ReturnType<TrackingClient['track']> {
    return requireTrackingClient().track(...args);
  },
  trackImmediately(
    ...args: Parameters<TrackingClient['trackImmediately']>
  ): ReturnType<TrackingClient['trackImmediately']> {
    return requireTrackingClient().trackImmediately(...args);
  },
  syncSchema(
    ...args: Parameters<TrackingClient['syncSchema']>
  ): ReturnType<TrackingClient['syncSchema']> {
    return requireTrackingClient().syncSchema(...args);
  },
  pageView(
    ...args: Parameters<TrackingClient['pageView']>
  ): ReturnType<TrackingClient['pageView']> {
    return requireTrackingClient().pageView(...args);
  },
  pageLeave(
    ...args: Parameters<TrackingClient['pageLeave']>
  ): ReturnType<TrackingClient['pageLeave']> {
    return requireTrackingClient().pageLeave(...args);
  },
  flush(): ReturnType<TrackingClient['flush']> {
    return requireTrackingClient().flush();
  },
  destroy() {
    activeClient?.destroy();
    activeClient = undefined;
  },
  getClient() {
    return activeClient;
  },
};

export { createTrackingClient };
export {
  DEFAULT_TRACKING_STORAGE_KEY,
  createMemoryStorage,
  createTrackingQueueStorage,
} from './storage';
export {
  DEFAULT_TRACKING_ENDPOINT,
  DEFAULT_TRACKING_ANONYMOUS_USER_STORAGE_KEY,
  DEFAULT_TRACKING_ENV_STORAGE_KEY,
  DEFAULT_TRACKING_ENVIRONMENT,
  DEFAULT_TRACKING_SCHEMA_STORAGE_KEY_PREFIX,
  TRACKING_BATCH_PATH,
  TRACKING_ENV_PATH,
  TRACKING_SCHEMA_PATH_TEMPLATE,
  TRACKING_TRACK_PATH,
  createTrackingSchemaPath,
  joinUrl,
  resolveTrackingEndpoint,
} from './environment';
export type {
  BatchTrackingRequest,
  ResolvedTrackingConfig,
  SingleTrackingRequest,
  TrackingClient,
  TrackingClientOptions,
  TrackingEnvironment,
  TrackingEventDefinition,
  TrackingEventKey,
  TrackingEventPayload,
  TrackingFetch,
  TrackingLogger,
  TrackingProjectType,
  TrackingProjectSchemaInput,
  TrackingProjectSchemaRequest,
  TrackingPropertySchema,
  TrackingPropertyType,
  TrackingProperties,
  TrackingScheduler,
  TrackOptions,
} from './types';
