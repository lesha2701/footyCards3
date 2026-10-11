import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { MyPlayer, MyPlayerView } from "@/api/myPlayer";
import MyPlayerPage from "@/pages/MyPlayerPage";

const fetchMyPlayer = vi.fn<() => Promise<MyPlayerView>>();
const createMyPlayer = vi.fn();
const trainMyPlayer = vi.fn();
const buyMyPlayerCosmetic = vi.fn();
const setMyPlayerSkill = vi.fn();
vi.mock("@/api/myPlayer", async (orig) => ({
  ...(await orig<typeof import("@/api/myPlayer")>()),
  fetchMyPlayer: () => fetchMyPlayer(),
  createMyPlayer: (...args: unknown[]) => createMyPlayer(...args),
  trainMyPlayer: (...args: unknown[]) => trainMyPlayer(...args),
  buyMyPlayerCosmetic: (...args: unknown[]) => buyMyPlayerCosmetic(...args),
  setMyPlayerSkill: (...args: unknown[]) => setMyPlayerSkill(...args),
}));

const player: MyPlayer = {
  name: "Тест Игрок", number: 9, position: "ST", category: "FWD",
  appearance: { skin: 1, hair: 2, hair_color: 0, beard: 1, eye_color: 2, kit: 3, kit_pattern: 1 },
  attributes: { atk: 68, def: 36 },
  rating: 52, attack_rating: 68, defense_rating: 36, tier: "bronze", tier_label: "Бронза", key_attr: "atk",
};

const baseView: MyPlayerView = {
  enabled: true, balance: 5000, player: null, xp: 0, level: 1, xp_into_level: 0, xp_for_next: 100, xp_today: 0,
  xp_daily_cap: 200, xp_per_reward: 10, xp_career_match: 15, points_available: 0, points_per_level: 4,
  rating_cap: 88, at_rating_cap: false, tier_thresholds: [65, 75, 85],
  appearance_options: { skin: 6, hair: 14, hair_color: 7, beard: 5, eye_color: 6, kit: 10, kit_pattern: 4 },
  attr_labels: { atk: "Атака", def: "Защита" },
  next_tier_at: null,
  skill: null,
  training: {
    done_today: false, can_train: true, extra_credits: 0, extra_bought_today: 0, extra_max: 3, extra_left_today: 3,
    extra_coins_price: 300, extra_stars_price: 15, xp_base: 20, xp_per_hit: 15, max_hits: 3,
  },
  cosmetics: {
    owned: [], accessory: null, background: null,
    catalog: [{ code: "headband", kind: "accessory", name: "Повязка на голову", price: 300, owned: false }],
  },
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <MyPlayerPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("MyPlayerPage", () => {
  beforeEach(() => {
    fetchMyPlayer.mockReset();
    createMyPlayer.mockReset();
    trainMyPlayer.mockReset();
    buyMyPlayerCosmetic.mockReset();
    setMyPlayerSkill.mockReset();
  });

  it("walks through the constructor and creates the player", async () => {
    fetchMyPlayer.mockResolvedValue(baseView);
    createMyPlayer.mockResolvedValue({ ...baseView, player });
    renderPage();
    expect(await screen.findByText("Создай своего игрока")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Дреды" }));
    fireEvent.click(screen.getByRole("button", { name: "Зелёные" }));
    fireEvent.click(screen.getByRole("button", { name: "Дальше" }));
    fireEvent.click(screen.getByRole("button", { name: "Дальше" }));
    const create = screen.getByRole("button", { name: "Создать игрока" });
    expect(create).toBeDisabled(); // no name yet
    fireEvent.change(screen.getByPlaceholderText("Например, А. Иванов"), { target: { value: "Тест Игрок" } });
    fireEvent.click(screen.getByRole("button", { name: "CAM" }));
    fireEvent.click(create);
    await waitFor(() => expect(createMyPlayer).toHaveBeenCalled());
    expect(createMyPlayer.mock.calls[0][0]).toMatchObject({ name: "Тест Игрок", position: "CAM", appearance: { hair: 9, eye_color: 3 } });
    expect(await screen.findByTestId("my-player-card")).toBeInTheDocument();
  });

  it("spends attribute points and shows the new frame on a tier change", async () => {
    fetchMyPlayer.mockResolvedValue({
      ...baseView, player, level: 3, points_available: 8, next_tier_at: 65,
    });
    trainMyPlayer.mockResolvedValue({
      ...baseView, level: 3, points_available: 3,
      player: { ...player, rating: 65, tier: "silver", tier_label: "Серебро", attributes: { atk: 73, def: 36 } },
    });
    renderPage();
    expect(await screen.findByText("Уровень 3")).toBeInTheDocument();
    expect(screen.getByText("главная для ST")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "+5 Атака" }));
    await waitFor(() => expect(trainMyPlayer).toHaveBeenCalledWith("atk", 5));
    expect(await screen.findByText("Нажми, чтобы продолжить")).toBeInTheDocument();
  });

  it("buys a cosmetic in the style tab and assigns a skill like a card", async () => {
    const skill = {
      enabled: true, code: null, name: null, icon: null, level: 0, level_label: null, upgrade: null,
      assign_token_cost: 1, assign_coin_cost: 0, replace_token_cost: 1, replace_coin_cost: 300,
      tokens: { sniper: 1 },
      options: [{ code: "sniper", name: "Снайпер", icon: "🎯", effect: "Точнее бьёт", bonus_phrase: "" }],
    };
    fetchMyPlayer.mockResolvedValue({ ...baseView, player, level: 10, skill });
    buyMyPlayerCosmetic.mockResolvedValue({ ...baseView, player: { ...player, accessory: "headband" }, level: 10, skill });
    setMyPlayerSkill.mockResolvedValue({
      ...baseView, player, level: 10, skill: { ...skill, code: "sniper", name: "Снайпер", level: 1, level_label: "I" },
    });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Назначить" }));
    await waitFor(() => expect(setMyPlayerSkill).toHaveBeenCalled());
    expect(setMyPlayerSkill.mock.calls[0][0]).toBe("sniper");

    fireEvent.click(screen.getByRole("button", { name: "Стиль" }));
    fireEvent.click(await screen.findByRole("button", { name: /300/ }));
    await waitFor(() => expect(buyMyPlayerCosmetic).toHaveBeenCalled());
    expect(buyMyPlayerCosmetic.mock.calls[0][0]).toBe("headband");
  });

  it("offers extra trainings for coins and Stars after the free one", async () => {
    fetchMyPlayer.mockResolvedValue({
      ...baseView, player, training: { ...baseView.training, done_today: true, can_train: false, extra_left_today: 2 },
    });
    renderPage();
    expect(await screen.findByText(/сегодня можно купить 2 из 3/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /300/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: "⭐ 15" })).toBeEnabled();
  });
});
