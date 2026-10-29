import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CareerSeason, CareerSquadCard, TacticsCatalog } from "@/api/career";
import { TacticBoard } from "@/components/career/TacticBoard";
import { LINE_Y, boardLayout } from "@/lib/careerBoard";

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
  card: { player: { display_name: name, last_name: name, position, rating: 80, image_path: null } } as never,
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
  rounds_played: 2, formation: "4-3-3",
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

describe("tactics board layout", () => {
  it("lines stand higher with a high block, the keeper at the bottom; slots carry the line-up", () => {
    const squad = season.squad;
    const high = boardLayout("4-3-3", "high", { GK: 9, FWD1: 1 }, squad);
    const low = boardLayout("4-3-3", "low", { GK: 9, FWD1: 1 }, squad);
    expect(high).toHaveLength(11);
    const def = (l: typeof high) => l.find((p) => p.code === "DEF1")!.y;
    expect(def(high)).toBe(LINE_Y.high.DEF);
    expect(def(low)).toBe(LINE_Y.low.DEF);
    expect(high.find((p) => p.code === "GK")).toMatchObject({ x: 50, y: 128 });
    expect(high.find((p) => p.code === "FWD1")!.entry?.card_id).toBe(1);
    expect(high.find((p) => p.code === "MID1")!.entry).toBeUndefined();
  });
});

describe("tactics board", () => {
  beforeEach(() => {
    for (const f of [setCareerRoles, setCareerMarking, setCareerPlan]) f.mockReset().mockResolvedValue({});
  });

  const board = (over: Partial<Parameters<typeof TacticBoard>[0]> = {}) => {
    const setTactic = vi.fn();
    const setMentality = vi.fn();
    wrap(<TacticBoard season={season} catalog={catalog} formation="4-3-3" tactic={{ direction: "wings", block: "high" }}
      setTactic={setTactic} mentality="BALANCED" setMentality={setMentality} onView={vi.fn()} onError={vi.fn()} {...over} />);
    return { setTactic, setMentality };
  };

  it("a setting on the pitch opens its options with the hint; the mentality is a thermometer", () => {
    const { setTactic, setMentality } = board();
    fireEvent.click(screen.getByRole("button", { name: "Направление атаки: Фланги" }));
    const options = screen.getByRole("radiogroup", { name: "Направление атаки" });
    expect(within(options).getByRole("radio", { name: "Фланги" })).toHaveAttribute("aria-checked", "true");
    expect(options).toHaveTextContent("атака флангами");
    fireEvent.click(within(options).getByRole("radio", { name: "Центр" }));
    // Picking closes the options.
    expect(screen.queryByRole("radiogroup", { name: "Направление атаки" })).toBeNull();
    expect(setTactic).toHaveBeenCalledWith({ direction: "center", block: "high" });
    fireEvent.click(screen.getByRole("radio", { name: "Атакующий" }));
    expect(setMentality).toHaveBeenCalledWith("ATTACKING");
  });

  it("the roles view: the line-up on the pitch; a player card with energy, role, marking and set pieces", async () => {
    board();
    expect(screen.queryByRole("button", { name: "Крайнев, LW" })).toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "Роли игроков" }));
    fireEvent.click(screen.getByRole("button", { name: "Крайнев, LW" }));
    expect(screen.getByLabelText("Энергия 20% — сильно устал")).toBeInTheDocument();
    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Роль: Крайние полузащитники" })).getByRole("radio", { name: /Срезка в центр/ }));
    await vi.waitFor(() => expect(setCareerRoles).toHaveBeenCalledWith({ winger: "inside" }, 2));
    fireEvent.click(screen.getByRole("button", { name: /Опекать звезду: Звездин/ }));
    await vi.waitFor(() => expect(setCareerMarking).toHaveBeenCalledWith(1, 2));
    fireEvent.click(screen.getByRole("button", { name: /Угловые/ }));
    await vi.waitFor(() => expect(setCareerPlan).toHaveBeenCalled());
    expect(setCareerPlan.mock.calls[0][0]).toMatchObject({ round_index: 2, set_pieces: { corner_taker: 1 } });
  });

  it("the keeper's card has no marking or set pieces", () => {
    board();
    fireEvent.click(screen.getByRole("tab", { name: "Роли игроков" }));
    fireEvent.click(screen.getByRole("button", { name: "Вратарёв, GK" }));
    expect(screen.queryByRole("button", { name: /Опекать звезду/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Угловые/ })).toBeNull();
  });
});
