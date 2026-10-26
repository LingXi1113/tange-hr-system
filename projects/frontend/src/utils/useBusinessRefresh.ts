import { useEffect } from 'react';

import { subscribeBusinessDataChanged } from './businessDataEvents';

/** Refresh already-open business pages after mutations, cross-tab changes or returning to the window. */
export function useBusinessRefresh(refresh: () => void | Promise<void>) {
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    const queue = () => {
      clearTimeout(timer);
      timer = setTimeout(() => { void refresh(); }, 180);
    };
    const visible = () => { if (document.visibilityState === 'visible') queue(); };
    const unsubscribe = subscribeBusinessDataChanged(queue);
    window.addEventListener('focus', queue);
    document.addEventListener('visibilitychange', visible);
    return () => {
      clearTimeout(timer);
      unsubscribe();
      window.removeEventListener('focus', queue);
      document.removeEventListener('visibilitychange', visible);
    };
  }, [refresh]);
}
