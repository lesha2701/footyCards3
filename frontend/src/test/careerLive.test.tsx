import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CareerAchievements, CareerLive, CareerSeason, TacticsCatalog } from "@/api/career";
import { LiveMatchCenter } from "@/components/career/CareerLive";
import { CoachExtras } from "@/components/career/CoachExtras";
import { MarkingCard, PlanHints, RolesCard } from "@/components/career/RolesMarking";

const setCareerHalftime = vi.fn();
const setCareerRoles = vi.fn();
const setCareerMarking = vi.fn();
const fetchCareerLeaderboard = vi.fn();
vi.mock("@/api/career", async (orig) => ({
  ...(await orig<typeof import("@/api/career")>()),
  setCareerHalftime: (o: unknown) => setCareerHalftime(o),
  setCareerRoles: (r: unknown, i: unknown) => setCareerRoles(r, i),
  setCareerMarking: (m: unknown, i: unknown) => setCareerMarking(m, i),
  fetchCareerLeaderboard: (d: unknown) => fetchCareerLeaderboard(d),
}));

const axis = (key: string, label: string, values: [string, string][]) => ({
  key, label, values: values.map(([value, l]) => ({ value, label: l, hint: `подсказка ${l}` })),
});
const catalog: TacticsCatalog = {
  axes: [axis("block", "Линия обороны и прессинга", [["high", "Высокий прессинг"], ["mid", "Средний блок"], ["low", "Низкий блок"]])],
  presets: [],
  interactions: [],
  roles: [
    { group: "winger", label: "Крайние полузащитники", positions: ["LW", "RW", "LM", "RM"], values: [
      { value: "crosser", label: "Навесы с фланга", hint: "навесы" }, { value: "inside", label: "Срезка в центр", hint: "срезка" }] },
    { group: "pivot", label: "Опорник", positions: ["CDM"], values: [
      { value: "destroyer", label: "Разрушитель", hint: "разрушитель" }, { value: "playmaker", label: "Плеймейкер", hint: "плеймейкер" }] },
  ],
};

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

const player = (card_id: number, name: string, position: string, fatigue = 30) => ({ card_id, name, position, rating: 80, fatigue });
const live: CareerLive = {
  round: 3, second_half_at: new Date(Date.now() + 8 * 60_000).toISOString(),
  home: 0, away: 2, home_name: "Dev FC", away_name: "Бот 2", hs: 0, as: 1,
  events: [{ minute: 30, event_type: "goal", team: "b", description: "Гол Бота 2", payload: {} }],
  my_side: "a",
  on: [player(1, "Иванов", "ST", 72), player(2, "Петров", "CM")], bench: [player(50, "Сидоров", "ST", 5)],
  subs_left: 3, mentality: "BALANCED", tactic: { block: "mid" }, orders: null,
};
const handlers = { onView: vi.fn(), onError: vi.fn() };

