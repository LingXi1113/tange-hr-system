/// <reference types="vite/client" />

declare const __APP_ID__: string;
declare const __COMPANY_ID__: string;
declare const __PROJECT_ID__: string;
declare const __PROJECT_TYPE__: 'embedded' | 'normal';
declare const __TRACKING_ENDPOINT__: string;

interface ImportMetaEnv {
  readonly VITE_APP_TITLE?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_DEV_PORT?: string;
  readonly VITE_PREVIEW_PORT?: string;
  readonly VITE_ENABLE_ROLE_SWITCHER?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
