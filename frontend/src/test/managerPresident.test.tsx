import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ManagerOffice, ManagerRating } from "@/api/manager";
import MatchdayPanel from "@/components/manager/MatchdayPanel";
import PresidentRating from "@/components/manager/PresidentRating";

const setManagerTickets = vi.fn();
const fetchManagerRating = vi.fn<() => Promise<ManagerRating>>();
vi.mock("@/api/manager", async (orig) => ({
  ...(await orig<typeof import("@/api/manager")>()),
  setManagerTickets: (...args: unknown[]) => setManagerTickets(...args),
  fetchManagerRating: () => fetchManagerRating(),
}));

const LOOK = {
  shape: "shield", symbol: "⚽", color: "#1f8a4c", color2: "#f5f5f5", kit: "plain", kit_color: "#1f8a4c", kit_color2: "#f5f5f5",
  frame: "classic", theme: "night",
};

const office = {
  window_open: true, free_budget: 5_000_000,
  tickets: { pct: 100, min: 50, max: 200, elasticity: 0.6, attendance_min: 20, attendance_max: 130, support_per_pct: 0.1, fans_per_pct: 20,
    base_per_match: 200_000, capacity: 30_000 },
  injuries: [{ name: "Н. Морозов", rounds_left: 2, cost: 75_000 }],
  offers: { insurance: { taken: false, premium: 90_000, cover_pct: 100, medical: 3, chance_pct: 7.2, treatment_pct: 5, rounds: [1, 3] } },
} as unknown as ManagerOffice;

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

describe("MatchdayPanel", () => {
  beforeEach(() => setManagerTickets.mockReset());

  it("shows attendance, money and the crowd for a price and saves it", async () => {
    setManagerTickets.mockResolvedValue(office);
    const onInsure = vi.fn();
    wrap(<MatchdayPanel office={office} onDone={() => {}} onError={() => {}} busy={false} onInsure={onInsure} />);
    fireEvent.change(screen.getByLabelText("Цена билета"), { target: { value: "150" } });
    // 150 % → 70 % of the people: €200k × 1.05, −3 % at home, −600 fans.
    expect(screen.getByText("70%")).toBeInTheDocument();
    expect(screen.getByText("€210 тыс")).toBeInTheDocument();
    expect(screen.getByText("-3%")).toBeInTheDocument();
    expect(screen.getByText("-600")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Установить 150%" }));
    await waitFor(() => expect(setManagerTickets).toHaveBeenCalledWith(150));
    expect(screen.getByText(/Н. Морозов/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Застраховать" }));
    expect(onInsure).toHaveBeenCalled();
  });
});

describe("PresidentRating", () => {
  it("lists the best presidents and my place, by profit and by capital", async () => {
    const row = (place: number, name: string, score: number, mine = false) => ({ place, club_id: place, name, division: 3, look: LOOK, score, mine });
    fetchManagerRating.mockResolvedValue({
      season_key: "2026-W44",
      profit: { rows: [row(1, "Ястребы", 4_000_000), row(2, "Совы", 1_500_000, true)], my_place: 2, my_score: 1_500_000, total: 9 },
      capital: { rows: [row(1, "Совы", 30_000_000, true)], my_place: 1, my_score: 30_000_000, total: 9 },
    });
    wrap(<PresidentRating />);
    expect(await screen.findByText("#2")).toBeInTheDocument();
    expect(screen.getByText("Ястребы")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "💰 Капитал" }));
    expect(screen.getByText("#1")).toBeInTheDocument();
  });
});
