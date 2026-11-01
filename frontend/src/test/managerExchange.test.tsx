import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ManagerExchange } from "@/api/manager";
import ExchangePanel from "@/components/manager/ExchangePanel";

const fetchManagerExchange = vi.fn<() => Promise<ManagerExchange>>();
const tradeManagerShares = vi.fn();
const floatManagerShares = vi.fn();
const listManagerShares = vi.fn();
vi.mock("@/api/manager", async (orig) => ({
  ...(await orig<typeof import("@/api/manager")>()),
  fetchManagerExchange: () => fetchManagerExchange(),
  tradeManagerShares: (...args: unknown[]) => tradeManagerShares(...args),
  floatManagerShares: (...args: unknown[]) => floatManagerShares(...args),
  listManagerShares: (...args: unknown[]) => listManagerShares(...args),
}));

const LOOK = {
  shape: "shield", symbol: "⚽", color: "#1f8a4c", color2: "#f5f5f5", kit: "plain", kit_color: "#1f8a4c", kit_color2: "#f5f5f5",
  frame: "classic", theme: "night",
};

const x: ManagerExchange = {
  enabled: true, club_id: 1, window_open: true, budget: 9_000_000, free_budget: 5_000_000,
  rules: {
    shares_total: 1000, ipo_max_pct: 49, holder_max_pct: 25, exchange_fee_pct: 2, buyback_premium_pct: 10, ipo_season_cap_pct: 50,
    exchange_spread_pct: 5, ask_band_pct: 15, dividend_pct: 20, bond_rate_min_pct: 4, bond_rate_max_pct: 25, bond_unit_eur: 100_000, bond_seasons_max: 3, bond_holder_max_pct: 25,
  },
  my_stock: {
    listed: false, shares_total: 1000, floated: 0, unsold: 0, pool: 0, held_by_others: 0, price: 20_000, history: [], ipo_left: 490,
    raised_this_season: 0, raise_cap: 30_000_000, dividends_paid: 0, buyback_price: 22_000, holders: [],
  },
  market: [{
    club_id: 7, name: "Ястребы", division: 2, division_name: "Дивизион 2", look: LOOK, price: 25_000, change_pct: 4.2, cap: 25_000_000,
    available: 300, floated: 400, history: [24_000, 25_000], mine: false, held: 40, holder_cap: 250, dividends_paid: 0,
    offers: [{ price: 24_000, shares: 100, kind: "ask" }, { price: 25_000, shares: 200, kind: "ipo" }],
    bid: 23_750, band: [21_250, 28_750], listed: 0, ask: 0,
  }],
  portfolio: [],
  bonds: { limit: 1_000_000, owed: 0, market: [], mine: [], held: [] },
  tape: [{ id: 1, club: "Ястребы", side: "ipo", shares: 400, price: 24_000, at: null }],
};

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><ExchangePanel onError={() => {}} /></QueryClientProvider>);
}

describe("ExchangePanel", () => {
  beforeEach(() => {
    [fetchManagerExchange, tradeManagerShares, floatManagerShares, listManagerShares].forEach((f) => f.mockReset());
    fetchManagerExchange.mockResolvedValue(x);
  });

  it("lists clubs with the price and buys shares through a confirmation", async () => {
    tradeManagerShares.mockResolvedValue(x);
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /Ястребы.*Дивизион 2/ }));
    expect(screen.getByText(/IPO 400 акц/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Купить · / }));
    fireEvent.click(await screen.findByRole("button", { name: "Купить" }));
    await waitFor(() => expect(tradeManagerShares).toHaveBeenCalledWith(7, "buy", 10));
  });

  it("buys the cheapest offers first and lists own shares at an ask", async () => {
    listManagerShares.mockResolvedValue(x);
    renderPanel();
    fireEvent.click(await screen.findByRole("button", { name: /Ястребы.*Дивизион 2/ }));
    // 10 shares: all from the holder's ask at €24k, + 2 % fee.
    expect(screen.getByRole("button", { name: /^Купить · / })).toHaveTextContent("€245 тыс");
    fireEvent.click(screen.getByRole("button", { name: "Выставить" }));
    await waitFor(() => expect(listManagerShares).toHaveBeenCalledWith(7, 10, 25_000));
  });

  it("floats the own club on the IPO tab", async () => {
    floatManagerShares.mockResolvedValue(x);
    renderPanel();
    fireEvent.click(await screen.findByText("🏛 Мой клуб"));
    fireEvent.click(screen.getByRole("button", { name: "🔔 Провести IPO" }));
    fireEvent.click(await screen.findByRole("button", { name: "Выпустить" }));
    await waitFor(() => expect(floatManagerShares).toHaveBeenCalledWith(100));
  });
});
