import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { CareerSeason, CareerSquadCard, TacticsCatalog } from "@/api/career";
import CareerSquad from "@/components/career/CareerSquad";
import { lineY } from "@/lib/squadTactic";

const card = (card_id: number, name: string, position: string, fatigue = 20): CareerSquadCard => ({
  card: { player: { display_name: name, last_name: name, position, rating: 80, image_path: null, club: "Клуб", country: "Страна", rarity: "rare" } } as never,
  card_id, fatigue, injured_rounds: 0, suspended_rounds: 0, yellows: 0, form: 1, owned: true,
});

const catalog: TacticsCatalog = {
  axes: [
    { key: "direction", label: "Направление атаки", values: [
      { value: "wings", label: "Фланги", hint: "атака флангами" }, { value: "center", label: "Центр", hint: "через центр" }] },
    { key: "block", label: "Линия обороны и прессинга", values: [
      { value: "high", label: "Высокий прессинг", hint: "прессинг" }, { value: "low", label: "Низкий блок", hint: "низко" }] },
  ],
  presets: [],
  interactions: [],
  roles: [{ group: "winger", label: "Крайние полузащитники", positions: ["LW", "RW"], values: [
    { value: "crosser", label: "Навесы с фланга", hint: "навесы" }, { value: "inside", label: "Срезка в центр", hint: "срезка" }] }],
};

const season = {
  id: 1, rounds_played: 2, formation: "4-3-3", status: "active", tactics_version: 2, chemistry: null,
  tactic: { direction: "wings", block: "high" },
  slots: [{ code: "GK", category: "GK", ideal_position: "GK" }, { code: "FWD1", category: "FWD", ideal_position: "LW" }],
  lineup: { GK: 9, FWD1: 1 },
  squad: [card(9, "Вратарёв", "GK"), card(1, "Крайнев", "LW", 80)],
  roles: {},
  scouting: { star: { player_id: 5, name: "Звездин", rating: 90, position: "ST" }, marking: null },
  set_pieces: null,
  match_plan: { rules: [], subs: [] },
} as unknown as CareerSeason;

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

describe("the tactic under the squad", () => {
  const band = (top: number, bottom: number) => ({ top, bottom, mid: (top + bottom) / 2 });
  it("the defensive line goes up with a high block and down with a low one", () => {
    const mid = band(100, 160), def = band(200, 260), gk = band(300, 360);
    const [high, middle, low] = ["high", "mid", "low"].map((b) => lineY(b, mid, def, gk));
    expect(high).toBeLessThan(middle);
    expect(middle).toBeGreaterThan(mid.bottom);
    expect(middle).toBeLessThan(def.top);
    expect(low).toBeGreaterThan(def.bottom);
    expect(low).toBeLessThan(gk.top);
  });
});

describe("«Состав»", () => {
  it("the legend says what the drawing under the cards shows; no player roles here", () => {
    wrap(<CareerSquad season={season} catalog={catalog} onView={vi.fn()} onError={vi.fn()} />);
    const legend = screen.getByRole("list", { name: "Тактика на поле" });
    expect(legend).toHaveTextContent("Фланги");
    expect(legend).toHaveTextContent("Высокий прессинг");
    expect(screen.queryByRole("tab", { name: "Роли игроков" })).toBeNull();
  });
});
