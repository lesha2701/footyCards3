import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  buyTownDecor, buyTownHotel, buyTownHouse, claimTownIncome, fetchTown, sellTownResidentSpare, unlockTown, type TownResident, type TownResidentsAlbum, type TownState,
} from "@/api/town";
import { useAuthStore } from "@/store/authStore";
import { DISTRICTS, MAP_ZONES, SCENE_H, SCENE_W, SPRITES, moverAt, type Mover } from "@/lib/town";
import TownPage from "@/pages/TownPage";
import TownResidentsPage from "@/pages/TownResidentsPage";

const inside = ([x, y]: [number, number]) => x >= 0 && x <= SCENE_W && y >= 0 && y <= SCENE_H;

describe("town data", () => {
  it("has five districts of twelve buildings and the base on the map", () => {
    expect(DISTRICTS.map((d) => d.code)).toEqual(["center", "favela", "beach", "mountains", "business"]);
    expect(MAP_ZONES.map((z) => z.code).sort()).toEqual(["base", "beach", "business", "center", "favela", "mountains"]);
    for (const d of DISTRICTS) {
      expect(d.buildings).toHaveLength(12);
      expect(new Set(d.buildings.map((b) => b.code)).size).toBe(12);
      for (const { zone } of d.buildings) {
        expect(zone[0] < zone[2] && zone[1] < zone[3]).toBe(true);
        expect(inside([zone[0], zone[1]]) && inside([zone[2], zone[3]])).toBe(true);
      }
      for (const m of d.movers) {
        expect(SPRITES[m.sprite]).toBeDefined();
        expect(m.route.points.every(inside)).toBe(true);
      }
    }
  });
});

describe("moverAt", () => {
  const line: Mover = { sprite: "people/01", route: { points: [[0, 0], [100, 0]] }, speed: 10, start: 0 };

  it("walks an open route to the end and back", () => {
    expect(moverAt(line, 5)).toMatchObject({ x: 50, y: 0 });
    expect(moverAt(line, 5).dx).toBeGreaterThan(0);
    const back = moverAt(line, 15);
    expect(back.x).toBeCloseTo(50);
    expect(back.dx).toBeLessThan(0);
  });

  it("goes round a loop", () => {
    const square: Mover = { ...line, route: { points: [[0, 0], [10, 0], [10, 10], [0, 10]], loop: true }, speed: 1 };
    expect(moverAt(square, 15)).toMatchObject({ x: 10, y: 5 });
    expect(moverAt(square, 25)).toMatchObject({ x: 5, y: 10 });
    expect(moverAt(square, 40)).toMatchObject({ x: 0, y: 0 });
  });
});

const town = (over: Partial<TownState> = {}): TownState => ({
  enabled: true,
  unlocked: true,
  unlock_coins: 5000,
  rename_stars: 99,
  name: null,
  hotel: { owned: false, price: 5000, cards: 250, max_cards: 1000, rent_per_100_cards: 30, rent: 75 },
  decor: [
    { code: "park", name: "Парк с фонтаном", price: 40000, rent_pct: 8, owned: false },
    { code: "pier", name: "Пирс с колесом обозрения", price: 3000, rent_pct: 5, owned: false },
    { code: "island", name: "Остров легенды", price: 75000, rent_pct: 12, owned: true },
  ],
  decor_pct: 12,
  residents: { enabled: true, population: 7, rent_per_resident: 1, rent: 7, rent_pct: 20, hotel_pct: 0, daily_coins: 0 },
  houses: [{ district: "beach", code: "surf" }],
  owned_total: 1,
  total_houses: 60,
  price_growth_pct: 4,
  districts: DISTRICTS.map((d) => ({
    code: d.code, name: d.name, rent: 45, next_price: 4160, owned: d.code === "beach" ? 1 : 0, total: 12,
  })),
  income: { rate_per_day: 45, pending: 30, cap: 45, max_hours: 24 },
  ...over,
});

