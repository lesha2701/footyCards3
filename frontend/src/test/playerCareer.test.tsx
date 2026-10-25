import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PlayerCareerClub, PlayerCareerSeason, PlayerCareerView } from "@/api/playerCareer";
import PlayerCareerPage from "@/pages/PlayerCareerPage";

const fetchPlayerCareer = vi.fn<() => Promise<PlayerCareerView>>();
const signPlayerCareerContract = vi.fn();
const counterPlayerCareerOffer = vi.fn();
const acceptPlayerCareerOffer = vi.fn();
const playPlayerCareerMoment = vi.fn();
const answerPlayerCareerEvent = vi.fn();
const openPlayerCareerChest = vi.fn();
const fetchFriendsLeague = vi.fn();
const createFriendsLeague = vi.fn();
vi.mock("@/api/playerCareer", async (orig) => ({
  ...(await orig<typeof import("@/api/playerCareer")>()),
  fetchPlayerCareer: () => fetchPlayerCareer(),
  signPlayerCareerContract: (...args: unknown[]) => signPlayerCareerContract(...args),
  counterPlayerCareerOffer: (...args: unknown[]) => counterPlayerCareerOffer(...args),
  acceptPlayerCareerOffer: (...args: unknown[]) => acceptPlayerCareerOffer(...args),
  playPlayerCareerMoment: (...args: unknown[]) => playPlayerCareerMoment(...args),
  answerPlayerCareerEvent: (...args: unknown[]) => answerPlayerCareerEvent(...args),
  openPlayerCareerChest: () => openPlayerCareerChest(),
  fetchFriendsLeague: () => fetchFriendsLeague(),
  createFriendsLeague: (...args: unknown[]) => createFriendsLeague(...args),
}));

const top = { id: 1, name: "Высшая лига", level: 1 };
const low = { id: 5, name: "Любительская лига", level: 5 };
const clubs: PlayerCareerClub[] = [
  {
    key: "cc:1", name: "Барселона", rating: 86, is_demo: false, real_cards: 12, reputation_needed: 450,
    locked_reason: "Нужен престиж 450", stars: ["Месси"], salary: 3600, league: top, level: 1, club_stars: 5,
    legend: { player_name: "Легенда", goals: 47, seasons: 5 }, expected_role: "bench",
  },
  {
    key: "cc:9", name: "Юность", rating: 52, is_demo: true, real_cards: 0, reputation_needed: 0,
    locked_reason: null, stars: [], salary: 150, league: low, level: 5, club_stars: 1, legend: null, expected_role: "starter",
  },
];

const base: PlayerCareerView = {
  enabled: true, has_player: true, player: null, rating: 52, reputation: 0,
  career: { seasons: 0, matches: 0, goals: 0, assists: 0, titles: 0, top_scorer: 0, mvp: 0 },
  club: null, clubs, season: null, can_change_club: true,
  rewards: { win: 25, draw: 10, goal: 10, xp: 15, places: [1000, 700, 500, 350, 250, 180, 120, 80], objective_coins: 150, objective_rep: 5 },
  history: [], freshness: { value: 88, per_match: 15 }, contract: null,
  national: { country: null, prestige_needed: 150, called_up: false }, cups: [], golden_ball: null,
  haggle_steps: [10, 20, 30], max_counters: 2,
  role: null, role_label: null, trust: 50, trust_starter: 70, trust_captain: 85, injury_rounds: 0, pending: null,
  event: null, news: [], legends: [], chest: { available: true, coins_min: 50, coins_max: 200, token_pct: 10 },
  weekly: { week: "2026-W42", tasks: [] },
  shop: {
    pro_stars: 299, pro_days: 30, pro_xp_pct: 50, agent_stars: 50, agent_haggle_bonus: 15, refresh_coins: 300, refresh_stars: 15,
    heal_coins: 500, heal_stars: 20, save_offer_stars: 30, fast_enabled: false, fast_stars: 100, fast_round_minutes: 120, pro: false, pro_until: null,
    agent_credits: 0, fast_season_credits: 0,
  },
  fast: false,
};

