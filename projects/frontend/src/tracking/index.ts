import { tracking } from '@/lib/jahead-track-frontend-sdk';
import { PROJECT_TYPE } from '@/config/project';
import { getCachedCompanyUserId } from '@/services/auth';
import { getAuthToken } from '@/services/authToken';
import { trackingSchema } from '@/tracking.schema';

let initialized = false;
let pageLoadPageViewTracked = false;

function getTrackingEndpoint() {
  return __TRACKING_ENDPOINT__ || undefined;
}

function createTrackingFetcher(): typeof fetch {
  return (input, init = {}) => {
    const headers = new Headers(init.headers);
    const token = getAuthToken();

    if (token) {
      headers.set('X-Auth-Token', token);
    }

    return fetch(input, {
      ...init,
      headers,
    });
  };
}

export function initializeTracking(embeddedUserId?: string) {
  if (initialized) {
    return;
  }

  const missingFields = [
    !__PROJECT_ID__ ? 'PROJECT_ID' : undefined,
    !__COMPANY_ID__ ? 'COMPANY_ID' : undefined,
  ].filter(Boolean);

  if (missingFields.length > 0) {
    console.warn(
      `[tracking] ${missingFields.join(', ')} missing; event tracking will continue for diagnostics.`,
    );
  }

  initialized = true;

  const userId =
    PROJECT_TYPE === 'embedded' ? embeddedUserId ?? getCachedCompanyUserId() : undefined;

  tracking.init({
    projectId: __PROJECT_ID__,
    tenantId: __COMPANY_ID__,
    projectType: PROJECT_TYPE,
    userId,
    anonymousUser: PROJECT_TYPE !== 'embedded',
    schemaVersion: trackingSchema.schema_version,
    endpoint: getTrackingEndpoint(),
    fetcher: createTrackingFetcher(),
    autoPageView: false,
    autoPageLeave: true,
  });

  void tracking.syncSchema(trackingSchema).catch((error) => {
    console.warn('[tracking] Failed to sync tracking schema.', error);
  });
}

function getInitialHashRoute() {
  const hash = window.location.hash.replace(/^#/, '');
  const [routePath = '/', rawSearch = ''] = hash.split('?');

  return {
    routePath: routePath || '/',
    routeSearch: rawSearch ? `?${rawSearch}` : '',
  };
}

export function trackPageLoadPageView() {
  if (pageLoadPageViewTracked) {
    return;
  }

  if (!tracking.getClient()) {
    return;
  }

  pageLoadPageViewTracked = true;
  const { routePath, routeSearch } = getInitialHashRoute();

  void tracking
    .pageView({
      route_path: routePath,
      route_search: routeSearch,
    })
    .then(() => tracking.flush())
    .catch((error) => {
      console.warn('[tracking] Failed to track page view.', error);
    });
}