const resident = (id: number, name: string, copies: number, over: Partial<TownResident> = {}): TownResident => ({
  id, name, title: null, description: null, icon: "🧑", image_path: null, rarity: "common", bonus: "none", bonus_value: 0,
  bonus_label: "", effect_label: "+1 монета в день", owned: copies > 0, copies, spare_coins: 10, ...over,
});
const album = (): TownResidentsAlbum => ({
  enabled: true,
  residents: [
    resident(2, "Капитан", 1, { rarity: "legendary", bonus: "rent_pct", bonus_value: 20, bonus_label: "+20% к ренте домов" }),
    resident(1, "Рыбак", 2),
    resident(3, "Тень", 0),
  ],
  owned_count: 2, total_count: 3, population: 3, rent_per_resident: 1,
  bonuses: { rent_pct: 20, hotel_pct: 0, daily_coins: 0 }, caps: { pct: 100, daily_coins: 500 },
});

vi.mock("@/api/town", () => ({
  fetchTown: vi.fn(async () => town()),
  buyTownHouse: vi.fn(async () => ({ ...town(), new_balance: 840 })),
  claimTownIncome: vi.fn(async () => ({ ...town(), claimed: 30, new_balance: 5030 })),
  buyTownHotel: vi.fn(async () => ({
    ...town({ hotel: { owned: true, price: 5000, cards: 250, max_cards: 1000, rent_per_100_cards: 30, rent: 75 } }),
    new_balance: 0,
  })),
  buyTownDecor: vi.fn(async () => ({
    ...town({ decor: town().decor.map((d) => ({ ...d, owned: true })) }), new_balance: 2000,
  })),
  unlockTown: vi.fn(async () => ({ ...town(), new_balance: 1000 })),
  fetchTownResidents: vi.fn(async () => album()),
  sellTownResidentSpare: vi.fn(async () => ({ ...album(), sold_coins: 10, new_balance: 5010 })),
  createTownRenameInvoice: vi.fn(),
  fetchTownInvoiceStatus: vi.fn(),
}));

