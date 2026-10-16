import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { PlayerCareerSeason, PlayerCareerView } from "@/api/playerCareer";
import PlayerCareerPage from "@/pages/PlayerCareerPage";

const fetchPlayerCareer = vi.fn<() => Promise<PlayerCareerView>>();
const signPlayerCareerContract = vi.fn();
vi.mock("@/api/playerCareer", async (orig) => ({
  ...(await orig<typeof import("@/api/playerCareer")>()),
  fetchPlayerCareer: () => fetchPlayerCareer(),
  signPlayerCareerContract: (...args: unknown[]) => signPlayerCareerContract(...args),
}));

const clubs = [
  { key: "club:Барселона", name: "Барселона", rating: 86, is_demo: false, real_cards: 12, reputation_needed: 104, locked_reason: "Нужен рейтинг 81+", stars: ["Месси"], salary: 860 },
  { key: "demo:Юность", name: "Юность", rating: 48, is_demo: true, real_cards: 0, reputation_needed: 0, locked_reason: null, stars: [], salary: 480 },
];

const base: PlayerCareerView = {
  enabled: true, has_player: true, player: null, rating: 52, reputation: 0,
  career: { seasons: 0, matches: 0, goals: 0, assists: 0, titles: 0, top_scorer: 0, mvp: 0 },
  club: null, clubs, season: null, can_change_club: true,
  rewards: { win: 25, draw: 10, goal: 10, xp: 15, places: [1000, 700, 500, 350, 250, 180, 120, 80], objective_coins: 150, objective_rep: 5 },
  history: [], freshness: { value: 88, per_match: 12 },
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
  });

  it("lists clubs, locks the ones out of reach and signs an open one", async () => {
    fetchPlayerCareer.mockResolvedValue(base);
    signPlayerCareerContract.mockResolvedValue({ ...base, club: clubs[1] });
    renderPage();
    expect(await screen.findByText("Выбери клуб")).toBeInTheDocument();
    expect(screen.getByText(/Нужен рейтинг 81\+/)).toBeInTheDocument();
    expect(screen.getByText("Зарплата 480 за сезон")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Барселона/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /Юность/ }));
    await waitFor(() => expect(signPlayerCareerContract).toHaveBeenCalled());
    expect(signPlayerCareerContract.mock.calls[0][0]).toBe("demo:Юность");
  });

  it("shows a finished season with awards and transfer offers", async () => {
    const season: PlayerCareerSeason = {
      id: 1, status: "finished", rounds_played: 14, total_rounds: 14, next_round_at: null,
      teams: [{ index: 0, name: "Юность", rating: 48, is_mine: true }, { index: 1, name: "Заря", rating: 52, is_mine: false }],
      table: [], rounds: [], stats: { matches: 14, goals: 9, assists: 4, avg_rating: 7.6 }, scorers: [],
      final_place: 1, coins_earned: 1400, awards: ["Чемпион лиги", "Игрок сезона"],
      offers: [{ key: "demo:Заря", name: "Заря", rating: 52 }],
      salary: 480, objective_coins: 300,
      objectives: [
        { code: "place", target: 2, label: "Финишировать не ниже 2 места", value: 1, met: true },
        { code: "goals", target: 8, label: "Забить 8 голов", value: 9, met: true },
        { code: "avg_rating", target: 6.8, label: "Средняя оценка 6.8+", value: 6.5, met: false },
      ],
    };
    const history = [{
      id: 1, club: "Юность", club_rating: 48, place: 1, matches: 14, goals: 9, assists: 4, avg_rating: 7.6,
      awards: ["Чемпион лиги"], coins_earned: 1400, finished_at: "2026-10-10T19:00:00Z",
    }];
    fetchPlayerCareer.mockResolvedValue({ ...base, club: clubs[1], season, history });
    renderPage();
    expect(await screen.findByText("Сезон завершён · 1 место")).toBeInTheDocument();
    expect(screen.getByText(/Чемпион лиги · Игрок сезона/)).toBeInTheDocument();
    expect(screen.getByText("Предложения от клубов")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Новый сезон/ })).toBeInTheDocument();
    expect(screen.getByTestId("career-objectives")).toHaveTextContent("Забить 8 голов");
    expect(screen.getByText("Зарплата +480 · цели клуба +300")).toBeInTheDocument();
    expect(screen.getByTestId("career-timeline")).toHaveTextContent("Сезон 1 · Юность");
  });
});