describe("LiveMatchCenter", () => {
  beforeEach(() => setCareerHalftime.mockReset());

  it("shows the first half and sends half-time orders: mentality, changed axes and a substitution", async () => {
    setCareerHalftime.mockResolvedValue({});
    wrap(<LiveMatchCenter live={live} catalog={catalog} {...handlers} />);
    expect(screen.getByText(/Live · тур 4 · перерыв/)).toBeInTheDocument();
    expect(screen.getByText(/2-й тайм через 7:5\d|2-й тайм через 8:00/)).toBeInTheDocument();
    expect(screen.getByText(/нужно отыгрываться/)).toBeInTheDocument();

    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Настрой" })).getByRole("radio", { name: "Атакующий" }));
    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Линия обороны и прессинга" })).getByRole("radio", { name: "Высокий прессинг" }));
    fireEvent.click(screen.getByRole("button", { name: /Иванов/ }));
    fireEvent.click(screen.getByRole("button", { name: /Сидоров/ }));
    expect(screen.getByText("↓ Иванов")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Отдать указания" }));
    await vi.waitFor(() => expect(setCareerHalftime).toHaveBeenCalled());
    expect(setCareerHalftime.mock.calls[0][0]).toEqual({
      mentality: "ATTACKING", tactic: { block: "high" }, subs: [{ out: 1, in: 50 }],
    });
  });

  it("one tap plans substitutions for the tired: the best-fitting fresh bench player", async () => {
    setCareerHalftime.mockResolvedValue({});
    wrap(<LiveMatchCenter live={{ ...live, bench: [player(51, "Кузнецов", "CM", 0), player(50, "Сидоров", "ST", 5)] }} catalog={catalog} {...handlers} />);
    fireEvent.click(screen.getByRole("button", { name: /Заменить уставших \(1\)/ }));
    expect(screen.getByText("↓ Иванов")).toBeInTheDocument();
    expect(screen.getByText("↑ Сидоров")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Отдать указания" }));
    await vi.waitFor(() => expect(setCareerHalftime).toHaveBeenCalled());
    expect(setCareerHalftime.mock.calls[0][0].subs).toEqual([{ out: 1, in: 50 }]);
  });

  it("the bench opens under the player tapped, the same position first", () => {
    wrap(<LiveMatchCenter live={{ ...live, bench: [player(51, "Кузнецов", "CM", 0), player(50, "Сидоров", "ST", 5)] }} catalog={catalog} {...handlers} />);
    fireEvent.click(screen.getByRole("button", { name: /Петров/ }));
    const options = within(screen.getByLabelText("Замена для Петров")).getAllByRole("button");
    expect(options[0]).toHaveTextContent("Кузнецов");
    expect(options[1]).toHaveTextContent("Сидоров");
  });

  it("confirms saved orders", () => {
    wrap(<LiveMatchCenter live={{ ...live, orders: { mentality: null, tactic: {}, subs: [{ out: 1, in: 50 }] } }} catalog={catalog} {...handlers} />);
    expect(screen.getByText(/Указания приняты/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Обновить указания" })).toBeInTheDocument();
  });
});

const season = {
  rounds_played: 2, roles: { winger: "crosser" },
  slots: [{ code: "GK", category: "GK", ideal_position: "GK" }, { code: "FWD1", category: "FWD", ideal_position: "LW" },
    { code: "MID1", category: "MID", ideal_position: "CM" }],
  lineup: { GK: 9, FWD1: 1, MID1: 2 },
  squad: [
    { card_id: 9, card: { player: { display_name: "Вратарёв" } } }, { card_id: 1, card: { player: { display_name: "Иванов" } } },
    { card_id: 2, card: { player: { display_name: "Петров" } } },
  ],
  scouting: { star: { player_id: 77, name: "Звездин", rating: 88, position: "ST" }, marking: null, marks_you: true },
  plan_hints: [{ code: "tired", text: "Усталость 70+: Иванов. Добавь замены" }],
} as unknown as CareerSeason;

describe("Roles, marking and plan hints", () => {
  beforeEach(() => { setCareerRoles.mockReset(); setCareerMarking.mockReset(); });

  it("offers roles only for lines the formation has", async () => {
    setCareerRoles.mockResolvedValue({});
    wrap(<RolesCard season={season} catalog={catalog} {...handlers} />);
    expect(screen.queryByText("Опорник")).not.toBeInTheDocument(); // no CDM slot
    const group = screen.getByRole("radiogroup", { name: "Крайние полузащитники" });
    expect(within(group).getByRole("radio", { name: "Навесы с фланга" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(within(group).getByRole("radio", { name: "Срезка в центр" }));
    await vi.waitFor(() => expect(setCareerRoles).toHaveBeenCalledWith({ winger: "inside" }, 2));
  });

  it("marks the star with an outfield player and warns about a legend bot", async () => {
    setCareerMarking.mockResolvedValue({});
    wrap(<MarkingCard season={season} {...handlers} />);
    expect(screen.getByText("Звездин")).toBeInTheDocument();
    const select = screen.getByLabelText("Опекает");
    expect(within(select).queryByText("Вратарёв")).not.toBeInTheDocument();
    fireEvent.change(select, { target: { value: "2" } });
    await vi.waitFor(() => expect(setCareerMarking).toHaveBeenCalledWith(2, 2));
    expect(screen.getByText(/возьмёт под опеку твоего лучшего игрока/)).toBeInTheDocument();
  });

  it("lists plan hints", () => {
    wrap(<PlanHints season={season} />);
    expect(screen.getByText(/Усталость 70\+: Иванов/)).toBeInTheDocument();
  });
});

const achievements: CareerAchievements = {
  items: [
    { code: "first_win", icon: "🥇", title: "Первая победа", text: "Выиграй первый матч", unlocked_at: "2026-10-10T10:00:00Z" },
    { code: "cup", icon: "🏅", title: "Кубок", text: "Выиграй кубок", unlocked_at: null },
  ],
  unlocked: 1, total: 2,
  trophies: [{ kind: "title", label: "Чемпион: Вторая лига", division: 3, season_id: 4, at: "2026-10-10T10:00:00Z" }],
  run: { wins: 2, unbeaten: 3, clean: 1 },
};

describe("CoachExtras", () => {
  it("shows the trophy cabinet, achievements and the leaderboard", async () => {
    fetchCareerLeaderboard.mockResolvedValue({
      division: null, divisions: [],
      rows: [{ rank: 1, user_id: 3, name: "Гуру", division: 1, division_name: "Высшая лига", reputation: 400, level: "Легенда",
        titles: 3, promotions: 4, seasons: 9, trophies: 7, achievements: 10, is_me: false }],
      me: { rank: 12, user_id: 1, name: "Dev", division: 3, division_name: "Вторая лига", reputation: 40, level: "Новичок",
        titles: 0, promotions: 1, seasons: 2, trophies: 1, achievements: 1, is_me: true },
    });
    wrap(<CoachExtras achievements={achievements} />);
    fireEvent.click(screen.getByRole("button", { name: /Достижения 1\/2/ }));
    expect(screen.getByText("Чемпион: Вторая лига")).toBeInTheDocument();
    expect(screen.getByText("Первая победа")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Рейтинг тренеров/ }));
    expect(await screen.findByText("Гуру")).toBeInTheDocument();
    expect(screen.getByText("Dev")).toBeInTheDocument();
    expect(fetchCareerLeaderboard).toHaveBeenCalledWith(null);
  });
});
