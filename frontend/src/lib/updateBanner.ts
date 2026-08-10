const STORAGE_PREFIX = "fc_update_dismissed_";

export function isUpdateDismissed(userId: number, broadcastAt: string): boolean {
  try {
    return localStorage.getItem(`${STORAGE_PREFIX}${userId}`) === broadcastAt;
  } catch {
    return true;
  }
}

export function dismissUpdate(userId: number, broadcastAt: string): void {
  try {
    localStorage.setItem(`${STORAGE_PREFIX}${userId}`, broadcastAt);
  } catch {
    // Storage unavailable (e.g. private mode) — nothing to persist, the
    // banner will just show again next session, which is an acceptable fallback.
  }
}
