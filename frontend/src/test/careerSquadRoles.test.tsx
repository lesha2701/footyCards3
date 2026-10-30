import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CareerSeason, CareerSquadCard, TacticsCatalog } from "@/api/career";
import CareerSquad from "@/components/career/CareerSquad";
import { lineY } from "@/lib/careerRoles";

const setCareerRoles = vi.fn();
const setCareerMarking = vi.fn();
const setCareerPlan = vi.fn();
vi.mock("@/api/career", async (orig) => ({
  ...(await orig<typeof import("@/api/career")>()),
  setCareerRoles: (r: unknown, i: unknown) => setCareerRoles(r, i),
  setCareerMarking: (m: unknown, i: unknown) => setCareerMarking(m, i),
  setCareerPlan: (p: unknown) => setCareerPlan(p),
}));

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

describe("«Состав»: roles of the players", () => {
  beforeEach(() => {
    for (const f of [setCareerRoles, setCareerMarking, setCareerPlan]) f.mockReset().mockResolvedValue({});
  });

  const squad = () => wrap(<CareerSquad season={season} catalog={catalog} onView={vi.fn()} onError={vi.fn()} />);

  it("the legend says what the drawing under the cards shows", () => {
    squad();
    const legend = screen.getByRole("list", { name: "Тактика на поле" });
    expect(legend).toHaveTextContent("Фланги");
    expect(legend).toHaveTextContent("Высокий прессинг");
  });

  it("the roles view: the role of the line under the card; a tap opens the card with role, marking and set pieces", async () => {
    squad();
    expect(screen.queryByText("+ роль")).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Роли игроков" }));
    expect(screen.getByText("+ роль")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "FWD1: Крайнев" }));
    expect(within(screen.getByRole("dialog")).getByLabelText("Энергия 20% — сильно устал")).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Роль: Крайние полузащитники" })).getByRole("radio", { name: /Срезка в центр/ }));
    await vi.waitFor(() => expect(setCareerRoles).toHaveBeenCalledWith({ winger: "inside" }, 2));
    fireEvent.click(screen.getByRole("button", { name: /Опекать звезду: Звездин/ }));
    await vi.waitFor(() => expect(setCareerMarking).toHaveBeenCalledWith(1, 2));
    fireEvent.click(screen.getByRole("button", { name: /Угловые/ }));
    await vi.waitFor(() => expect(setCareerPlan).toHaveBeenCalled());
    expect(setCareerPlan.mock.calls[0][0]).toMatchObject({ round_index: 2, set_pieces: { corner_taker: 1 } });
  });

  it("a set role shows on the card; the keeper's card has no marking or set pieces", () => {
    wrap(<CareerSquad season={{ ...season, roles: { winger: "crosser" } }} catalog={catalog} onView={vi.fn()} onError={vi.fn()} />);
    fireEvent.click(screen.getByRole("tab", { name: "Роли игроков" }));
    expect(screen.getByTitle("Навесы с фланга")).toHaveTextContent("Навесы");
    fireEvent.click(screen.getByRole("button", { name: "GK: Вратарёв" }));
    expect(screen.queryByRole("button", { name: /Опекать звезду/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Угловые/ })).toBeNull();
  });
});
