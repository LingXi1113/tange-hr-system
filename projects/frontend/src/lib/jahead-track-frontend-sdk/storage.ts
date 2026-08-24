import type { TrackingEventPayload } from './types';

export const DEFAULT_TRACKING_STORAGE_KEY = 'jahead_tracking_queue';

export interface TrackingQueueStorage {
  read: () => TrackingEventPayload[];
  write: (events: TrackingEventPayload[]) => void;
  append: (event: TrackingEventPayload) => TrackingEventPayload[];
}

export function createMemoryStorage(): Storage {
  const items = new Map<string, string>();

  return {
    get length() {
      return items.size;
    },
    clear() {
      items.clear();
    },
    getItem(key) {
      return items.get(key) ?? null;
    },
    key(index) {
      return Array.from(items.keys())[index] ?? null;
    },
    removeItem(key) {
      items.delete(key);
    },
    setItem(key, value) {
      items.set(key, value);
    },
  };
}

export function getDefaultStorage(windowRef?: Window): Storage {
  if (windowRef?.localStorage) {
    return windowRef.localStorage;
  }

  if (typeof window !== 'undefined' && window.localStorage) {
    return window.localStorage;
  }

  return createMemoryStorage();
}

export function createTrackingQueueStorage({
  storage,
  storageKey = DEFAULT_TRACKING_STORAGE_KEY,
}: {
  storage: Storage;
  storageKey?: string;
}): TrackingQueueStorage {
  return {
    read() {
      const raw = storage.getItem(storageKey);

      if (!raw) {
        return [];
      }

      try {
        const parsed = JSON.parse(raw) as unknown;

        if (Array.isArray(parsed)) {
          return parsed as TrackingEventPayload[];
        }
      } catch {
        storage.removeItem(storageKey);
      }

      return [];
    },
    write(events) {
      if (events.length === 0) {
        storage.removeItem(storageKey);
        return;
      }

      storage.setItem(storageKey, JSON.stringify(events));
    },
    append(event) {
      const events = this.read();
      events.push(event);
      this.write(events);
      return events;
    },
  };
}
