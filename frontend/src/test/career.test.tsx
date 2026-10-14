import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CareerAnalysis, CareerDivision, CareerSeason, CareerView, Tactic, TacticsCatalog } from "@/api/career";
import type { ChemistryOut, UserCard } from "@/types";
import CareerMatchAnalysis from "@/components/career/CareerMatchAnalysis";
import CareerSquad from "@/components/career/CareerSquad";
import CareerPage from "@/pages/CareerPage";

const fetchCareer = vi.fn<() => Promise<CareerView>>();
const setCareerPlan = vi.fn();
const setCareerLineup = vi.fn();
const previewCareerTactic = vi.fn();
vi.mock("@/api/career", async (orig) => ({
  ...(await orig<typeof import("@/api/career")>()),
  fetchCareer: () => fetchCareer(),
  setCareerPlan: (plan: unknown) => setCareerPlan(plan),
  setCareerLineup: (payload: unknown) => setCareerLineup(payload),
  previewCareerTactic: (tactic: unknown) => previewCareerTactic(tactic),
}));

const axis = (key: string, label: string, values: [string, string][]) => ({
  key, label, values: values.map(([value, l]) => ({ value, label: l, hint: `подсказка ${l}` })),
});
const catalog: TacticsCatalog = {
  axes: [
    axis("direction", "Направление атаки", [["wings", "Фланги"], ["mixed", "Смешанно"], ["center", "Центр"]]),
    axis("buildup", "Построение атаки", [["short", "Короткий пас"], ["mixed", "Смешанно"], ["direct", "Прямой пас"]]),
    axis("on_loss", "После потери мяча", [["counterpress", "Контрпрессинг"], ["drop", "Отход в блок"]]),
    axis("on_win", "После отбора", [["fast", "Быстрая атака"], ["keep", "Сохранить мяч"]]),
    axis("block", "Линия обороны и прессинга", [["high", "Высокий прессинг"], ["mid", "Средний блок"], ["low", "Низкий блок"]]),
  ],
  presets: [
    { code: "POSSESSION", label: "Контроль мяча", tactic: { direction: "mixed", buildup: "short", on_loss: "counterpress", on_win: "keep", block: "mid" } },
    { code: "HIGH_PRESS", label: "Прессинг", tactic: { direction: "mixed", buildup: "direct", on_loss: "counterpress", on_win: "fast", block: "high" } },
    { code: "COUNTER_ATTACK", label: "Контратаки", tactic: { direction: "mixed", buildup: "direct", on_loss: "drop", on_win: "fast", block: "low" } },
  ],
  interactions: [],
};
const POSSESSION: Tactic = catalog.presets[0].tactic;
const PRESS: Tactic = catalog.presets[1].tactic;

const division = (n: number): CareerDivision => ({
  division: n, name: ["Высшая лига", "Первая лига", "Вторая лига", "Третья лига", "Любительская лига"][n - 1], count: 5,
  reward_pct: [250, 200, 150, 125, 100][n - 1], bot_level: "pro", bot_level_label: "Профи", promote: 2, relegate: 2,
});

const baseView: CareerView = {
  enabled: true,
  difficulties: [
    { code: "amateur", label: "Любитель", reward_pct: 100 },
    { code: "pro", label: "Профи", reward_pct: 150 },
    { code: "legend", label: "Легенда", reward_pct: 200 },
  ],
  place_rewards: [1500, 1000, 700, 500, 350, 250, 150, 100],
  slots: ["12:00", "19:00"],
  slot_times: [],
  division: division(3),
  divisions: [1, 2, 3, 4, 5].map(division),
  tactics_catalog: catalog,
  season: null,
  invite: null,
};

const teams = Array.from({ length: 8 }, (_, i) => ({
  index: i, name: i === 0 ? "Dev FC" : `Бот ${i}`, is_bot: i !== 0, user_id: i === 0 ? 1 : null, strength: 70,
}));

