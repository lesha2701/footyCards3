export type ClubTab = "now" | "together" | "treasury" | "club";

export const CLUB_TABS: ClubTab[] = ["now", "together", "treasury", "club"];

/** Sections that open as a sheet over the club home (components/clubs/ClubSheet). */
export const CLUB_SHEETS = [
  "war", "raid", "quests", "league", "games", "wall", "shop", "treasury", "activity", "stats", "leaderboard",
] as const;

export type ClubSheetKey = (typeof CLUB_SHEETS)[number];
