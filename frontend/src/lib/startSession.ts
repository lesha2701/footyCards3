/** The first request of the app (POST /auth/session) with a deadline and
 * a couple of quiet retries: without them a stalled backend kept players on
 * the black loading screen for as long as the connection hung. Refusals
 * (4xx: bad initData, banned…) are final — retrying can't change them. */
import { ApiRequestError } from "@/lib/api";

export const SESSION_TIMEOUT_MS = 12_000;
export const SESSION_ATTEMPTS = 3;
export const SESSION_RETRY_DELAY_MS = 1_500;

function retryable(err: unknown): boolean {
  if (!(err instanceof ApiRequestError)) return true;
  return err.status === undefined || err.status >= 500 || err.status === 408;
}

export async function startSession<T>(
  request: (timeoutMs: number) => Promise<T>,
  opts: { attempts?: number; delayMs?: number; timeoutMs?: number } = {},
): Promise<T> {
  const attempts = opts.attempts ?? SESSION_ATTEMPTS;
  const delayMs = opts.delayMs ?? SESSION_RETRY_DELAY_MS;
  const timeoutMs = opts.timeoutMs ?? SESSION_TIMEOUT_MS;
  let last: unknown;
  for (let i = 0; i < attempts; i++) {
    try {
      return await request(timeoutMs);
    } catch (err) {
      last = err;
      if (!retryable(err) || i === attempts - 1) break;
      await new Promise((r) => setTimeout(r, delayMs * (i + 1)));
    }
  }
  throw last;
}
