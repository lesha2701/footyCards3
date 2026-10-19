import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type { CardEquipment, EquipmentItem } from "@/api/equipment";
import CardEquipmentPanel from "@/components/equipment/CardEquipmentPanel";

const item = (over: Partial<EquipmentItem> = {}): EquipmentItem => ({
  id: 1, name: "Бутсы «Ретро-70»", description: null, image_path: null, icon: "👞", slot: "boots", slot_label: "Бутсы",
  rarity: "rare", collection_id: 1, collection_name: "Ретро-70", effect: "shot_pp", effect_value: 3,
  effect_label: "+3% к точности удара", cond_club: null, cond_country: null, coins_price: 300, stars_price: 0, ...over,
});

const state: CardEquipment = {
  enabled: true, card_id: 7, rating_bonus: 1, chemistry: 0, boosts: { shot_pp: 3 },
  slots: [
    { code: "boots", label: "Бутсы", available: true, worn: { copy_id: 11, item: item(), applies: true }, options: [] },
    { code: "kit", label: "Форма", available: true, worn: null, options: [
      { copy_id: 12, item: item({ id: 2, name: "Форма «Ретро-70»", slot: "kit", effect: "rating", effect_label: "+1 к рейтингу" }), applies: true },
    ] },
    { code: "socks", label: "Гетры и щитки", available: true, worn: null, options: [] },
    { code: "gloves", label: "Перчатки", available: false, worn: null, options: [] },
    { code: "accessory", label: "Аксессуар", available: true, worn: null, options: [] },
    { code: "artifact", label: "Артефакт", available: true, worn: null, options: [] },
  ],
};

vi.mock("@/api/equipment", () => ({
  fetchCardEquipment: vi.fn(async () => state),
  equipItem: vi.fn(async () => state),
  unequipItem: vi.fn(async () => ({ enabled: true, items: [] })),
}));

const renderPanel = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <CardEquipmentPanel cardId={7} />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("CardEquipmentPanel", () => {
  it("shows what the worn things give and every slot, artifact included", async () => {
    renderPanel();
    expect(await screen.findByText("+1 к рейтингу · +3% к удару")).toBeInTheDocument();
    for (const label of ["Бутсы", "Форма", "Гетры и щитки", "Перчатки", "Аксессуар", "Артефакт"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("offers free inventory things for a slot", async () => {
    renderPanel();
    fireEvent.click(await screen.findByText("Форма"));
    expect(screen.getByText("Форма «Ретро-70»")).toBeInTheDocument();
    expect(screen.getByText("Надеть")).toBeInTheDocument();
  });

  it("explains the goalkeeper-only gloves slot", async () => {
    renderPanel();
    fireEvent.click(await screen.findByText("Перчатки"));
    expect(screen.getByText("Этот слот только для вратаря")).toBeInTheDocument();
  });
});
