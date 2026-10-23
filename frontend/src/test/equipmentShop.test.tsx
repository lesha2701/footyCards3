import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import EquipmentShop from "@/components/shop/EquipmentShop";

const boots = {
  id: 1, name: "Бутсы «Ретро-70»", description: "Кожа и шипы", image_path: null, icon: "👟", slot: "boots",
  slot_label: "Бутсы", rarity: "epic", collection_id: 10, collection_name: "Ретро-70", effect: "shot_pp",
  effect_value: 3, effect_label: "+3% к удару", cond_club: null, cond_country: "Бразилия", coins_price: 1500,
  stars_price: 15, owned: 0,
};

vi.mock("@/api/equipment", () => ({
  fetchEquipmentShop: vi.fn(async () => ({
    enabled: true,
    slots: [],
    caps: { rating: 3, pp: 8, chemistry: 1 },
    collections: [{ id: 10, name: "Ретро-70", description: null, image_path: null, set_size: 4, set_bonus_rating: 1, items: [boots] }],
    singles: [],
  })),
  buyEquipment: vi.fn(),
  createEquipmentStarsInvoice: vi.fn(),
}));

describe("Экипировка в магазине", () => {
  it("shows collections as tiles with a price and the effect in the sheet", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <EquipmentShop />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("«Ретро-70»")).toBeInTheDocument();
    expect(screen.getByText("Комплект 4: +1")).toBeInTheDocument();
    expect(screen.getByText("1 500")).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Бутсы «Ретро-70»: подробнее"));
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("+3% к удару")).toBeInTheDocument();
    expect(screen.getByText(/только для игроков страны Бразилия/)).toBeInTheDocument();
    expect(screen.getByText(/Полный комплект «Ретро-70» \(4 шт\.\) на одной карточке/)).toBeInTheDocument();
  });
});
