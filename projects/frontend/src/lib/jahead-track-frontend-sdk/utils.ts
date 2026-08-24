export function getWindowRef(windowRef?: Window) {
  if (windowRef) {
    return windowRef;
  }

  if (typeof window === 'undefined') {
    return undefined;
  }

  return window;
}

export function nowIsoString() {
  return new Date().toISOString();
}

export function detectDeviceType(windowRef?: Window) {
  const width = windowRef?.screen?.width ?? 0;
  const userAgent = windowRef?.navigator?.userAgent ?? '';

  if (/Mobi|Android|iPhone|iPad|iPod/i.test(userAgent) || width < 768) {
    return 'mobile';
  }

  return 'desktop';
}

export function detectOS(userAgent: string) {
  if (/Windows/i.test(userAgent)) {
    return 'Windows';
  }
  if (/Mac OS|Macintosh/i.test(userAgent)) {
    return 'macOS';
  }
  if (/Android/i.test(userAgent)) {
    return 'Android';
  }
  if (/iPhone|iPad|iPod/i.test(userAgent)) {
    return 'iOS';
  }
  if (/Linux/i.test(userAgent)) {
    return 'Linux';
  }
  return 'Unknown';
}

export function detectBrowser(userAgent: string) {
  if (/Edg\//i.test(userAgent)) {
    return 'Edge';
  }
  if (/Chrome|CriOS/i.test(userAgent)) {
    return 'Chrome';
  }
  if (/Firefox|FxiOS/i.test(userAgent)) {
    return 'Firefox';
  }
  if (/Safari/i.test(userAgent)) {
    return 'Safari';
  }
  return 'Unknown';
}

export function collectPageContext(windowRef?: Window) {
  const userAgent = windowRef?.navigator?.userAgent ?? '';

  return {
    page_url: windowRef?.location?.href,
    page_path: windowRef?.location?.pathname,
    page_title: windowRef?.document?.title,
    referrer: windowRef?.document?.referrer,
    device_type: detectDeviceType(windowRef),
    os: detectOS(userAgent),
    browser: detectBrowser(userAgent),
    user_agent: userAgent,
    language: windowRef?.navigator?.language,
    screen_width: windowRef?.screen?.width,
    screen_height: windowRef?.screen?.height,
  };
}
