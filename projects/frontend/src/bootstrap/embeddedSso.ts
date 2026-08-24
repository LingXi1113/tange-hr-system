import { getOrCreateEmbeddedTrackingFallbackUserId, loginBySsoCode } from '@/services/auth';

interface JaheadAuthCodeResult {
  appId: string;
  companyId: string;
  code: string;
}

interface JaheadRequestAuthCodeOptions {
  appId: string;
  success?: (result: JaheadAuthCodeResult) => void;
  fail?: (error: { errMsg?: string; message?: string }) => void;
}

interface JaheadBridge {
  version?: string;
  isJaheadClient?: boolean;
  requestAuthCode: (options: JaheadRequestAuthCodeOptions) => Promise<JaheadAuthCodeResult>;
}

interface JaheadWindow extends Window {
  Jahead?: JaheadBridge;
}

export async function prepareEmbeddedSso({ appId }: { appId: string }) {
  if (!appId) {
    console.warn('[auth] PROJECT_TYPE=embedded requires OPEN_PLATFORM_APP_ID or APP_ID.');
    return getOrCreateEmbeddedTrackingFallbackUserId();
  }

  const jahead = (window as JaheadWindow).Jahead;

  if (!jahead?.requestAuthCode) {
    console.warn('[auth] window.Jahead.requestAuthCode is unavailable; embedded SSO skipped.');
    return getOrCreateEmbeddedTrackingFallbackUserId();
  }

  try {
    const authCodeResult = await jahead.requestAuthCode({ appId });

    if (!authCodeResult.code) {
      throw new Error('Jahead auth code is empty.');
    }

    const result = await loginBySsoCode(authCodeResult.code);
    const companyUserId = result.data?.company_user_id?.trim();

    if (!companyUserId) {
      throw new Error('SSO response does not contain company_user_id.');
    }

    return companyUserId;
  } catch (error) {
    console.warn('[auth] Embedded SSO failed.', error);
    return getOrCreateEmbeddedTrackingFallbackUserId();
  }
}
