export const BUSINESS_DATA_CHANGED_EVENT = 'hrats:business-data-changed';

const BUSINESS_DATA_REVISION_KEY = 'hrats:business-data-revision';

export interface BusinessDataChange {
  method: string;
  url: string;
  changedAt: number;
}

/** 通知当前页面及其他浏览器标签页：候选人相关业务数据已变化。 */
export function notifyBusinessDataChanged(change: Omit<BusinessDataChange, 'changedAt'>) {
  if (typeof window === 'undefined') return;
  const detail: BusinessDataChange = { ...change, changedAt: Date.now() };
  window.dispatchEvent(new CustomEvent<BusinessDataChange>(BUSINESS_DATA_CHANGED_EVENT, { detail }));
  try {
    window.localStorage.setItem(BUSINESS_DATA_REVISION_KEY, JSON.stringify(detail));
  } catch {
    // 存储不可用时，同标签页事件仍然有效。
  }
}

export function subscribeBusinessDataChanged(listener: (change?: BusinessDataChange) => void) {
  if (typeof window === 'undefined') return () => undefined;

  const handleLocalChange = (event: Event) => {
    listener((event as CustomEvent<BusinessDataChange>).detail);
  };
  const handleStorageChange = (event: StorageEvent) => {
    if (event.key !== BUSINESS_DATA_REVISION_KEY || !event.newValue) return;
    try {
      listener(JSON.parse(event.newValue) as BusinessDataChange);
    } catch {
      listener();
    }
  };

  window.addEventListener(BUSINESS_DATA_CHANGED_EVENT, handleLocalChange);
  window.addEventListener('storage', handleStorageChange);
  return () => {
    window.removeEventListener(BUSINESS_DATA_CHANGED_EVENT, handleLocalChange);
    window.removeEventListener('storage', handleStorageChange);
  };
}