const finished: PlayerCareerSeason = {
  id: 1, status: "finished", rounds_played: 14, total_rounds: 14, next_round_at: null,
  teams: [{ index: 0, name: "Юность", rating: 52, is_mine: true }, { index: 1, name: "Заря", rating: 52, is_mine: false }],
  table: [], rounds: [], stats: { matches: 14, goals: 9, assists: 4, avg_rating: 7.6 }, scorers: [],
  final_place: 1, coins_earned: 1400, awards: ["Чемпион лиги", "Игрок сезона"], league: low, agent: false, saved: false,
  offers: [
    {
      key: "cc:9", name: "Юность", rating: 52, club_stars: 1, league: "Любительская лига", level: 5, salary: 160, bonus: 30,
      counters: 0, status: "open", renewal: true, last: null,
    },
    {
      key: "cc:7", name: "Заря", rating: 58, club_stars: 2, league: "Любительская лига", level: 5, salary: 220, bonus: 120,
      counters: 0, status: "open", renewal: false, last: null,
    },
  ],
  salary: 150, objective_coins: 300,
  objectives: [
    { code: "place", target: 2, label: "Финишировать не ниже 2 места", value: 1, met: true },
    { code: "goals", target: 8, label: "Забить 8 голов", value: 9, met: true },
    { code: "avg_rating", target: 6.8, label: "Средняя оценка 6.8+", value: 6.5, met: false },
  ],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <PlayerCareerPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("PlayerCareerPage", () => {
  beforeEach(() => {
    fetchPlayerCareer.mockReset();
    signPlayerCareerContract.mockReset();
    counterPlayerCareerOffer.mockReset();
    acceptPlayerCareerOffer.mockReset();
  });

  it("picks a club by division, shows prestige locks and salary", async () => {
    fetchPlayerCareer.mockResolvedValue(base);
    signPlayerCareerContract.mockResolvedValue({ ...base, club: clubs[1] });
    renderPage();
    expect(await screen.findByText("Выбери клуб")).toBeInTheDocument();
    // Opens on the lowest open division; the top one is locked.
    expect(screen.getByRole("button", { name: /Юность/ })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: /Высшая лига/ }));
    expect(screen.getByText(/Нужен престиж 450/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Барселона/ })).toBeDisabled();
    expect(screen.getByText(/Зарплата 3600 за сезон · престиж от 450/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Любительская лига/ }));
    fireEvent.click(screen.getByRole("button", { name: /Юность/ }));
    await waitFor(() => expect(signPlayerCareerContract).toHaveBeenCalled());
    expect(signPlayerCareerContract.mock.calls[0][0]).toBe("cc:9");
  });

  it("runs the transfer window: haggle, walk-away and accept", async () => {
    const view: PlayerCareerView = {
      ...base, club: clubs[1], season: finished, can_change_club: true, reputation: 60,
      contract: { salary: 150, seasons_left: 0, expired: true, free_agent_level: 4 },
      history: [{
        id: 1, club: "Юность", club_rating: 52, place: 1, matches: 14, goals: 9, assists: 4, avg_rating: 7.6,
        awards: ["Чемпион лиги"], coins_earned: 1400, finished_at: "2026-10-10T19:00:00Z",
      }],
    };
    fetchPlayerCareer.mockResolvedValue(view);
    counterPlayerCareerOffer.mockResolvedValue({
      ...view,
      season: { ...finished, offers: [{ ...finished.offers[0], status: "withdrawn", last: "walked" }, finished.offers[1]] },
      haggle: { club: "Юность", agreed: false, chance: 50 },
    });
    acceptPlayerCareerOffer.mockResolvedValue({
      ...view, contract: { salary: 220, seasons_left: 2, expired: false, free_agent_level: 4 },
      season: { ...finished, offers: [{ ...finished.offers[0], status: "withdrawn" }, { ...finished.offers[1], status: "accepted" }] },
    });
    renderPage();
    expect(await screen.findByTestId("contract-expired")).toHaveTextContent("Прими одно из предложений");
    const windowBlock = screen.getByTestId("transfer-window");
    expect(windowBlock).toHaveTextContent("Продление · Юность");
    expect(screen.getByTestId("career-objectives")).toHaveTextContent("Забить 8 голов");
    expect(screen.getByTestId("career-timeline")).toHaveTextContent("Сезон 1 · Юность");

    fireEvent.click(screen.getAllByRole("button", { name: "+30%" })[0]);
    await waitFor(() => expect(counterPlayerCareerOffer).toHaveBeenCalledWith("cc:9", 30));
    expect(await screen.findByText("«Юность» отказался и ушёл.")).toBeInTheDocument();
    expect(screen.getByText("Клуб ушёл")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Принять" }));
    await waitFor(() => expect(acceptPlayerCareerOffer).toHaveBeenCalledWith("cc:7"));
  });

  it("shows cups, the national-team status and the «Золотой мяч» race", async () => {
    fetchPlayerCareer.mockResolvedValue({
      ...base, club: clubs[1], reputation: 160, contract: { salary: 150, seasons_left: 1, expired: false, free_agent_level: 4 },
      national: { country: "Испания", prestige_needed: 150, called_up: true },
      cups: [{
        id: 3, kind: "national", title: "Турнир сборных · Испания", status: "active", rounds_played: 1,
        next_round_at: "2026-10-17T16:00:00Z", alive: true, won: false, award: null, coins_earned: 200, my_team: "Испания",
        rounds: [
          {
            label: "1/4 финала", at: null, me: { played: true, goals: 1, assists: 0, rating: 7.4, own: 2, opp: 1, pens: false, won: true, opponent: "Бразилия" },
            matches: [{ home: "Испания", away: "Бразилия", home_mine: true, away_mine: false, hs: 2, away_score: 1, pens: false, winner_mine: true, home_won: true }],
          },
          { label: "1/2 финала", at: null, me: null, matches: [{ home: "Испания", away: "Франция", home_mine: true, away_mine: false, hs: null, away_score: null, pens: null, winner_mine: null, home_won: null }] },
        ],
      }],
      golden_ball: {
        month: "2026-10", month_label: "Октябрь 2026", min_matches: 8, prize_coins: 3000, prize_prestige: 50,
        weights: { FWD: { goals: 3, assists: 2, clean_sheets: 0 }, GK: { goals: 6, assists: 3, clean_sheets: 7 } },
        table: [{ place: 1, user_id: 7, user_name: "Петя", is_me: false, matches: 10, goals: 0, assists: 0, clean_sheets: 6, line: "GK", avg_rating: 7.4, score: 116 }],
        me: { place: 0, user_id: 1, user_name: "Я", is_me: true, matches: 5, goals: 2, assists: 1, clean_sheets: 0, line: "FWD", avg_rating: 7, score: 78 },
        winners: [{ month: "2026-09", month_label: "Сентябрь 2026", user_name: "Вася", is_me: false, score: 120, goals: 11, assists: 4, avg_rating: 7.9 }],
      },
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Кубки" }));
    expect(screen.getByTestId("national-status")).toHaveTextContent("Ты в сборной: Испания");
    const cup = screen.getByTestId("cup-national");
    expect(cup).toHaveTextContent("Турнир сборных · Испания");
    expect(cup).toHaveTextContent("2:1");
    expect(cup).toHaveTextContent("оценка 7.4");

    fireEvent.click(screen.getByRole("button", { name: "Золотой мяч" }));
    const ball = screen.getByTestId("golden-ball");
    expect(ball).toHaveTextContent("Октябрь 2026");
    expect(ball).toHaveTextContent("матчей 5/8");
    expect(ball).toHaveTextContent("Сентябрь 2026: Вася");
    expect(screen.getByTestId("golden-ball-weights")).toHaveTextContent("Вратарь: гол 6 · пас 3 · на ноль 7");
    expect(ball).toHaveTextContent("🧱 6");
  });

  it("plays a key moment: action, timing, result", async () => {
    const active: PlayerCareerSeason = {
      ...finished, status: "active", rounds_played: 1, final_place: null, offers: [],
      rounds: [{ index: 0, at: null, home: 0, away: 1, hs: 1, away_score: 1, me: { played: true, goals: 0, assists: 0, rating: null, own: 1, opp: 1, opponent: "Заря" } }],
    };
    const pending = {
      round: 0, deadline: "2099-01-01T12:00:00Z", line: "FWD",
      moments: [{
        i: 0, kind: "attack" as const, minute: 34, text: "Ты получаешь мяч у штрафной — момент!", status: "open" as const,
        choice: null, hit: null, success: null, auto: false,
        options: [{ code: "shot", label: "Удар по воротам", chance: 45, chance_hit: 63 }, { code: "pass", label: "Пас под удар", chance: 55, chance_hit: 73 }],
      }],
    };
    const view = { ...base, club: clubs[1], season: active, pending, contract: { salary: 150, seasons_left: 1, expired: false, free_agent_level: 4 } };
    fetchPlayerCareer.mockResolvedValue(view);
    playPlayerCareerMoment.mockResolvedValue({
      ...view, pending: null, moment_result: { i: 0, kind: "attack", choice: "shot", success: true, chance: 63 },
    });
    renderPage();
    const block = await screen.findByTestId("key-moments");
    expect(block).toHaveTextContent("«Заря» · пока 1:1");
    fireEvent.click(screen.getByRole("button", { name: "Играть" }));
    fireEvent.click(screen.getByRole("button", { name: /Удар по воротам/ }));
    expect(screen.getByTestId("moment-bar")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Сейчас!" }));
    await waitFor(() => expect(playPlayerCareerMoment).toHaveBeenCalled());
    expect(playPlayerCareerMoment.mock.calls[0].slice(0, 2)).toEqual([0, "shot"]);
    expect(await screen.findByText("ГОЛ!")).toBeInTheDocument();
  });

  it("answers a story event and shows role, trust and an injury", async () => {
    const view = {
      ...base, club: { ...clubs[1] }, role: "bench" as const, role_label: "Запасной", trust: 40, injury_rounds: 2,
      contract: { salary: 150, seasons_left: 1, expired: false, free_agent_level: 4 },
      event: {
        id: 1, code: "ad", title: "Рекламный контракт", text: "Бренд зовёт на съёмку", status: "open",
        choices: [{ key: "sign", label: "Согласиться", effects: { coins: 300, freshness: -15 } }, { key: "rest", label: "Отдохнуть", effects: { freshness: 15 } }],
      },
      news: [{ round: 3, headline: "Хет-трик Виктора!" }],
      legends: [{ place: 1, user_name: "Петя", player_name: "Легенда", is_me: false, seasons: 4, matches: 50, goals: 30, assists: 5, titles: 1 }],
    };
    fetchPlayerCareer.mockResolvedValue(view);
    answerPlayerCareerEvent.mockResolvedValue({ ...view, event: null });
    renderPage();
    const event = await screen.findByTestId("story-event");
    expect(event).toHaveTextContent("+300 монет · -15 свежесть");
    expect(screen.getByTestId("career-status")).toHaveTextContent("Запасной");
    expect(screen.getByTestId("injury")).toHaveTextContent("пропустит ещё 2 тура");
    expect(screen.getByTestId("news")).toHaveTextContent("Хет-трик Виктора!");
    expect(screen.getByTestId("hall-of-fame")).toHaveTextContent("Легенда");
    fireEvent.click(screen.getByRole("button", { name: /Согласиться/ }));
    await waitFor(() => expect(answerPlayerCareerEvent).toHaveBeenCalledWith(1, "sign"));
  });

  it("opens the daily chest and shows Pro in the bonus tab; invites friends", async () => {
    fetchPlayerCareer.mockResolvedValue({ ...base, club: clubs[1], contract: { salary: 150, seasons_left: 1, expired: false, free_agent_level: 4 } });
    openPlayerCareerChest.mockResolvedValue({ coins: 120, token: null, balance: 1000 });
    fetchFriendsLeague.mockResolvedValue({
      league: null, invites: [], can_create: true, derby_multiplier: 2, rewards: [800, 500, 300],
      friends: [{ user_id: 7, name: "Петя", player_name: "Пётр" }],
    });
    createFriendsLeague.mockResolvedValue({ league: null, invites: [], can_create: false, friends: [], derby_multiplier: 2, rewards: [] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Бонусы" }));
    expect(screen.getByTestId("career-pro")).toHaveTextContent("Подключить на 30 дней · ⭐ 299");
    fireEvent.click(screen.getByRole("button", { name: "Открыть" }));
    expect(await screen.findByText("+120 монет")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Лига друзей" }));
    fireEvent.click(await screen.findByRole("button", { name: /Пётр/ }));
    fireEvent.click(screen.getByRole("button", { name: "Позвать (1)" }));
    await waitFor(() => expect(createFriendsLeague).toHaveBeenCalled());
    expect(createFriendsLeague.mock.calls[0][0]).toEqual([7]);
  });
});
