import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CareerSeason, CareerView } from "@/api/career";
import CareerPage from "@/pages/CareerPage";

const fetchCareer = vi.fn<() => Promise<CareerView>>();
vi.mock("@/api/career", async (orig) => ({ ...(await orig<typeof import("@/api/career")>()), fetchCareer: () => fetchCareer() }));

const baseView: CareerView = {
  enabled: true,
  difficulties: [
    { code: "amateur", label: "Любитель", reward_pct: 100 },
    { code: "pro", label: "Профи", reward_pct: 150 },
    { code: "legend", label: "Легенда", reward_pct: 200 },
  ],
  place_rewards: [1500, 1000, 700, 500, 350, 250, 150, 100],
  slots: ["12:00", "19:00"],
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
    { index: 0, at: null, matches: [{ home: 0, away: 1, hs: 2, as: 1, has_events: true }] },
    { index: 1, at: null, matches: [{ home: 2, away: 0, hs: null, as: null, has_events: false }] },
  ],
  squad: [], lineup: {}, slots: [], formation: "4-3-3", mentality: "BALANCED", playstyle: "CENTRAL_PLAY",
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

  it("offers difficulty, a friend season and the champion reward when there is no season", async () => {
    fetchCareer.mockResolvedValue(baseView);
    renderPage();
    expect(await screen.findByText("Начать сезон")).toBeInTheDocument();
    expect(screen.getByText("Сезон с другом")).toBeInTheDocument();
    // Профи = 150% of the 1st-place reward.
    expect(screen.getByText(/Чемпиону: 2250/)).toBeInTheDocument();
  });

  it("shows the next opponent and the tabs for an active season", async () => {
    fetchCareer.mockResolvedValue({ ...baseView, season: activeSeason });
    renderPage();
    expect(await screen.findByText(/В гостях: Бот 2/)).toBeInTheDocument();
    expect(screen.getByText(/тур 2 из 14/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Таблица" })).toBeInTheDocument();
    expect(screen.getByText("1 место")).toBeInTheDocument();
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
