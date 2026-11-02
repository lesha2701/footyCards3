import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ManagerAnalytics, ManagerLook, ManagerPass } from "@/api/manager";
import AnalyticsPanel from "@/components/manager/AnalyticsPanel";
import Stadium from "@/components/manager/Stadium";

const fetchManagerAnalytics = vi.fn<() => Promise<ManagerAnalytics>>();
vi.mock("@/api/manager", () => ({ fetchManagerAnalytics: () => fetchManagerAnalytics() }));
vi.mock("@/lib/myPlayerStars", () => ({ payMyPlayerWithStars: vi.fn() }));

const LOOK: ManagerLook = {
  shape: "shield", symbol: "🦁", color: "#c62828", color2: "#f5f5f5", kit: "plain", kit_color: "#c62828", kit_color2: "#f5f5f5",
  frame: "classic", theme: "night", stands: "tifo",
};

const PASS: ManagerPass = { code: "analytics", name: "Аналитика Pro", about: "", stars: 99, days: 30, active: false, until: null };

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("Stadium", () => {
  it("draws the bought skin with the club symbol on the tifo", () => {
    render(<Stadium look={LOOK} />);
    expect(screen.getByTestId("stadium")).toHaveAttribute("data-skin", "tifo");
    expect(screen.getByText("🦁")).toBeInTheDocument();
  });
});

describe("AnalyticsPanel", () => {
  it("is a teaser with the Stars price without the pass", () => {
    wrap(<AnalyticsPanel pass={PASS} onError={() => {}} />);
    expect(screen.getByTestId("analytics-teaser")).toBeInTheDocument();
    expect(screen.getByText("99 ⭐")).toBeInTheDocument();
    expect(fetchManagerAnalytics).not.toHaveBeenCalled();
  });

  it("breaks the next opponent down line by line with the pass", async () => {
    fetchManagerAnalytics.mockResolvedValue({
      opponent: {
        name: "Ястребы", home: true, at: null, style: "counter", formation: "4-4-2", edge: "lose", rating: 60, my_rating: 58,
        lines: [
          { line: "GK", mine: 60, theirs: 55 }, { line: "DEF", mine: 57, theirs: 61 },
          { line: "MID", mine: 58, theirs: 58 }, { line: "FWD", mine: 59, theirs: 62 },
        ],
        record: { form: ["W", "W", "L"], gf: 7, ga: 3, played: 3 }, my_record: { form: ["D"], gf: 1, ga: 1, played: 1 }, injuries: 2,
      },
    });
    wrap(<AnalyticsPanel pass={{ ...PASS, active: true }} onError={() => {}} />);
    expect(await screen.findByText("Разбор: «Ястребы»")).toBeInTheDocument();
    expect(screen.getByText(/Его стиль бьёт твой/)).toBeInTheDocument();
    expect(screen.getByText("Защита")).toBeInTheDocument();
    expect(screen.getByText(/Соперник: 7:3 · 🩹 2/)).toBeInTheDocument();
  });
});
