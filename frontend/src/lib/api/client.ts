import axios, { AxiosError } from 'axios';
import { ErrorResponse } from '../../core/types/api';

export const isNetworkError = (error: unknown): boolean => {
  if (error instanceof AxiosError) {
    if (!error.response) {
      // No response means network-level failure
      return true;
    }
    // Also treat aborted requests as non-error (cancelled by user/HMR)
    if (error.code === 'ECONNABORTED' || axios.isCancel(error)) {
      return true;
    }
  }
  if (error instanceof Error && error.name === 'CanceledError') {
    return true;
  }
  return false;
};

export const getErrorMessage = (error: unknown, fallback: string): string => {
  if (error instanceof AxiosError) {
    if (error.response) {
      // Server responded with error status
      const data = error.response.data as ErrorResponse | undefined;
      return data?.detail || `HTTP ${error.response.status}: ${error.response.statusText}`;
    }
    if (!error.response) {
      // Network error
      if (error.code === 'ECONNABORTED' || axios.isCancel(error)) {
        return 'Request cancelled';
      }
      return 'Backend unreachable';
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
};

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export const apiClient = axios.create({
  baseURL,
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Only log non-network errors to console; network errors are expected during offline/dev startup.
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (isNetworkError(error)) {
      // Network errors are handled gracefully by stores, not logged as red errors
      return Promise.reject(error);
    }

    // Real API errors (4xx/5xx with response) should still be logged as errors.
    if (error.response) {
      const errorData = error.response.data as ErrorResponse;
      console.error(`[API Error] ${errorData.category || 'General'}: ${errorData.detail}`);
    } else {
      console.error('[API Error] Unexpected error:', error.message);
    }
    return Promise.reject(error);
  }
);
