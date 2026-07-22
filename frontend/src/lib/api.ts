import axios, { AxiosError } from "axios";

import { useAuthStore } from "@/store/authStore";
import { getRawInitData, isInsideTelegram } from "@/lib/telegram";
import type { ApiError } from "@/types";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";

export const api = axios.create({ baseURL: API_URL });

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

  constructor(message: string, code: string, status?: number, details?: Record<string, unknown>) {
    super(message);
    this.code = code;
    this.status = status;
    this.details = details;
  }
}

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiError>) => {
    const body = error.response?.data;
    if (body?.error) {
      throw new ApiRequestError(body.error.message, body.error.code, error.response?.status, body.error.details);
    }
    throw new ApiRequestError(error.message, "network_error", error.response?.status);
  },
);

export function staticUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  const base = (import.meta.env.VITE_STATIC_URL as string) ?? "http://localhost:8000/static";
  return `${base}/${path}`;
}
