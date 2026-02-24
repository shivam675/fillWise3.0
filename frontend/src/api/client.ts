/**
 * Centralised Axios instance with:
 * - Bearer-token injection from auth store
 * - CSRF double-submit cookie header
 * - 401 → automatic token refresh with queue-based retry
 * - Structured error forwarding
 */
import axios, {
  type AxiosInstance,
  type InternalAxiosRequestConfig,
  type AxiosError,
} from "axios";
import type { ApiErrorPayload } from "@/types/api";
import { useAuthStore } from "@/stores/auth";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

// ── Singleton Axios instance ─────────────────────────────────────────────────
export const http: AxiosInstance = axios.create({
  baseURL: `${BASE_URL}/api/v1`,
  withCredentials: true,          // send HttpOnly cookies (CSRF)
  headers: {
    "Content-Type": "application/json",
  },
  timeout: 30_000,
});

// ── Request interceptor — attach auth + CSRF headers ────────────────────────
http.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = useAuthStore.getState().accessToken;
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  // Read CSRF token from cookie set by the backend and echo it as a header.
  const csrfToken = getCookie("csrf_token");
  if (csrfToken) {
    config.headers["X-CSRF-Token"] = csrfToken;
  }
  return config;
});

// ── Response interceptor — handle 401 with token refresh ────────────────────
let isRefreshing = false;
let refreshQueue: Array<{
  resolve: (token: string) => void;
  reject: (err: unknown) => void;
}> = [];

function processQueue(error: unknown, token: string | null): void {
  refreshQueue.forEach((p) => (token ? p.resolve(token) : p.reject(error)));
  refreshQueue = [];
}

http.interceptors.response.use(
  (res) => res,
  async (error: AxiosError<ApiErrorPayload>) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };

    if (error.response?.status === 401 && !original._retry) {
      const refreshToken = useAuthStore.getState().refreshToken;
      if (!refreshToken) {
        useAuthStore.getState().logout();
        return Promise.reject(error);
      }

      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          refreshQueue.push({ resolve, reject });
        }).then((newToken) => {
          original.headers.Authorization = `Bearer ${newToken}`;
          return http(original);
        });
      }

      original._retry = true;
      isRefreshing = true;

      try {
        const { data } = await axios.post<{
          access_token: string;
          refresh_token: string;
        }>(`${BASE_URL}/api/v1/auth/refresh`, { refresh_token: refreshToken });

        useAuthStore.getState().setTokens(data.access_token, data.refresh_token);
        processQueue(null, data.access_token);
        original.headers.Authorization = `Bearer ${data.access_token}`;
        return http(original);
      } catch (err) {
        processQueue(err, null);
        useAuthStore.getState().logout();
        return Promise.reject(err);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);

// ── Utility ──────────────────────────────────────────────────────────────────
function getCookie(name: string): string | null {
  const match = document.cookie.match(
    new RegExp("(?:^|; )" + encodeURIComponent(name) + "=([^;]*)")
  );
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * Extract a human-readable message from an API error.
 */
export function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as ApiErrorPayload | undefined;
    return (
      payload?.error?.message ??
      error.message ??
      "An unexpected error occurred"
    );
  }
  if (error instanceof Error) return error.message;
  return "An unexpected error occurred";
}
