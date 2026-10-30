import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MyPlayer, MyPlayerSponsorView } from "@/api/myPlayer";
import MyPlayerHallOfFame from "@/components/myPlayer/MyPlayerHallOfFame";
import MyPlayerSponsor from "@/components/myPlayer/MyPlayerSponsor";
import TrophyShowcase from "@/components/myPlayer/TrophyShowcase";

const fetchMyPlayerSponsor = vi.fn();
const signMyPlayerSponsor = vi.fn();
const claimMyPlayerSponsor = vi.fn();
const fetchMyPlayerHallOfFame = vi.fn();
vi.mock("@/api/myPlayer", async (orig) => ({
  ...(await orig<typeof import("@/api/myPlayer")>()),
  fetchMyPlayerSponsor: () => fetchMyPlayerSponsor(),
  signMyPlayerSponsor: (...args: unknown[]) => signMyPlayerSponsor(...args),
  claimMyPlayerSponsor: (...args: unknown[]) => claimMyPlayerSponsor(...args),
  fetchMyPlayerHallOfFame: (...args: unknown[]) => fetchMyPlayerHallOfFame(...args),
}));

const player: MyPlayer = {
  name: "Тест Игрок", number: 9, position: "ST", category: "FWD",
  appearance: { skin: 1, hair: 2, hair_color: 0, beard: 1, eye_color: 2, kit: 3, kit_pattern: 1 },
  attributes: { atk: 68, def: 36 },
  rating: 52, attack_rating: 68, defense_rating: 36, tier: "bronze", tier_label: "Бронза", key_attr: "atk",
};

const goals = [
  { code: "training", label: "Тренировки", target: 5, coins: 150, premium_only: false },
  { code: "duel_win", label: "Победы в дуэлях", target: 3, coins: 150, premium_only: false },
  { code: "career_match", label: "Матчи в карьере", target: 8, coins: 150, premium_only: false },
  { code: "career_win", label: "Победы в карьере", target: 4, coins: 200, premium_only: true },
];
const brand = { code: "volt", name: "Volt Energy", emoji: "⚡", color: "#facc15", goals };
const base: MyPlayerSponsorView = {
  week: "2026-W44", ends_at: new Date(Date.now() + 3 * 86_400_000).toISOString(), stars: 49, premium_pct: 200, bonus_coins: 300,
  offers: [brand], contract: null,
};

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

describe("«Мой игрок» extras", () => {
  beforeEach(() => vi.clearAllMocks());

  it("signs a sponsor of the week and claims a done goal", async () => {
    fetchMyPlayerSponsor.mockResolvedValue(base);
    const contract = {
      ...base, offers: [],
      contract: {
        ...brand, premium: false,
        goals: goals.map((g, i) => ({ ...g, value: i === 0 ? 5 : 1, done: i === 0, claimed: false, locked: g.premium_only })),
        bonus: { coins: 300, claimed: false, ready: false },
      },
    };
    signMyPlayerSponsor.mockResolvedValue(contract);
    claimMyPlayerSponsor.mockResolvedValue({ ...contract, balance: 1150 });
    wrap(<MyPlayerSponsor />);
    expect(await screen.findByText("Volt Energy")).toBeInTheDocument();
    expect(screen.getByText(/Победы в карьере: 4/)).toHaveTextContent("⭐");
    fireEvent.click(screen.getByRole("button", { name: "Подписать контракт" }));
    await waitFor(() => expect(signMyPlayerSponsor.mock.calls[0]?.[0]).toBe("volt"));
    expect(await screen.findByText("премиум")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Улучшить за 49/ })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: /150/ })[0]);
    await waitFor(() => expect(claimMyPlayerSponsor.mock.calls[0]?.[0]).toBe("training"));
  });

  it("shows the cabinet in its showcase with career totals and the patron badge", () => {
    render(
      <TrophyShowcase
        trophies={[{ id: 1, code: "player_career_champion", name: "Чемпион лиги", icon: "🏆", image_path: null, message: null, granted_at: "2026-10-01T10:00:00Z" }]}
        cabinet={{ showcase: "sc_gold", totals: { seasons: 3, goals: 21, titles: 1, matches: 40 }, cups: 0,
          patron: { level: 2, name: "Меценат II", sent: 6, next_at: 20 } }}
      />,
    );
    expect(screen.getByTestId("career-totals")).toHaveTextContent("Голы 21");
    expect(screen.getByText("🎁 Меценат II")).toBeInTheDocument();
    expect(screen.getByText("Золотая витрина")).toBeInTheDocument();
  });

  it("lists the hall of fame by the chosen metric", async () => {
    fetchMyPlayerHallOfFame.mockResolvedValue({
      metric: "goals", entries: [{ place: 1, user_id: 5, user_name: "Коля", value: 42, player }], me: { place: 7, value: 12 },
    });
    wrap(<MyPlayerHallOfFame />);
    expect(await screen.findByText("42")).toBeInTheDocument();
    expect(screen.getByText(/место/)).toHaveTextContent("7");
    fireEvent.click(screen.getByRole("button", { name: /Золотой мяч/ }));
    await waitFor(() => expect(fetchMyPlayerHallOfFame).toHaveBeenCalledWith("golden_ball"));
  });
});
