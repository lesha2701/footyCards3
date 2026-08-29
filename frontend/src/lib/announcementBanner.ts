const STORAGE_PREFIX = "fc_announcement_dismissed_";

export function isAnnouncementDismissed(userId: number, updatedAt: string): boolean {
  try {
    return localStorage.getItem(`${STORAGE_PREFIX}${userId}`) === updatedAt;
  } catch {
    return true;
  }
}

export function dismissAnnouncement(userId: number, updatedAt: string): void {
  try {
    localStorage.setItem(`${STORAGE_PREFIX}${userId}`, updatedAt);
  } catch {
    // Storage unavailable (e.g. private mode) — nothing to persist, the
    // banner will just show again next session, which is an acceptable fallback.
  }
}
