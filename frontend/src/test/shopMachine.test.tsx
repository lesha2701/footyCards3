import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import PackMachine from "@/components/shop/PackMachine";
import PackTile from "@/components/shop/PackTile";
import type { Pack } from "@/types";

vi.mock("@/hooks/useStarsPackPurchase", () => ({
  useStarsPackPurchase: () => ({ phase: "idle", error: null, buy: vi.fn(), busy: false }),
}));

const pack = (patch: Partial<Pack>): Pack => ({
  id: 1, slug: "basic", name: "Basic Pack", description: "", price: 100, stars_price: null, bonus_coins: null,
  badge_id: null, badge: null, image_path: null, card_count: 3, guaranteed_min_rarity: null, is_active: true,
  purchase_limit_per_user: null, available_from: null, available_until: null,
  rarity_probabilities: [
    { rarity: "common", probability: 0.75 },
    { rarity: "rare", probability: 0.2 },
    { rarity: "legendary", probability: 0.05 },
  ] as Pack["rarity_probabilities"],
  coach_drop_chance: 0, stadium_drop_chance: 0, user_purchase_count: 0, is_available_now: true, expected_value: 62,
  ...patch,
});

describe("Автомат паков", () => {
  const packs = [pack({}), pack({ id: 2, name: "Premium Pack", price: 350 })];
  const machine = (balance: number, index = 0, extra: Partial<Parameters<typeof PackMachine>[0]> = {}) =>
    render(
      <PackMachine
        packs={packs} index={index} onIndexChange={vi.fn()} balance={balance}
        onOpen={vi.fn()} onOpenMany={vi.fn()} onNeedCoins={vi.fn()} topUpStars={() => 25} onStarsPurchased={vi.fn()} {...extra}
      />,
    );

  it("shows the pack with its rarest chance and opens ×10 through the sheet", () => {
    const onOpenMany = vi.fn();
    machine(5000, 0, { onOpenMany });
    expect(screen.getByText("Basic Pack")).toBeInTheDocument();
    expect(screen.getByText(/Легендарная 5%/)).toBeInTheDocument();
    fireEvent.click(screen.getByText("×10"));
    expect(onOpenMany).toHaveBeenCalledWith(packs[0], 10);
  });

  it("offers to top up instead of a dead «не хватает» button", () => {
    const onNeedCoins = vi.fn();
    machine(300, 1, { onNeedCoins });
    expect(screen.getByText(/от 25 ⭐/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Докупить 50/));
    expect(onNeedCoins).toHaveBeenCalled();
  });

  it("offers as many as the balance allows and locks ×N below two", () => {
    const { unmount } = machine(1000, 1);
    expect(screen.getByText("×2")).toBeInTheDocument();
    unmount();
    machine(400, 1);
    expect(screen.getByText("×10").closest("button")).toBeDisabled();
  });

  it("rolls to the next pack by itself", () => {
    vi.useFakeTimers();
    const onIndexChange = vi.fn();
    machine(5000, 0, { onIndexChange });
    vi.advanceTimersByTime(4100);
    expect(onIndexChange).toHaveBeenCalledWith(1);
    vi.useRealTimers();
  });

  it("flips to the next pack with the arrow", () => {
    const onIndexChange = vi.fn();
    machine(5000, 1, { onIndexChange });
    fireEvent.click(screen.getByLabelText("Следующий пак"));
    expect(onIndexChange).toHaveBeenCalledWith(0);
  });
});

describe("Плитка пака", () => {
  const tile = (open: boolean, onOpen = vi.fn(), balance = 500) => (
    <PackTile pack={pack({})} open={open} onToggle={vi.fn()} balance={balance} onOpen={onOpen} onNeedCoins={vi.fn()} topUpStars={() => 25} onStarsPurchased={vi.fn()} />
  );

  it("shows the price on the cover and ×1 / ×5 / ×10 with chances in the sheet", () => {
    const onOpen = vi.fn();
    const { rerender } = render(tile(false, onOpen));
    expect(screen.getByText("100")).toBeInTheDocument();
    expect(screen.queryByText("×5")).not.toBeInTheDocument();
    rerender(tile(true, onOpen));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Обычная")).toBeInTheDocument();
    expect(screen.getByText("75%")).toBeInTheDocument();
    fireEvent.click(screen.getByText("×5"));
    expect(onOpen).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }), 5);
    expect(screen.getByText("×10").closest("button")).toBeDisabled();
  });
});
