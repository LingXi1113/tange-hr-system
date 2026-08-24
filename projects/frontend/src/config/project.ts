export type ProjectType = 'embedded' | 'normal';

export const PROJECT_TYPE: ProjectType = __PROJECT_TYPE__;
export const APP_ID = __APP_ID__;
export const isEmbeddedApp = PROJECT_TYPE === 'embedded';
