import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import ShowcaseCard from "@/components/home/ShowcaseCard";

const pack = { id: 1, name: "Premium Pack", price: 350, stars_price: null, image_path: null };

vi.mock("@/api/packs", () => ({
  fetchDailyOffer: vi.fn(async () => ({ pack, discount_pct: 30, price: 245, claimed_today: false, ends_at: new Date().toISOString() })),
  fetchPacks: vi.fn(async () => [pack]),
}));
vi.mock("@/api/monetization", () => ({
  fetchArtifacts: vi.fn(async () => ({
    enabled: true,
    shop: [
      { id: 7, name: "Бутса Пеле", icon: "👟", image_path: null, owned_count: 0, left: 5, coins_price: 900, stars_price: 0 },
      { id: 8, name: "Уже куплен", icon: "🏆", image_path: null, owned_count: 1, left: 5, coins_price: 900, stars_price: 0 },
    ],
  })),
  fetchCosmetics: vi.fn(async () => ({
    items: [{ id: 3, kind: "profile_frame", name: "Золотая рамка", style_key: "gold", coins_price: 0, stars_price: 25, owned: false, is_active: true, is_exclusive: false }],
  })),
}));

describe("Витрина дня", () => {
  it("shows the discounted pack of the day and two not-owned shop items", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter><ShowcaseCard /></MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("−30%")).toBeInTheDocument();
    expect(screen.getByText("245")).toBeInTheDocument();
    expect(await screen.findByText("Бутса Пеле")).toBeInTheDocument();
    expect(await screen.findByText("Золотая рамка")).toBeInTheDocument();
    expect(screen.getByText("25 ⭐")).toBeInTheDocument();
    expect(screen.queryByText("Уже куплен")).not.toBeInTheDocument();
  });
});
