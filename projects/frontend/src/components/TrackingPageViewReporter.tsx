import { useEffect } from 'react';

import { trackPageLoadPageView } from '@/tracking';

export function TrackingPageViewReporter() {
  useEffect(() => {
    trackPageLoadPageView();
  }, []);

  return null;
}
