import type { ClubRole } from "@/types";

export const CLUB_ROLE_LABELS: Record<ClubRole, string> = {
  captain: "Капитан",
  vice_captain: "Вице-капитан",
  assistant: "Ассистент",
  treasurer: "Казначей",
  member: "Участник",
};

/** Roles the captain can hand out from the member list (club_service.set_member_role). */
export const ASSIGNABLE_CLUB_ROLES: ClubRole[] = ["member", "assistant", "vice_captain", "treasurer"];

/** Squad, packs, join requests, kicks — mirrors club_service.MANAGER_ROLES. */
export function isClubManager(role: ClubRole | null | undefined): boolean {
  return role === "captain" || role === "vice_captain" || role === "assistant";
}
