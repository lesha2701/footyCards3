const STORAGE_PREFIX = "fc_onboarding_seen_";

export function hasSeenOnboarding(userId: number): boolean {
  try {
    return localStorage.getItem(`${STORAGE_PREFIX}${userId}`) === "1";
  } catch {
    return true;
  }
}

export function markOnboardingSeen(userId: number): void {
  try {
    localStorage.setItem(`${STORAGE_PREFIX}${userId}`, "1");
  } catch {
    // Storage unavailable (e.g. private mode) — nothing to persist, the
    // guide will just show again next session, which is an acceptable fallback.
  }
}
