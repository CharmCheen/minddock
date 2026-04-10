import axios from 'axios';
import { ErrorResponse } from '../../core/types/api';

const baseURL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000';

export const apiClient = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.data) {
      const errorData = error.response.data as ErrorResponse;
      console.error(`[API Error] ${errorData.category || 'General'}: ${errorData.detail}`);
    } else {
      console.error('[API Error] Network or unknown error:', error.message);
    }
    return Promise.reject(error);
  }
);
