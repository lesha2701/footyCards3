import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import ArtifactsPage from "@/pages/ArtifactsPage";
import type { ArtifactCatalog, ArtifactInfo } from "@/types";

const info = (patch: Partial<ArtifactInfo>): ArtifactInfo => ({
  id: 1, name: "This is Anfield", description: null, image_path: null, icon: "🪧", rarity: "epic",
  target: "club", target_label: "Для клуба", effect: "opp_home_pct", effect_value: 1,
  effect_label: "−1% к силе соперника в домашних матчах", link_type: "stadium", link_kind: "стадион", link_name: "Энфилд",
  link_label: "−2% к силе соперника в домашних матчах", link_owned: true, card_player_name: null, card_label: "",
  active_label: "−2% к силе соперника в домашних матчах", coins_price: 100, stars_price: 20, status: 20, max_supply: null, left: null,
  ...patch,
});

const shirt = info({ id: 2, name: "Футболка Марадоны", target: "my_player", target_label: "Для Моего игрока",
  effect: "dribble_pp", effect_value: 3, effect_label: "+3% к обыгрышу 1 на 1", active_label: "+3% к обыгрышу 1 на 1",
  link_type: null, link_kind: "", link_name: null, link_label: "", link_owned: false,
  card_player_name: "Марадона", card_label: "+3 к рейтингу карточек «Марадона»" });

const catalog: ArtifactCatalog = {
  enabled: true, slots: 3, active_count: 1, balance: 1000,
  shop: [{ ...info({}), owned_count: 1 }, { ...shirt, owned_count: 1 }],
  shelf: [
    { copy_id: 10, serial_number: 1, equipped: true, source: "coins", artifact: info({}) },
    { copy_id: 11, serial_number: 7, equipped: false, source: "gift", artifact: shirt },
  ],
  effects: { club: [{ effect: "opp_home_pct", value: 2, label: "−2% к силе соперника в домашних матчах" }], my_player: [] },
};

const api = vi.hoisted(() => ({ setArtifactActive: vi.fn(), giftArtifact: vi.fn() }));
vi.mock("@/api/monetization", () => ({
  fetchArtifacts: async () => catalog,
  setArtifactActive: api.setArtifactActive,
  giftArtifact: api.giftArtifact,
  buyArtifactWithCoins: vi.fn(),
  createArtifactStarsInvoice: vi.fn(),
}));
vi.mock("@/api/friends", () => ({
  fetchFriends: async () => ({ friends: [{ user: { id: 42, first_name: "Друг" }, since: "" }], incoming: [], outgoing: [] }),
}));

function wrap(node: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("artifacts page", () => {
  it("shows the active slots, their effects and the shelf", async () => {
    wrap(<ArtifactsPage />);
    expect(await screen.findByText("Активные · 1/3")).toBeInTheDocument();
    expect(screen.getAllByText("Пусто")).toHaveLength(2);
    expect(screen.getByText("Клуб: −2% к силе соперника в домашних матчах")).toBeInTheDocument();
    expect(screen.getByText("Футболка Марадоны")).toBeInTheDocument();
  });

  it("activates a shelf copy and gifts one to a friend", async () => {
    api.setArtifactActive.mockResolvedValue(catalog);
    api.giftArtifact.mockResolvedValue(catalog);
    wrap(<ArtifactsPage />);
    fireEvent.click(await screen.findByText("Футболка Марадоны"));
    expect(screen.getByText("Для Моего игрока · подарок")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Сделать активным"));
    await waitFor(() => expect(api.setArtifactActive).toHaveBeenCalledWith(11, true));

    fireEvent.click(screen.getByText("Футболка Марадоны"));
    fireEvent.click(screen.getByText("Подарить другу"));
    fireEvent.click(await screen.findByText("Друг"));
    await waitFor(() => expect(api.giftArtifact).toHaveBeenCalledWith(11, 42));
  });

  it("explains the rules and the stadium bonus in the shop", async () => {
    wrap(<ArtifactsPage />);
    fireEvent.click(await screen.findByText("Магазин"));
    expect(await screen.findByText(/Копии одного артефакта не суммируются/)).toBeInTheDocument();
    expect(screen.getByText(/Если есть стадион «Энфилд»: −2%/)).toBeInTheDocument();
    expect(screen.getByText("+3 к рейтингу карточек «Марадона»")).toBeInTheDocument();
    expect(screen.getAllByText("+20 статуса Моему игроку").length).toBeGreaterThan(0);
  });
});
