import { create } from 'zustand';
import { apiClient } from '../../../lib/api/client';

export type BackendStatus = 'checking' | 'online' | 'offline';

interface AvailabilityState {
  status: BackendStatus;
  lastChecked: number | null;
  retryCount: number;
  retryTimer: ReturnType<typeof setTimeout> | null;

  probe: () => Promise<void>;
  setOnline: () => void;
  setOffline: () => void;
  reset: () => void;
}

const MAX_RETRY_INTERVAL_MS = 30000;
const BASE_RETRY_INTERVAL_MS = 2000;

function getRetryInterval(count: number): number {
  const interval = BASE_RETRY_INTERVAL_MS * Math.pow(2, count);
  return Math.min(interval, MAX_RETRY_INTERVAL_MS);
}

export const useAvailabilityStore = create<AvailabilityState>((set, get) => ({
  status: 'checking',
  lastChecked: null,
  retryCount: 0,
  retryTimer: null,

  probe: async () => {
    // If already online, skip
    if (get().status === 'online') return;

    set({ status: 'checking' });
    try {
      await apiClient.get('/health', { timeout: 3000 });
      set({ status: 'online', retryCount: 0, lastChecked: Date.now() });
    } catch {
      const { retryCount } = get();
      const nextCount = retryCount + 1;
      const interval = getRetryInterval(retryCount);

      set({
        status: 'offline',
        retryCount: nextCount,
        lastChecked: Date.now(),
      });

      // Schedule retry
      const existing = get().retryTimer;
      if (existing) clearTimeout(existing);
      const timer = setTimeout(() => {
        get().probe();
      }, interval);
      set({ retryTimer: timer });
    }
  },

  setOnline: () => {
    const existing = get().retryTimer;
    if (existing) clearTimeout(existing);
    set({ status: 'online', retryCount: 0, retryTimer: null, lastChecked: Date.now() });
  },

  setOffline: () => {
    set({ status: 'offline' });
  },

  reset: () => {
    const existing = get().retryTimer;
    if (existing) clearTimeout(existing);
    set({ status: 'checking', retryCount: 0, retryTimer: null, lastChecked: null });
    get().probe();
  },
}));
