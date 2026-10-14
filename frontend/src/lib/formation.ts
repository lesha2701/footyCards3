export interface FormationSlot {
  code: string;
  category: "GK" | "DEF" | "MID" | "FWD";
  idealPosition: string;
}

export const FORMATION_SLOTS: FormationSlot[] = [
  { code: "GK", category: "GK", idealPosition: "GK" },
  { code: "DEF1", category: "DEF", idealPosition: "LB" },
  { code: "DEF2", category: "DEF", idealPosition: "CB" },
  { code: "DEF3", category: "DEF", idealPosition: "CB" },
  { code: "DEF4", category: "DEF", idealPosition: "RB" },
  { code: "MID1", category: "MID", idealPosition: "CDM" },
  { code: "MID2", category: "MID", idealPosition: "CM" },
  { code: "MID3", category: "MID", idealPosition: "CAM" },
  { code: "FWD1", category: "FWD", idealPosition: "LW" },
  { code: "FWD2", category: "FWD", idealPosition: "ST" },
  { code: "FWD3", category: "FWD", idealPosition: "RW" },
];

export const CATEGORY_POSITIONS: Record<FormationSlot["category"], string[]> = {
  GK: ["GK"],
  DEF: ["LB", "CB", "RB", "LWB", "RWB"],
  MID: ["CDM", "CM", "CAM", "LM", "RM"],
  FWD: ["LW", "ST", "RW"],
};

/** Full-backs and wing-backs count as each other's ideal position (as on
 * the backend: lineup_service.on_ideal_position). */
const POSITION_EQUIVALENTS: Record<string, string> = { LB: "LWB", LWB: "LB", RB: "RWB", RWB: "RB" };

export function onIdealPosition(position: string | null | undefined, ideal: string): boolean {
  return !!position && (position === ideal || POSITION_EQUIVALENTS[position] === ideal);
}

export const CATEGORY_LABELS: Record<FormationSlot["category"], string> = {
  GK: "Вратарь",
  DEF: "Защита",
  MID: "Полузащита",
  FWD: "Атака",
};

export const TACTICS: { value: "attacking" | "balanced" | "defensive"; label: string; description: string }[] = [
  { value: "attacking", label: "Атакующая", description: "+Сила атаки" },
  { value: "balanced", label: "Сбалансированная", description: "+Бонус всем" },
  { value: "defensive", label: "Оборонительная", description: "+Сила защиты" },
];
