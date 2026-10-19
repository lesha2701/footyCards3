import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CoinPackagesPanel } from "@/components/shop/CoinPackages";
import { packEndsIn, packTotal, packsWord } from "@/lib/packOdds";
import type { Pack } from "@/types";

vi.mock("@/api/wallet", () => ({
  fetchCoinPackages: vi.fn(async () => [
    { id: 1, stars_price: 10, coins_amount: 200, is_active: true, sort_order: 0, first_purchase_bonus_coins: 200 },
    { id: 2, stars_price: 50, coins_amount: 1100, is_active: true, sort_order: 1, first_purchase_bonus_coins: 1100 },
    { id: 3, stars_price: 100, coins_amount: 2600, is_active: true, sort_order: 2, first_purchase_bonus_coins: 2600 },
  ]),
  createCoinInvoice: vi.fn(),
  fetchCoinInvoiceStatus: vi.fn(),
}));

const pack = (patch: Partial<Pack>) => ({ price: 100, bulk10_discount_pct: 0, available_until: null, ...patch }) as Pack;

describe("магазин: расчёты", () => {
  it("applies the ×10 discount only from ten packs", () => {
    expect(packTotal(pack({ bulk10_discount_pct: 10 }), 5)).toBe(500);
    expect(packTotal(pack({ bulk10_discount_pct: 10 }), 10)).toBe(900);
    expect(packTotal(pack({ price: 333, bulk10_discount_pct: 15 }), 10)).toBe(2831);
  });

  it("shows a timer only for packs leaving within a week", () => {
    const now = Date.UTC(2026, 9, 20, 12);
    expect(packEndsIn(pack({ available_until: new Date(now + 2 * 86_400_000 + 1000).toISOString() }), now)).toBe("2 дн.");
    expect(packEndsIn(pack({ available_until: new Date(now + 5 * 3_600_000).toISOString() }), now)).toBe("5 ч");
    expect(packEndsIn(pack({ available_until: new Date(now + 9 * 86_400_000).toISOString() }), now)).toBeNull();
  });

  it("declines «пак»", () => {
    expect([1, 3, 7, 11, 21, 24].map((n) => `${n} ${packsWord(n)}`)).toEqual([
      "1 пак", "3 пака", "7 паков", "11 паков", "21 пак", "24 пака",
    ]);
  });
});

describe("пакеты монет", () => {
  it("flags the best value, the popular one and the first purchase bonus", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <CoinPackagesPanel onPurchased={vi.fn()} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Выгоднее всего")).toBeInTheDocument();
    expect(screen.getByText("Популярный")).toBeInTheDocument();
    expect(screen.getByText("+30%")).toBeInTheDocument();
    expect(screen.getByText("+200 на первую покупку")).toBeInTheDocument();
  });
});
