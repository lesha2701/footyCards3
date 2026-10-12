import cases from "./chemistryCases.json";
import { chemistryFrozenText, chemistryGain, chemistrySwapHints, computeChemistry, linkLevel, playerPoints } from "@/lib/chemistry";
import type { ChemistryOut, ChemistryRules } from "@/types";

interface Case {
  name: string;
  formation: string;
  rules: ChemistryRules;
  slot_count: number;
  adjacency: [string, string][];
  players: { slot: string; club: string; country: string; position: string }[];
  expected: { team: number; team_max: number; links: unknown[]; players: Record<string, unknown> };
}

// Ideal positions per slot code for the formations used in the fixture
// (backend club_formation_service.CLUB_FORMATIONS).
const IDEAL: Record<string, Record<string, string>> = {
  "4-3-3": { GK: "GK", DEF1: "LB", DEF2: "CB", DEF3: "CB", DEF4: "RB", MID1: "CDM", MID2: "CM", MID3: "CAM", FWD1: "LW", FWD2: "ST", FWD3: "RW" },
  "4-4-2": { GK: "GK", DEF1: "LB", DEF2: "CB", DEF3: "CB", DEF4: "RB", MID1: "LM", MID2: "CM", MID3: "CM", MID4: "RM", FWD1: "ST", FWD2: "ST" },
};

describe("chemistry parity with the backend", () => {
  for (const c of cases as unknown as Case[]) {
    it(c.name, () => {
      const result = computeChemistry(
        c.players.map((p) => ({ ...p, idealPosition: IDEAL[c.formation][p.slot] })),
        c.adjacency, c.rules, c.slot_count,
      );
      expect(result.team).toBe(c.expected.team);
      expect(result.teamMax).toBe(c.expected.team_max);
      expect(result.links).toEqual(c.expected.links);
      const players = Object.fromEntries(
        Object.entries(result.players).map(([k, v]) => [k, { points: v.points, link_sum: v.link_sum, on_position: v.on_position, rating_bonus: v.rating_bonus }]),
      );
      expect(players).toEqual(c.expected.players);
    });
  }
});

const rules: ChemistryRules = {
  link_strong: 2, link_medium: 1, thresholds: [1, 2, 4], player_max: 3, player_floor: 0, rating_per_point: 1, off_position_penalty: 0,
};

describe("chemistry helpers", () => {
  it("link levels and points", () => {
    expect(linkLevel({ club: "Real ", country: "Spain" }, { club: "Real", country: "Spain" })).toBe("strong");
    expect(linkLevel({ club: "Real", country: "Spain" }, { club: "Barca", country: "Spain" })).toBe("medium");
    expect(linkLevel({ club: "", country: "" }, { club: "", country: "" })).toBe("none");
    expect([0, 1, 2, 3, 4].map((s) => playerPoints(s, true, rules))).toEqual([0, 1, 2, 2, 3]);
    expect(playerPoints(9, false, { ...rules, player_floor: 2 })).toBe(0);
  });

  it("gain and swap hints for a hypothetical card", () => {
    const chemistry = { enabled: true, rules, adjacency: [["GK", "DEF2"], ["GK", "DEF3"]] } as unknown as ChemistryOut;
    const slots = [
      { slot_code: "GK", ideal_position: "GK", player: { id: 1, display_name: "A", club: "Real", country: "Spain", position: "GK" } },
      { slot_code: "DEF2", ideal_position: "CB", player: { id: 2, display_name: "B", club: "X", country: "Y", position: "CB" } },
      { slot_code: "DEF3", ideal_position: "CB", player: null },
    ];
    const candidate = { club: "Real", country: "Spain", position: "CB" };
    // GK goes 0 -> 2 (sum 2), the new DEF3 gets 2 -> team +4.
    expect(chemistryGain(chemistry, slots, "DEF3", candidate)).toBe(4);
    const hints = chemistrySwapHints(chemistry, slots, (s) =>
      s.slot_code === "GK" ? [] : [{ cardId: 9, playerId: 9, name: "C", ...candidate }],
    );
    // Same +4 either way (replacing B in DEF2, or filling DEF3); ties by slot code.
    expect(hints).toEqual([
      { slotCode: "DEF2", cardId: 9, name: "C", currentName: "B", gain: 4 },
      { slotCode: "DEF3", cardId: 9, name: "C", currentName: null, gain: 4 },
    ]);
    expect(chemistryGain({ ...chemistry, enabled: false }, slots, "DEF3", candidate)).toBeNull();
  });
});

describe("chemistryFrozenText", () => {
  const base: ChemistryOut = {
    enabled: false, strength_bonus: null, formation: null, team: 0, team_max: 0, links: [], players: [], adjacency: [], rules: null,
  };

  it("says nothing outside a running tournament", () => {
    expect(chemistryFrozenText(undefined)).toBeNull();
    expect(chemistryFrozenText({ ...base, enabled: true, live_enabled: true })).toBeNull();
  });

  it("explains frozen rules and a tournament that started before the switch", () => {
    expect(chemistryFrozenText({ ...base, enabled: true, frozen: true })).toMatch(/зафиксированным/);
    expect(chemistryFrozenText({ ...base, frozen: true, live_enabled: true })).toMatch(/не действует/);
    expect(chemistryFrozenText({ ...base, frozen: true, live_enabled: false })).toBeNull();
  });
});
