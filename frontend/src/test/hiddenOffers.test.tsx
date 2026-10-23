import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { StarterOfferBanner } from "@/components/shop/StarterOffer";

vi.mock("@/api/monetization", () => ({
  fetchStarterOffer: vi.fn(async () => ({
    available: true, stars_price: 50, contents: { coins: 10000 }, expires_at: null, seen: true, purchased: false,
  })),
  createStarterOfferInvoice: vi.fn(),
  markStarterOfferSeen: vi.fn(),
}));

const renderBanner = (hideable: boolean) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <StarterOfferBanner hideable={hideable} />
    </QueryClientProvider>,
  );

describe("Стартовый набор: скрыть", () => {
  beforeEach(() => localStorage.clear());

  it("home: the cross hides the offer and it stays hidden", async () => {
    const first = renderBanner(true);
    fireEvent.click(await screen.findByRole("button", { name: "Скрыть предложение" }));
    expect(screen.queryByText("Стартовый набор")).not.toBeInTheDocument();
    first.unmount();
    renderBanner(true);
    await new Promise((r) => setTimeout(r, 20));
    expect(screen.queryByText("Стартовый набор")).not.toBeInTheDocument();
  });

  it("shop: no cross, and a hidden offer is still there", async () => {
    localStorage.setItem("fc.hidden_offer.starter_offer", "true");
    renderBanner(false);
    expect(await screen.findByText("Стартовый набор")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Скрыть предложение" })).not.toBeInTheDocument();
  });
});