describe("TownPage", () => {
  beforeEach(() => {
    vi.mocked(buyTownHouse).mockClear();
    vi.mocked(claimTownIncome).mockClear();
    vi.mocked(fetchTown).mockImplementation(async () => town());
    useAuthStore.setState({ user: { ...(useAuthStore.getState().user ?? {}), balance: 5000 } as never });
  });

  const at = (path: string) =>
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/town" element={<TownPage />} />
            <Route path="/town/residents" element={<TownResidentsPage />} />
            <Route path="/town/:district" element={<TownPage />} />
            <Route path="/base" element={<p>экран базы</p>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

  it("opens a district from the map, and the base on its own page", async () => {
    at("/town");
    fireEvent.click(screen.getByRole("button", { name: "Фавелы" }));
    expect(screen.getByRole("heading", { name: "Фавелы" })).toBeInTheDocument();
    expect(await screen.findAllByRole("button", { name: /4\s160 монет/ })).toHaveLength(12);
  });

  it("goes to the club base", () => {
    at("/town");
    fireEvent.click(screen.getByRole("button", { name: "Клубная база" }));
    expect(screen.getByText("экран базы")).toBeInTheDocument();
  });

  it("buys a house from its sheet", async () => {
    at("/town/beach");
    fireEvent.click(await screen.findByRole("button", { name: /^Маяк · / }));
    expect(screen.getByRole("dialog", { name: "Маяк" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Купить за 4\s160/ }));
    await waitFor(() => expect(buyTownHouse).toHaveBeenCalledWith("beach", "lighthouse", expect.any(String)));
    await waitFor(() => expect(useAuthStore.getState().user?.balance).toBe(840));
  });

  it("shows an owned house and collects the rent", async () => {
    at("/town/beach");
    fireEvent.click(await screen.findByRole("button", { name: "Серф-школа · твой дом" }));
    expect(screen.getByText(/Твой дом/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Закрыть" }));
    fireEvent.click(screen.getByRole("button", { name: "Забрать" }));
    expect(await screen.findByText(/\+30 монет/)).toBeInTheDocument();
  });

  it("does not offer a house the player cannot afford", async () => {
    useAuthStore.setState({ user: { ...(useAuthStore.getState().user ?? {}), balance: 100 } as never });
    at("/town/beach");
    fireEvent.click(await screen.findByRole("button", { name: /^Маяк · / }));
    expect(screen.getByRole("button", { name: /Не хватает 4\s060 монет/ })).toBeDisabled();
  });

  it("opens a locked town for coins and sells nothing before", async () => {
    vi.mocked(fetchTown).mockImplementation(async () => town({ unlocked: false, houses: [], owned_total: 0 }));
    at("/town");
    const open = await screen.findByRole("button", { name: /Открыть город за 5\s000 монет/ });
    expect(screen.queryByRole("region", { name: "Отель" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Переименовать|Дать городу имя/ })).not.toBeInTheDocument();
    fireEvent.click(open);
    await waitFor(() => expect(unlockTown).toHaveBeenCalled());
    await waitFor(() => expect(useAuthStore.getState().user?.balance).toBe(1000));
    expect(await screen.findByText(/Город твой/)).toBeInTheDocument();
  });

  it("opens a closed place on the map, and fireworks go up once all are open", async () => {
    at("/town");
    expect(await screen.findByRole("button", { name: "Остров легенды · твоё" })).toBeInTheDocument();
    expect(screen.queryByTestId("town-fireworks")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /^Пирс с колесом обозрения · 3\s000 монет$/ }));
    expect(screen.getByRole("dialog", { name: "Пирс с колесом обозрения" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Открыть за 3\s000/ }));
    await waitFor(() => expect(buyTownDecor).toHaveBeenCalledWith("pier", expect.any(String)));
    expect(await screen.findByText(/Пирс с колесом обозрения открыто — \+5% к ренте домов/)).toBeInTheDocument();
    expect(screen.getByTestId("town-fireworks")).toBeInTheDocument();
    await waitFor(() => expect(useAuthStore.getState().user?.balance).toBe(2000));
  });

  it("does not open the town without the coins", async () => {
    useAuthStore.setState({ user: { ...(useAuthStore.getState().user ?? {}), balance: 1000 } as never });
    vi.mocked(fetchTown).mockImplementation(async () => town({ unlocked: false }));
    at("/town");
    expect(await screen.findByRole("button", { name: /не хватает 4\s000 монет/ })).toBeDisabled();
  });

  it("shows the residents on the map and their album, and sells a spare copy", async () => {
    at("/town");
    expect(await screen.findByRole("link", { name: "Жители города" })).toHaveTextContent(/Жители · 7.*\+7\/д/);
    at("/town/residents");
    expect(await screen.findByText(/Собрано 2 из 3 · население 3/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Тень, ещё нет" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Рыбак, копий 2" }));
    fireEvent.click(screen.getByRole("button", { name: /Продать лишнюю за 10/ }));
    await waitFor(() => expect(sellTownResidentSpare).toHaveBeenCalledWith(1, 1));
    expect(await screen.findByText(/Продано: \+10 монет/)).toBeInTheDocument();
    await waitFor(() => expect(useAuthStore.getState().user?.balance).toBe(5010));
  });

  it("shows the town's own name and buys the hotel for the cards held", async () => {
    vi.mocked(fetchTown).mockImplementation(async () => town({ name: "Сан-Виктор" }));
    at("/town");
    expect(await screen.findByText("Сан-Виктор")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Переименовать · ⭐ 99/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отель" })).toHaveTextContent(/\+75\/д.*5\s000/);
    fireEvent.click(screen.getByRole("button", { name: "Отель" }));
    await waitFor(() => expect(buyTownHotel).toHaveBeenCalled());
    expect(await screen.findByText(/Отель открыт/)).toBeInTheDocument();
  });
});
