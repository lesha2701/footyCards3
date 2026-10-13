import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CareerAnalysis, CareerDivision, CareerSeason, CareerView } from "@/api/career";
import CareerMatchAnalysis from "@/components/career/CareerMatchAnalysis";
import CareerPage from "@/pages/CareerPage";

const fetchCareer = vi.fn<() => Promise<CareerView>>();
const setCareerPlan = vi.fn();
vi.mock("@/api/career", async (orig) => ({
  ...(await orig<typeof import("@/api/career")>()),
  fetchCareer: () => fetchCareer(),
  setCareerPlan: (plan: unknown) => setCareerPlan(plan),
}));

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
  scouting: {
    round_index: 1, opponent_index: 2, opponent_name: "Бот 2", is_bot: true, strength: 72,
    formation: "4-4-2", mentality: "DEFENSIVE", playstyle: "POSSESSION", source: "last_match", form: ["W"],
    hint: "advantage", win_pct: 51.9, counters: ["HIGH_PRESS", "CENTRAL_PLAY"], beats: ["COUNTER_ATTACK", "WING_PLAY"],
    adaptive: true, my_last_playstyle: "CENTRAL_PLAY", threat_styles: ["HIGH_PRESS", "WING_PLAY"],
  },
  familiarity: {
    stored_pct: 4, current_pct: 4, max_pct: 10, step_pct: 2, keep_pct: 50,
    last_formation: "4-3-3", last_playstyle: "CENTRAL_PLAY",
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

  it("prepares the round: scouting, matchup preview, familiarity and a match plan", async () => {
    setCareerPlan.mockResolvedValue({ ...baseView, season: tacticsSeason });
    fetchCareer.mockResolvedValue({ ...baseView, season: tacticsSeason });
    renderPage();
    expect(await screen.findByText("Разведка: Бот 2")).toBeInTheDocument();
    expect(screen.getByText(/В прошлом туре играл/)).toBeInTheDocument();
    expect(screen.getByText(/Опасные для неё стили: Высокий прессинг, Игра флангами/)).toBeInTheDocument();
    // CENTRAL_PLAY vs POSSESSION: CENTRAL counters it.
    expect(screen.getAllByText("Преимущество").length).toBeGreaterThan(0);
    fireEvent.change(screen.getByLabelText("Стиль"), { target: { value: "WING_PLAY" } });
    expect(screen.getAllByText("Невыгодно").length).toBeGreaterThan(0);
    // Switching style keeps 50% of the 4% familiarity.
    expect(screen.getByText("+2.0% / 10%")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "+ Указание" }));
    fireEvent.click(screen.getByRole("button", { name: "Сохранить план" }));
    await vi.waitFor(() => expect(setCareerPlan).toHaveBeenCalled());
    expect(setCareerPlan.mock.calls[0][0]).toMatchObject({
      rules: [{ score: "behind", margin: 1, from_minute: 60, mentality: "ATTACKING", playstyle: null }],
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
    playstyle: "HIGH_PRESS", mentality: "BALANCED", formation: "4-3-3", opponent_playstyle: "POSSESSION",
    matchup: "advantage", familiarity_pct: 6,
    mine: stats, theirs: { ...stats, breakdown: 4 },
    goals_mine: { wing: 1, central: 0, counter: 1, penalty: 0 }, goals_theirs: { wing: 0, central: 1, counter: 0, penalty: 0 },
    instructions: [{ kind: "rule", minute: 63, rule: 0, mentality: "ATTACKING", playstyle: "HIGH_PRESS" }],
    substitutions: [
      { kind: "sub", minute: 70, sub: 0, in: "Петров", out: "Иванов", fatigue: 72 },
      { kind: "sub_skipped", minute: 75, sub: 1 },
    ],
    plan: {
      rules: [{ score: "behind", margin: 1, from_minute: 60, mentality: "ATTACKING", playstyle: null }],
      subs: [
        { minute: 70, slot: null, card_id: null, min_fatigue: 70 },
        { minute: 75, slot: "GK", card_id: null, min_fatigue: 0 },
        { minute: 80, slot: null, card_id: null, min_fatigue: 90 },
      ],
    },
  };

  it("lists only engine-recorded facts: goals by origin, instructions and substitutions", () => {
    render(<CareerMatchAnalysis analysis={analysis} />);
    expect(screen.getByText("Тактический разбор")).toBeInTheDocument();
    expect(screen.getByText("с флангов 1, с контратак 1")).toBeInTheDocument();
    expect(screen.getByText(/указание 1: Атакующий · Высокий прессинг/)).toBeInTheDocument();
    expect(screen.getByText(/замена: Петров вместо Иванов \(усталость 72%\)/)).toBeInTheDocument();
    expect(screen.getByText(/замена 2 не проведена/)).toBeInTheDocument();
    expect(screen.getByText("Замена 3: условие не наступило")).toBeInTheDocument();
    expect(screen.getByText("+6% к рейтингу")).toBeInTheDocument();
  });
});
