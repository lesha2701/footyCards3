import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { ManagerSummary } from "@/api/manager";
import ManagerFeature from "@/components/home/ManagerFeature";

const fetchManager = vi.fn<() => Promise<ManagerSummary>>();
vi.mock("@/api/manager", () => ({ fetchManagerSummary: () => fetchManager() }));

const LOOK = { shape: "shield", symbol: "⚽", color: "#1f8a4c", color2: "#f5f5f5" };

function view(over: Record<string, unknown>): ManagerSummary {
  return {
    enabled: true, league: null, today: [],
    season: { phase: "preseason", transfers_open: true, preseason_ends_at: "2026-11-04T12:00:00Z", first_round_at: "", rounds: 15 },
    club: { name: "Ночные Совы", look: LOOK, division_name: "Дивизион 8", budget: 31_300_000, trade_locked: false, next_match: null, checklist: null },
    ...over,
  } as unknown as ManagerSummary;
}

function wrap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter><ManagerFeature /></MemoryRouter></QueryClientProvider>);
}

describe("ManagerFeature", () => {
  it("lights up while the transfer window is open", async () => {
    fetchManager.mockResolvedValue(view({}));
    wrap();
    expect(await screen.findByText("Ночные Совы")).toBeInTheDocument();
    expect(screen.getByText(/Трансферное окно до/)).toBeInTheDocument();
    expect(screen.getByLabelText("Есть действие")).toBeInTheDocument();
    expect(screen.getByText("Бюджет €31,3 млн")).toBeInTheDocument();
  });

  it("shows the round, the place and the next match during the season", async () => {
    fetchManager.mockResolvedValue(view({
      season: { phase: "season", transfers_open: false, preseason_ends_at: "" },
      league: { status: "active", rounds_played: 6, total_rounds: 15, place: 3, size: 12 },
      club: {
        name: "Ночные Совы", look: LOOK, division_name: "Дивизион 8", budget: 1_000, trade_locked: true,
        next_match: { opponent: "Ястребы", home: true, at: null, edge: "even" }, checklist: null,
      },
    }));
    wrap();
    expect(await screen.findByText("Ночные Совы · тур 7/15")).toBeInTheDocument();
    expect(screen.getByText("Дома: Ястребы")).toBeInTheDocument();
    expect(screen.getByText("3 место")).toBeInTheDocument();
    expect(screen.queryByLabelText("Есть действие")).toBeNull();
  });

  it("puts an urgent thing first", async () => {
    fetchManager.mockResolvedValue(view({ today: [{ code: "incoming", icon: "📨", text: "Предложения по твоим игрокам: 2", tab: "club", urgent: true }] }));
    wrap();
    expect(await screen.findByText("📨 Предложения по твоим игрокам: 2")).toBeInTheDocument();
  });

  it("invites to found a club", async () => {
    fetchManager.mockResolvedValue(view({ club: null }));
    wrap();
    expect(await screen.findByText("Стань президентом")).toBeInTheDocument();
  });
});
