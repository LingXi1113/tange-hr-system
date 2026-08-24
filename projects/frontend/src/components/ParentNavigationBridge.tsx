import { useEffect, useRef } from 'react';
import { useLocation, useNavigate, useNavigationType } from 'react-router-dom';

const NAVIGATION_MESSAGE_TYPE = 'custom.workspace.navigation';
const NAVIGATION_MESSAGE_SOURCE = 'ai-coding-sdk';

export function useParentNavigationBridge() {
  const navigate = useNavigate();
  const location = useLocation();
  const navigationType = useNavigationType();

  const routeStackRef = useRef<string[]>([]);
  const routeIndexRef = useRef(-1);
  const applyingParentNavigationRef = useRef(false);

  useEffect(() => {
    const currentRoute = `${location.pathname}${location.search}${location.hash}`;

    if (applyingParentNavigationRef.current) {
      applyingParentNavigationRef.current = false;
      return;
    }

    const routeStack = routeStackRef.current;
    const currentIndex = routeIndexRef.current;

    if (routeStack[currentIndex] === currentRoute) {
      return;
    }

    if (navigationType === 'REPLACE' && currentIndex >= 0) {
      const nextRouteStack = [...routeStack];
      nextRouteStack[currentIndex] = currentRoute;
      routeStackRef.current = nextRouteStack;
      return;
    }

    const nextRouteStack = routeStack.slice(0, currentIndex + 1);
    nextRouteStack.push(currentRoute);

    routeStackRef.current = nextRouteStack;
    routeIndexRef.current = nextRouteStack.length - 1;
  }, [location, navigationType]);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      const data = event.data;

      if (data?.type !== NAVIGATION_MESSAGE_TYPE || data.source !== NAVIGATION_MESSAGE_SOURCE) {
        return;
      }

      const delta = data.action === 'back' ? -1 : data.action === 'forward' ? 1 : 0;

      if (!delta) {
        return;
      }

      const nextIndex = routeIndexRef.current + delta;
      const targetRoute = routeStackRef.current[nextIndex];

      if (!targetRoute) {
        return;
      }

      routeIndexRef.current = nextIndex;
      applyingParentNavigationRef.current = true;

      // Use app-level navigation instead of window.history.go()
      // to avoid affecting the parent page history.
      navigate(targetRoute, { replace: true });
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [navigate]);
}

export function ParentNavigationBridge() {
  useParentNavigationBridge();
  return null;
}
