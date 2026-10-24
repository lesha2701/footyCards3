import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import ModesGrid from "@/components/home/ModesGrid";
import AcademyPage from "@/pages/AcademyPage";
import type { AcademyState } from "@/types";

const wing = (code: string, name: string, level: number, building = false) => ({
  code, name, emoji: "🏠", about: "о корпусе", level, max_level: 5, effect: level ? `эффект ${level}` : null,
  next_effect: `эффект ${level + 1}`, next_cost: 2000, next_hours: 4, building,
});

const state: AcademyState = {
  enabled: true, level: 3, max_level: 25,
  wings: [wing("scout", "Скаутский отдел", 1), wing("training", "Тренировочная база", 2, true), wing("dorm", "Интернат", 0),
    wing("staff", "Тренерский штаб", 0), wing("hall", "Зал славы", 0)] as AcademyState["wings"],
  construction: { building_code: "training", to_level: 3, ends_at: new Date(Date.now() + 3_600_000).toISOString(), remaining_seconds: 3600, speedup_stars: 2 },
  scout_report: { chance_pct: 15, consolation_coins: 200, cooldown_days: 7, available: true, next_at: null },
  effects: { scout: 1, training: 8, dorm: 0, staff: 0, hall: 0 }, showcase_slots: 3, academy_cards: 0, cards: [],
};

vi.mock("@/api/academy", () => ({
  fetchAcademy: vi.fn(async () => state),
  upgradeAcademyWing: vi.fn(), claimScoutReport: vi.fn(), createAcademySpeedupInvoice: vi.fn(), fetchAcademyInvoiceStatus: vi.fn(),
}));
// The home strip also asks the other modes for their status.
vi.mock("@/api/clubBase", () => ({
  fetchClubBase: vi.fn(async () => ({ enabled: true, total_level: 3, construction: null, income: { daily: 0, pending: 0, cap: 0, max_days: 3 } })),
}));
vi.mock("@/api/clubs", () => ({
  fetchMyClub: vi.fn(async () => { throw new Error("no club"); }),
  fetchTournamentCurrent: vi.fn(), fetchNextOpponent: vi.fn(), claimDailyReward: vi.fn(),
}));
vi.mock("@/api/career", () => ({ fetchCareer: vi.fn(async () => ({ enabled: true, season: null, invite: null })) }));
vi.mock("@/api/myPlayer", () => ({ fetchMyPlayer: vi.fn(async () => ({ enabled: true, player: null })) }));
vi.mock("@/api/matches", () => ({ fetchArenaStats: vi.fn(async () => ({ arena_rating: 1000, division: null })) }));
vi.mock("@/api/personalTournament", () => ({ fetchPlayerTournamentCurrent: vi.fn(async () => ({ status: "not_queued" })) }));

function wrap(node: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

describe("Академия", () => {
  it("shows the campus, the construction with a Stars speed-up and blocks a second build", async () => {
    wrap(<AcademyPage />);
    expect(await screen.findByText(/Тренировочная база → уровень 3/)).toBeInTheDocument();
    expect(screen.getByText("Ускорить ⭐ 2")).toBeEnabled();
    expect(screen.getByRole("img", { name: /уровень 3/ })).toBeInTheDocument();
    for (const button of screen.getAllByText(/Улучшить|Построить|Строится/)) expect(button.closest("button")).toBeDisabled();
    expect(screen.getByText("Получить")).toBeEnabled();
  });

  it("the base tile on the home grid invites to claim the Academy's scouting report", async () => {
    wrap(<ModesGrid />);
    expect(await screen.findByText(/Скаутский отчёт готов/)).toBeInTheDocument();
    expect(screen.getByText("База")).toBeInTheDocument();
  });
});
