import headlessPlaceholder from "@/assets/halloween/boss-headless-placeholder.svg";

/** Illustrated bosses (src/assets/bosses/<mode>-<code>.webp, 384 px). */
const ART = import.meta.glob<string>("@/assets/bosses/*.webp", { eager: true, import: "default" });

const art = (key: string): string | undefined => ART[`/src/assets/bosses/${key}.webp`];

/** «Клубный рейд» bosses by code (club_raid_service.BOSSES). */
export const raidBossArt = (code: string | null | undefined): string | undefined => (code ? art(`raid-${code}`) : undefined);

// A battle carries only the boss name; the weekly boss screen has its code too.
const KONTRA_CODE_BY_NAME: Record<string, string> = {
  "Тренер-тиран": "tyrant", "Вратарь-стена": "wall", "Продажный судья": "referee", "Фанатский сектор": "ultras",
  "Безголовый вратарь": "headless",
};

/** «Контратака» weekly bosses (kontra_catalog.BOSSES), by code or by name. */
export const kontraBossArt = (code?: string | null, name?: string | null): string | undefined => {
  const key = code || (name ? KONTRA_CODE_BY_NAME[name] : undefined);
  if (!key) return undefined;
  // «🎃 Ночь тыкв»: a drawn placeholder until kontra-headless.webp is added.
  return art(`kontra-${key}`) ?? (key === "headless" ? headlessPlaceholder : undefined);
};
