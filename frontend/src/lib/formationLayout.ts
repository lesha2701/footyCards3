/** How each club formation is drawn on the pitch: rows of slot codes from
 * the attack (top) down to the goalkeeper, so a formation with two
 * midfield lines (4-2-3-1, 4-3-3 with a holding midfielder) shows them as
 * two rows instead of one crowded line. Slot codes are the backend's
 * (club_formation_service.CLUB_FORMATIONS). */

export const FORMATION_LABELS: Record<string, string> = {
  "4-3-3": "4-3-3",
  "4-3-3H": "4-3-3 (опорник)",
  "4-2-3-1": "4-2-3-1",
  "4-4-2": "4-4-2",
  "3-5-2": "3-5-2",
  "5-3-2": "5-3-2",
  "3-4-3": "3-4-3",
};

export function formationLabel(code: string | null | undefined): string {
  return (code && FORMATION_LABELS[code]) || code || "";
}

const ROWS: Record<string, string[][]> = {
  "4-3-3": [["FWD1", "FWD2", "FWD3"], ["MID1", "MID2", "MID3"], ["DEF1", "DEF2", "DEF3", "DEF4"], ["GK"]],
  "4-3-3H": [["FWD1", "FWD2", "FWD3"], ["MID1", "MID3"], ["MID2"], ["DEF1", "DEF2", "DEF3", "DEF4"], ["GK"]],
  "4-2-3-1": [["FWD1"], ["MID3", "MID4", "MID5"], ["MID1", "MID2"], ["DEF1", "DEF2", "DEF3", "DEF4"], ["GK"]],
  "4-4-2": [["FWD1", "FWD2"], ["MID1", "MID2", "MID3", "MID4"], ["DEF1", "DEF2", "DEF3", "DEF4"], ["GK"]],
  "3-5-2": [["FWD1", "FWD2"], ["MID1", "MID2", "MID3", "MID4", "MID5"], ["DEF1", "DEF2", "DEF3"], ["GK"]],
  "5-3-2": [["FWD1", "FWD2"], ["MID1", "MID2", "MID3"], ["DEF1", "DEF2", "DEF3", "DEF4", "DEF5"], ["GK"]],
  // Wing-backs (DEF4 / DEF5) play in the midfield row.
  "3-4-3": [["FWD1", "FWD2", "FWD3"], ["DEF4", "MID1", "MID2", "DEF5"], ["DEF1", "DEF2", "DEF3"], ["GK"]],
};

export interface PitchRow {
  key: string;
  category: "GK" | "DEF" | "MID" | "FWD";
  codes: string[];
}

function categoryOf(code: string): PitchRow["category"] {
  if (code === "GK") return "GK";
  return code.replace(/\d+$/, "") as PitchRow["category"];
}

/** Rows for `formation` limited to the given slot codes; an unknown
 * formation falls back to one row per line. */
export function pitchRows(formation: string | null | undefined, codes: string[]): PitchRow[] {
  const present = new Set(codes);
  const layout = (formation && ROWS[formation]) || (["FWD", "MID", "DEF", "GK"] as const).map((cat) =>
    codes.filter((c) => categoryOf(c) === cat));
  return layout
    .map((row, i) => ({ key: `${i}-${row.join(",")}`, category: categoryOf(row[0] ?? "GK"), codes: row.filter((c) => present.has(c)) }))
    .filter((row) => row.codes.length > 0);
}

/** Orders a row's slots as the layout lists them. */
export function inRow<T extends { slot_code?: string; code?: string }>(row: PitchRow, slots: T[]): T[] {
  return row.codes
    .map((code) => slots.find((s) => (s.slot_code ?? s.code) === code))
    .filter((s): s is T => s !== undefined);
}

/** Striped grass for squad pitches (components/squad/PitchBackground draws the markings). */
export const PITCH_STYLE = { background: "repeating-linear-gradient(180deg, #145236 0 34px, #11482f 34px 68px)" };
