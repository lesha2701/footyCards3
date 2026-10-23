import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import EquipmentShop from "@/components/shop/EquipmentShop";
import { computeChemistry } from "@/lib/chemistry";
import type { ChemistryRules } from "@/types";

const base = {
  description: null, image_path: null, icon: "👟", slot: "boots", slot_label: "Бутсы", rarity: "legendary",
  collection_id: null, collection_name: null, effect: "shot_pp", effect_value: 6, effect_label: "+6% к точности удара",
  cond_club: null, cond_country: null, coins_price: 0, stars_price: 500, owned: 0,
};

vi.mock("@/api/equipment", () => ({
  fetchEquipmentShop: vi.fn(async () => ({
    enabled: true, slots: [], caps: { rating: 3, pp: 8, chemistry: 1, talisman_pct: 15 },
    collections: [{
      id: 7, name: "Сборная Бразилии", description: null, image_path: null, set_size: 3, set_bonus_rating: 0,
      set_team_country: "Бразилия", set_team_chemistry: 1,
      items: [{ ...base, id: 3, name: "Форма «Селесао»", slot: "kit", slot_label: "Форма", collection_id: 7 }],
    }],
    singles: [
      { ...base, id: 1, name: "Золотая бутса", max_supply: 100, left: 2 },
      { ...base, id: 2, name: "Перчатки «Зима»", slot: "gloves", slot_label: "Перчатки", available_until: "2027-03-01T00:00:00+00:00" },
    ],
  })),
  buyEquipment: vi.fn(),
  createEquipmentStarsInvoice: vi.fn(),
}));

describe("Экипировка: тираж, сезон, сборная", () => {
  it("marks limited, seasonal and national-team things", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <EquipmentShop />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("ост. 2")).toBeInTheDocument();
    expect(screen.getByText(/^до 1/)).toBeInTheDocument();
    expect(screen.getByText("Комплект: +1 хим.")).toBeInTheDocument();
  });
});

describe("chemistry: national-team set", () => {
  it("gives +N to every on-position player of the country", () => {
    const rules: ChemistryRules = {
      link_strong: 2, link_medium: 1, thresholds: [1, 2, 4], player_max: 3, player_floor: 0, rating_per_point: 1,
      off_position_penalty: 0,
    } as ChemistryRules;
    const players = [
      { slot: "FWD2", club: "A", country: "Бразилия", position: "ST", idealPosition: "ST", teamCountry: "Бразилия", teamChemistry: 1 },
      { slot: "GK", club: "B", country: "Бразилия", position: "GK", idealPosition: "GK" },
      { slot: "FWD1", club: "C", country: "Италия", position: "LW", idealPosition: "LW" },
    ];
    const result = computeChemistry(players, [], rules, 11);
    expect(result.players.GK.points).toBe(1);
    expect(result.players.FWD2.points).toBe(1);
    expect(result.players.FWD1.points).toBe(0);
  });
});
