import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ManagerCupView, ManagerNews } from "@/api/manager";
import { CupPanel, NewsPanel } from "@/components/manager/CupNewsPanel";

const fetchManagerCup = vi.fn<() => Promise<ManagerCupView>>();
const fetchManagerNews = vi.fn<() => Promise<ManagerNews>>();
vi.mock("@/api/manager", () => ({
  fetchManagerCup: () => fetchManagerCup(),
  fetchManagerNews: () => fetchManagerNews(),
}));
vi.mock("@/components/common/ShareButton", () => ({ default: ({ label }: { label: string }) => <button>{label}</button> }));

const CUP: ManagerCupView = {
  enabled: true,
  prizes: [{ stage: "победитель", amount: 400_000 }],
  history: [{ season_key: "2026-W40", winner: "Старые" }],
  cup: {
    season_key: "2026-W44", status: "active", clubs: 8, total_rounds: 3, played: 1, next_at: "2026-11-03T18:00:00Z",
    rounds: [{ index: 0, name: "1/4 финала", at: "2026-11-02T18:00:00Z", matches: [
      { a: "Мои", b: "Чужие", hs: 2, as: 2, pens: [4, 3], winner: "Мои", mine: true, bye: false },
    ] }],
    mine: { alive: true, stage: null },
    winner: null,
  },
};

const NEWS: ManagerNews = {
  league: "Высшая лига", season_key: "2026-W44", date: "1 ноября", rounds: [3], total_rounds: 14,
  headline: "«Мои» разгромил «Чужие» 4:0!", my_place: 2,
  biggest: { home: "А", away: "Б", hs: 5, as: 1 },
  matches: [{ round: 3, home: "Мои", away: "Чужие", hs: 4, as: 0, mine: true }],
  top: [], leader: { name: "А", points: 9 }, scorer: { name: "Иванов", team: "А", goals: 5 }, transfer: null, cup: null,
};

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("CupPanel / NewsPanel", () => {
  it("shows my cup match with the penalties, prizes and past winners", async () => {
    fetchManagerCup.mockResolvedValue(CUP);
    wrap(<CupPanel />);
    expect(await screen.findByText("Кубок менеджеров")).toBeInTheDocument();
    expect(screen.getByText(/пен\. 4:3/)).toBeInTheDocument();
    expect(screen.getByText(/Призовые: победитель/)).toBeInTheDocument();
    expect(screen.getByText(/«Старые»/)).toBeInTheDocument();
  });

  it("hides the cup without a draw", async () => {
    fetchManagerCup.mockResolvedValue({ ...CUP, cup: null });
    const { container } = wrap(<CupPanel />);
    await waitFor(() => expect(fetchManagerCup).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("renders the front page with the share button and the day's matches", async () => {
    fetchManagerNews.mockResolvedValue(NEWS);
    wrap(<NewsPanel />);
    expect(await screen.findByText("«Мои» разгромил «Чужие» 4:0!")).toBeInTheDocument();
    expect(screen.getByText("Поделиться газетой")).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Все матчи дня/));
    expect(screen.getByText("Т3: Мои 4:0 Чужие")).toBeInTheDocument();
  });
});
