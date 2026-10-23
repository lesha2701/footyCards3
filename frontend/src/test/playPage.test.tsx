import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import PlayPage from "@/pages/PlayPage";

vi.mock("@/api/matches", () => ({ fetchArenaStats: vi.fn(async () => ({ arena_rating: 1000, division: null })) }));
vi.mock("@/api/games", () => ({
  fetchPenaltyStats: vi.fn(async () => ({ penalty_rating: 0 })),
  fetchGameLimits: vi.fn(async () => ({
    hourly_limit: 5, memory: 5, arena: 3, saboteur: 5, penalty: 0, free_kick: 5, hangman: 5, tactico: 5, pairs: 5, stratego: 5, magnate: 5, mordoboi: 5,
  })),
}));
vi.mock("@/api/tactico", () => ({
  fetchTacticoStats: vi.fn(async () => ({ tactics_rating: 0 })),
  fetchTacticoMatches: vi.fn(async () => [
    { id: 7, status: "in_progress", waiting_for_opponent: false, opponent_type: "friend", opponent_name: "Миша", viewer_side: "user" },
  ]),
}));
vi.mock("@/api/stratego", () => ({ fetchStrategoStats: vi.fn(async () => ({ stratego_rating: 0 })) }));
vi.mock("@/api/mordoboi", () => ({
  fetchMordoboiInfo: vi.fn(async () => ({ enabled: true })),
  fetchMordoboiStats: vi.fn(async () => ({ mordoboi_rating: 12, mordoboi_rank: null })),
  fetchMordoboiMatches: vi.fn(async () => [
    { id: 3, status: "in_progress", can_pick: true, opponent_type: "friend", opponent_name: "Петя", viewer_side: "opponent" },
  ]),
}));
vi.mock("@/api/kontra", () => ({
  fetchKontraHub: vi.fn(async () => ({ enabled: true, rating: 1040, active_battle_id: null })),
}));
vi.mock("@/api/blackjack", () => ({ fetchBlackjackStatus: vi.fn(async () => ({ enabled: false })) }));
vi.mock("@/api/personalTournament", () => ({ fetchPlayerTournamentCurrent: vi.fn(async () => ({ status: "not_queued" })) }));
vi.mock("@/api/career", () => ({ fetchCareer: vi.fn(async () => ({ enabled: true, season: null, invite: null })) }));
vi.mock("@/api/events", () => ({
  fetchWeeklyCup: vi.fn(async () => ({ enabled: true, title: "Найди пару", me: { place: 3, points: 120, games: 2 }, prizes: [5000], unclaimed_coins: 0 })),
  fetchMatchDay: vi.fn(async () => ({
    enabled: true, unclaimed: 0, rewards: { exact: 1000, diff: 400, outcome: 200 }, recent: [],
    current: { id: 1, home: "Спартак", away: "ЦСКА", open: true, prediction: null },
  })),
}));

const show = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <PlayPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

beforeEach(() => localStorage.clear());

describe("вкладка «Играть»", () => {
  it("puts the player's turn on top", async () => {
    show();
    expect(await screen.findByText("Твой ход")).toBeInTheDocument();
    expect(screen.getByText("Тактико · Миша")).toBeInTheDocument();
  });

  it("shows «Мордобой» in the tactics group when it is on, with the friend's pending punch", async () => {
    show();
    expect(await screen.findByText("Мордобой · Петя")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "🧠 Тактика" }));
    expect(screen.getByText("Мордобой")).toBeInTheDocument();
    expect(await screen.findByText("Рейтинг 12")).toBeInTheDocument();
    expect(screen.getByText("Контратака")).toBeInTheDocument();
    expect(screen.getByText("Арена 1040")).toBeInTheDocument();
  });

  it("shows the week's cup and the match of the day", async () => {
    show();
    expect(await screen.findByText("3 место · 120 очк.")).toBeInTheDocument();
    expect(screen.getAllByText("Спартак — ЦСКА").length).toBeGreaterThan(0);
  });

  it("filters by group and keeps favourites", async () => {
    show();
    fireEvent.click(screen.getByRole("tab", { name: "🏆 Сезоны" }));
    expect(screen.getByText("Карьера тренера")).toBeInTheDocument();
    expect(screen.queryByText("Пенальти")).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Добавить «Менеджер» в избранное"));
    fireEvent.click(screen.getByRole("tab", { name: "❤️ Избранное" }));
    const rows = screen.getAllByText(/Менеджер|Карьера тренера/);
    expect(rows.map((r) => r.textContent)).toEqual(["Менеджер"]);
  });

  it("sinks a used-up game to the bottom of its group", async () => {
    show();
    fireEvent.click(screen.getByRole("tab", { name: "⚡ Быстрые" }));
    const penalty = await screen.findByText("Пенальти");
    await within(penalty.closest("div")!.parentElement!).findByText("0/5");
    const titles = screen.getAllByText(/^(Card Arena|Пенальти|Memory)$/).map((e) => e.textContent);
    expect(titles.indexOf("Пенальти")).toBeGreaterThan(titles.indexOf("Memory"));
  });
});