const activeSeason: CareerSeason = {
  id: 5, status: "active", difficulty: "pro", difficulty_label: "Профи", rounds_played: 1, total_rounds: 14,
  schedule: [], next_round_at: null, invite_expires_at: null, is_creator: true, my_status: "accepted", my_team_index: 0,
  final_place: null, coins_earned: 30,
  participants: [{ user_id: 1, name: "Dev", status: "accepted", team_index: 0 }],
  teams,
  table: teams.map((t) => ({ team_index: t.index, played: 1, won: t.index === 0 ? 1 : 0, drawn: 0, lost: t.index === 0 ? 0 : 1, gf: 1, ga: 0, points: t.index === 0 ? 3 : 0 })),
  rounds: [
    {
      index: 0, at: null, matches: [{ home: 0, away: 1, hs: 2, as: 1, has_events: true }],
      report: { yellow: ["Иванов"], red: [], suspended: [], injured: [], form_up: [], form_down: [] },
    },
    { index: 1, at: null, matches: [{ home: 2, away: 0, hs: null, as: null, has_events: false }], report: null },
  ],
  squad: [], lineup: {}, slots: [], formation: "4-3-3", mentality: "BALANCED", playstyle: "CENTRAL_PLAY",
};

const tacticsSeason: CareerSeason = {
  ...activeSeason,
  difficulty: "pro",
  division: division(3),
  tactics_version: 1,
  tactic: POSSESSION,
  playstyle: "POSSESSION",
  scouting: {
    round_index: 1, opponent_index: 2, opponent_name: "Бот 2", is_bot: true, strength: 72,
    formation: "4-4-2", mentality: "DEFENSIVE", tactic: PRESS, preset: "HIGH_PRESS", source: "last_match", form: ["W"],
    matchup: {
      score: -0.08, hint: "disadvantage",
      items: [{ id: "press_vs_short", label: "Высокий прессинг перехватывает короткий розыгрыш", attacker: "me", favours: "them", value: -0.08 }],
    },
    win_pct: null, adaptive: true, my_last_tactic: POSSESSION, threat: { preset: "HIGH_PRESS", tactic: PRESS },
  },
  familiarity: {
    stored_pct: 4, current_pct: 4, max_pct: 9, step_pct: 2, keep_pct: 50, axis_keep_pct: 80,
    last_formation: "4-3-3", last_tactic: POSSESSION,
  },
  match_plan: null,
  plan_limits: { rules: 3, subs: 3 },
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <CareerPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("CareerPage", () => {
  beforeEach(() => fetchCareer.mockReset());

  it("starts in the player's division (no manual difficulty) with a friend option and the champion reward", async () => {
    fetchCareer.mockResolvedValue(baseView);
    renderPage();
    expect(await screen.findByText("Начать сезон")).toBeInTheDocument();
    expect(screen.getByText("Сезон с другом")).toBeInTheDocument();
    expect(screen.getByText("Вторая лига")).toBeInTheDocument();
    expect(screen.getByText(/Места 1–2 — повышение\. Последние 2 — вылет/)).toBeInTheDocument();
    expect(screen.queryByText("Сложность")).not.toBeInTheDocument();
    // Вторая лига = 150% of the 1st-place reward.
    expect(screen.getByText(/Чемпиону: 2250/)).toBeInTheDocument();
  });

  it("shows promotion after a finished season", async () => {
    fetchCareer.mockResolvedValue({
      ...baseView,
      season: { ...activeSeason, status: "finished", final_place: 1, division: division(3), next_division: division(2) },
    });
    renderPage();
    expect(await screen.findByText("Повышение! Следующий сезон — Первая лига")).toBeInTheDocument();
  });

  it("prepares the round: scouting, tactical axes with a live matchup preview, familiarity and a plan", async () => {
    setCareerPlan.mockResolvedValue({ ...baseView, season: tacticsSeason });
    setCareerLineup.mockResolvedValue({ ...baseView, season: tacticsSeason });
    previewCareerTactic.mockResolvedValue({
      score: 0.1, hint: "advantage",
      items: [{ id: "direct_behind_line", label: "Прямой пас за спину высокой линии", attacker: "me", favours: "me", value: 0.1 }],
    });
    fetchCareer.mockResolvedValue({ ...baseView, season: tacticsSeason });
    renderPage();
    expect(await screen.findByText("Бот 2")).toBeInTheDocument();
    expect(screen.getByText(/В прошлом туре/)).toBeInTheDocument();
    // The opponent may read my last played tactic, and with what.
    expect(screen.getByText(/скорее всего выберет «Прессинг»/)).toBeInTheDocument();
    // Saved tactic vs the scouted one: from the server's report.
    expect(screen.getAllByText("Невыгодно").length).toBeGreaterThan(0);
    expect(screen.getByText("Высокий прессинг перехватывает короткий розыгрыш")).toBeInTheDocument();
    expect(screen.getByText("+4.0%")).toBeInTheDocument();

    // Change one axis: the preview comes from the server, familiarity keeps 80%.
    fireEvent.click(within(screen.getByRole("radiogroup", { name: "Построение атаки" })).getByRole("radio", { name: "Прямой пас" }));
    expect(screen.getByText("Своя тактика")).toBeInTheDocument();
    expect(await screen.findByText("Прямой пас за спину высокой линии")).toBeInTheDocument();
    expect(previewCareerTactic).toHaveBeenCalledWith({ ...POSSESSION, buildup: "direct" });
    expect(screen.getByText("+3.2%")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сохранить тактику" }));
    await vi.waitFor(() => expect(setCareerLineup).toHaveBeenCalled());
    expect(setCareerLineup.mock.calls[0][0]).toMatchObject({ tactic: { ...POSSESSION, buildup: "direct" }, round_index: 1 });

    // A preset chip sets every axis at once.
    fireEvent.click(screen.getByRole("radio", { name: "Контратаки" }));
    expect(within(screen.getByRole("radiogroup", { name: "Линия обороны и прессинга" })).getByRole("radio", { name: "Низкий блок" }))
      .toHaveAttribute("aria-checked", "true");

    fireEvent.click(screen.getByRole("button", { name: "+ Указание" }));
    fireEvent.change(within(screen.getByLabelText("Указание 1")).getByLabelText("Линия обороны и прессинга"), { target: { value: "high" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить план" }));
    await vi.waitFor(() => expect(setCareerPlan).toHaveBeenCalled());
    expect(setCareerPlan.mock.calls[0][0]).toMatchObject({
      rules: [{ score: "behind", margin: 1, from_minute: 60, mentality: "ATTACKING", tactic: { block: "high" } }],
      subs: [],
      round_index: 1,
    });
  });

  it("shows the next opponent and the tabs for an active season", async () => {
    fetchCareer.mockResolvedValue({ ...baseView, season: activeSeason });
    renderPage();
    expect(await screen.findByText(/В гостях: Бот 2/)).toBeInTheDocument();
    expect(screen.getByText(/тур 2 из 14/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Таблица" })).toBeInTheDocument();
    expect(screen.getByText("1 место")).toBeInTheDocument();
  });

  it("shows the after-match report (cards) in the calendar", async () => {
    fetchCareer.mockResolvedValue({ ...baseView, season: activeSeason });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Календарь" }));
    expect(screen.getByText("жёлтые: Иванов")).toBeInTheDocument();
  });

  it("lets an invited friend accept or decline", async () => {
    fetchCareer.mockResolvedValue({
      ...baseView,
      invite: { season_id: 9, difficulty_label: "Легенда", from_name: "Вася", expires_at: null },
    });
    renderPage();
    expect(await screen.findByText("Вася зовёт в общий сезон")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Принять" })).toBeInTheDocument();
  });
});

describe("CareerMatchAnalysis", () => {
  const stats = { attacks: 30, wing_attack: 12, central_attack: 10, recycled: 8, advance: 9, stall: 7, breakdown: 6, counters: 4, counter_chances: 2 };
  const analysis: CareerAnalysis = {
    formation: "4-3-3", mentality: "BALANCED", tactic: PRESS, preset: "HIGH_PRESS", opponent_tactic: POSSESSION,
    matchup: {
      score: 0.08, hint: "advantage",
      items: [{ id: "press_vs_short", label: "Высокий прессинг перехватывает короткий розыгрыш", attacker: "them", favours: "me", value: 0.08 }],
    },
    familiarity_pct: 6,
    mine: stats, theirs: { ...stats, breakdown: 4 },
    goals_mine: { wing: 1, central: 0, counter: 1, penalty: 0 }, goals_theirs: { wing: 0, central: 1, counter: 0, penalty: 0 },
    duels: [{ id: "press_vs_short", label: "Высокий прессинг перехватывает короткий розыгрыш", attacker: "them", applied: 9, attacker_won: 2 }],
    instructions: [{ kind: "rule", minute: 63, rule: 0, mentality: "ATTACKING", tactic: { ...PRESS, block: "low" } }],
    substitutions: [
      { kind: "sub", minute: 70, sub: 0, in: "Петров", out: "Иванов", fatigue: 72 },
      { kind: "sub_skipped", minute: 75, sub: 1 },
    ],
    plan: {
      rules: [{ score: "behind", margin: 1, from_minute: 60, mentality: "ATTACKING", tactic: { block: "low" } }],
      subs: [
        { minute: 70, slot: null, card_id: null, min_fatigue: 70 },
        { minute: 75, slot: "GK", card_id: null, min_fatigue: 0 },
        { minute: 80, slot: null, card_id: null, min_fatigue: 90 },
      ],
    },
  };

  it("lists only engine-recorded facts: goals by origin, instructions and substitutions", () => {
    render(<CareerMatchAnalysis analysis={analysis} catalog={catalog} />);
    expect(screen.getByText("Тактический разбор")).toBeInTheDocument();
    expect(screen.getByText("с флангов 1, с контратак 1")).toBeInTheDocument();
    expect(screen.getByText(/указание 1: Атакующий · низкий блок/)).toBeInTheDocument();
    expect(screen.getByText(/Атаки соперника: 9 дуэлей, прорыв в 2/)).toBeInTheDocument();
    expect(screen.getByText(/замена: Петров вместо Иванов \(усталость 72%\)/)).toBeInTheDocument();
    expect(screen.getByText(/замена 2 не проведена/)).toBeInTheDocument();
    expect(screen.getByText("Замена 3: условие не наступило")).toBeInTheDocument();
    expect(screen.getByText(/сыгранность \+6%/)).toBeInTheDocument();
  });
});

describe("CareerSquad", () => {
  const card = (id: number, name: string, position: string, club: string, country: string) => ({
    card: { id, player: { id, display_name: name, position, rating: 80, club, country, image_path: null } } as unknown as UserCard,
    my_player: null, card_id: id, fatigue: 20, injured_rounds: 0, suspended_rounds: 0, yellows: 0, form: 0, owned: true,
  });
  const chem = {
    enabled: true, strength_bonus: null, formation: "4-3-3", team: 2, team_max: 6,
    links: [{ a: "FWD1", b: "FWD2", level: "strong" as const, points: 2 }],
    players: [
      { slot_code: "FWD1", points: 1, link_sum: 2, on_position: true, rating_bonus: 1 },
      { slot_code: "FWD2", points: 1, link_sum: 2, on_position: true, rating_bonus: 1 },
    ],
    adjacency: [["FWD1", "FWD2"]] as [string, string][],
    rules: { link_strong: 2, link_medium: 1, thresholds: [1, 2, 4], player_max: 3, player_floor: 0, rating_per_point: 1, off_position_penalty: 0 },
  };
  const season: CareerSeason = {
    ...activeSeason, tactics_version: 1, tactic: POSSESSION,
    slots: [{ code: "FWD1", category: "FWD", ideal_position: "LW" }, { code: "FWD2", category: "FWD", ideal_position: "ST" }],
    lineup: { FWD1: 1, FWD2: 2 },
    squad: [card(1, "Иван Комаров", "LW", "Спартак", "Россия"), card(2, "Пётр Жуков", "ST", "Спартак", "Россия"),
      card(3, "Луис Гомес", "ST", "Бока", "Аргентина")],
    chemistry: chem as unknown as ChemistryOut,
  };

  it("shows the XI with photos, chemistry and the chemistry cost of a swap", () => {
    const client = new QueryClient();
    render(<QueryClientProvider client={client}><CareerSquad season={season} onView={() => {}} onError={() => {}} /></QueryClientProvider>);
    expect(screen.getByRole("button", { name: "FWD2: Пётр Жуков" })).toBeInTheDocument();
    expect(screen.getByText("Запас · 1")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "FWD2: Пётр Жуков" }));
    // Гомес shares neither club nor country with the LW: chemistry drops.
    expect(screen.getByText("-2 хим.")).toBeInTheDocument();
  });
});
