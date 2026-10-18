import axios, { AxiosError } from "axios";

import { useAuthStore } from "@/store/authStore";
import { friendlyMessage } from "@/lib/friendlyErrors";
import { getRawInitData, isInsideTelegram } from "@/lib/telegram";
import type { ApiError } from "@/types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export const api = axios.create({ baseURL: API_URL });

/** Builds the same auth headers as the axios interceptor below, for the rare
 * request that can't go through axios — e.g. a `fetch(..., { keepalive: true })`
 * call fired from a `pagehide` handler while the page is actually unloading. */
export function buildAuthHeaders(): Record<string, string> {
  return isInsideTelegram() ? { "X-Telegram-Init-Data": getRawInitData() } : { "X-Dev-Mode": "true" };
}

export function apiUrl(path: string): string {
  return `${API_URL}${path}`;
}

api.interceptors.request.use((config) => {
  if (isInsideTelegram()) {
    config.headers.set("X-Telegram-Init-Data", getRawInitData());
  } else {
    config.headers.set("X-Dev-Mode", "true");
  }

  if (config.url?.startsWith("/admin")) {
    const token = useAuthStore.getState().adminToken;
    if (token) config.headers.set("Authorization", `Bearer ${token}`);
  }

  return config;
});

export class ApiRequestError extends Error {
  code: string;
  details?: Record<string, unknown>;
  status?: number;
  /** The server's own text (may be English); `message` is the player-facing one. */
  serverMessage: string;

  constructor(message: string, code: string, status?: number, details?: Record<string, unknown>, serverMessage?: string) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
    this.serverMessage = serverMessage ?? message;
  }
}

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiError>) => {
    const body = error.response?.data;
    const status = error.response?.status;
    // The admin panel keeps the server's exact text (it's for debugging).
    const isAdmin = !!error.config?.url?.startsWith("/admin");
    if (body?.error) {
      const shown = isAdmin ? body.error.message : friendlyMessage(body.error.message, status, true);
      throw new ApiRequestError(shown, body.error.code, status, body.error.details, body.error.message);
    }
    // No JSON error body: a network failure (no response) or a proxy / server
    // crash — never show axios' «Request failed with status code 500».
    throw new ApiRequestError(friendlyMessage(undefined, status, false), "network_error", status, undefined, error.message);
  },
);

export function staticUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  const base = (import.meta.env.VITE_STATIC_URL as string) ?? "http://localhost:8000/static";
  return `${base}/${path}`;
}
