// Art of the «Карьера игрока» trophies and of the trophy cabinets. A file
// dropped into assets/trophies (<name>.webp|png) or assets/cabinets is picked
// up by name; a trophy without art falls back to its emoji, a cabinet to its
// gradient (SHOWCASE_STYLE). An image an admin uploads for a trophy wins.

const trophyFiles = import.meta.glob<string>("../assets/trophies/*.{webp,png}", { eager: true, import: "default" });
const cabinetFiles = import.meta.glob<string>("../assets/cabinets/*.{webp,png}", { eager: true, import: "default" });

function byName(files: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {};
  for (const [path, url] of Object.entries(files)) {
    const name = path.split("/").pop()!.replace(/\.(webp|png)$/, "");
    out[name] = url;
  }
  return out;
}

const TROPHIES = byName(trophyFiles);
const CABINETS = byName(cabinetFiles);

/** Trophy code -> art file name. */
const TROPHY_FILE: Record<string, string> = {
  player_career_golden_ball: "golden_ball",
  player_career_golden_boot: "golden_boot",
  player_career_top_assist: "top_assist",
  player_career_golden_glove: "golden_glove",
  player_career_best_defender: "best_defender",
  player_career_champion: "champion",
  player_career_top_scorer: "top_scorer",
  player_career_mvp: "mvp",
  player_career_cl_winner: "cl",
  player_career_national_winner: "national",
};

/** The same cups handed out by an admin under a definition of his own. */
const TROPHY_FILE_BY_NAME: Record<string, string> = {
  "золотой мяч": "golden_ball",
  "золотая бутса": "golden_boot",
  "король передач": "top_assist",
  "золотая перчатка": "golden_glove",
  "лучший защитник": "best_defender",
  "лучший бомбардир": "top_scorer",
};

export function trophyArt(code: string, name?: string): string | null {
  const file = TROPHY_FILE[code] ?? TROPHY_FILE_BY_NAME[name?.trim().toLowerCase() ?? ""];
  return (file && TROPHIES[file]) || null;
}

/** Cabinet code ("wood" = the free one) -> backdrop art. */
export function cabinetArt(code: string): string | null {
  return CABINETS[code === "wood" ? "sc_wood" : code] ?? null;
}
