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
  DEF: ["LB", "CB", "RB"],
  MID: ["CDM", "CM", "CAM", "LM", "RM"],
  FWD: ["LW", "ST", "RW"],
};

export const CATEGORY_LABELS: Record<FormationSlot["category"], string> = {
  GK: "Вратарь",
  DEF: "Защита",
  MID: "Полузащита",
  FWD: "Атака",
};
