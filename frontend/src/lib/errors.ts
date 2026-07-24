import { ApiRequestError } from "@/lib/api";

/** Turns a raw API error into a player-friendly message. Special-cases the
 * hourly play-limit conflict (details.hourly_limit/retry_after_seconds) into
 * a clear "try again in N min" message instead of the raw backend string. */
export function formatGameError(err: unknown, fallback: string): string {
  if (err instanceof ApiRequestError) {
    const hourlyLimit = err.details?.hourly_limit;
    if (typeof hourlyLimit === "number") {
      const retryAfterSeconds = err.details?.retry_after_seconds;
      const minutes = typeof retryAfterSeconds === "number" ? Math.max(1, Math.ceil(retryAfterSeconds / 60)) : null;
      return minutes
        ? `Лимит ${hourlyLimit} игры в час исчерпан. Попробуй через ${minutes} мин.`
        : `Лимит ${hourlyLimit} игры в час исчерпан. Попробуй чуть позже.`;
    }
    return err.message;
  }
  return fallback;
}
