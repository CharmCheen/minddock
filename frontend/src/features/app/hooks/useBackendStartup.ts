import { useEffect, useRef } from 'react';
import { useAvailabilityStore } from '../store/availability';

interface UseBackendStartupOptions {
  onOnline?: () => void;
  onOffline?: () => void;
}

export function useBackendStartup({ onOnline, onOffline }: UseBackendStartupOptions = {}) {
  const { status, probe, reset } = useAvailabilityStore();
  const onOnlineRef = useRef(onOnline);
  const onOfflineRef = useRef(onOffline);

  // Keep refs current
  useEffect(() => { onOnlineRef.current = onOnline; }, [onOnline]);
  useEffect(() => { onOfflineRef.current = onOffline; }, [onOffline]);

  useEffect(() => {
    // Probe immediately on mount
    probe();
  }, [probe]);

  useEffect(() => {
    if (status === 'online') {
      onOnlineRef.current?.();
    } else if (status === 'offline') {
      onOfflineRef.current?.();
    }
  }, [status]);

  return { status, retry: probe, reset };
}
