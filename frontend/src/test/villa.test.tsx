import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { collectVillaIncome, saveVillaLayout, type VillaItem, type VillaState } from "@/api/town";
import { cellSet, checkLayout, corner, drawOrder, fencePieces, footprint, freeSpot, isPath, openCells, pathKerbs, unproject, zoomView, HOME_VIEW, PLOT_W } from "@/lib/villa";
import { PLOT_CELLS, PLOT_CHECK } from "@/lib/villaPlot";

/** A rectangle of open cells (the real plot is the meadow, PLOT_CELLS). */
const rect = (w: number, h: number) => cellSet(Array.from({ length: w * h }, (_, i) => [i % w, Math.floor(i / w)] as [number, number]));
import TownVillaPage from "@/pages/TownVillaPage";

const item = (over: Partial<VillaItem>): VillaItem => ({
  id: 1, code: "villa", name: "Вилла", emoji: "🏡", kind: "villa", w: 3, h: 3, x: 12, y: 17, rot: 0, serial: null, level: 1, ...over,
});

const villa = (): VillaState => ({
  villa_level: 1, garage_level: 0, cells_open: 140, cells_total: PLOT_CELLS.length,
  combos: [], all_combos: [{ a: "pool", b: "palm", name: "Тропики", emoji: "🌴", a_name: "Бассейн", b_name: "Пальма" }],
  prestige_combo: 5, prestige_staff: 15,
  items: [item({}), item({ id: 2, code: "palm", name: "Пальма", emoji: "🌴", kind: "yard", w: 1, h: 1, x: null, y: null, level: null })],
  car: null, staff: [], prestige: 21, prestige_pct: 0, user_id: 1, likes_total: 4,
  next_villa: { level: 2, price: 15000, cells: 220 }, next_garage: { level: 1, price: 8000, slots: 1 },
  garage_slots: 0, cars: 0,
  shop: [{ code: "palm", name: "Пальма", emoji: "🌴", kind: "yard", w: 1, h: 1, coins: 600, stars: 0, prestige: 1, owned: 1, supply: 0, sold: 0, can_buy: true, reason: "" }],
  posts: [{ post: "security", name: "Охрана", emoji: "🛡️", workplace: [] }], candidates: [],
  prestige_per_pct: 60, prestige_max_pct: 5, max_items: 120,
  perks: [{ code: "training", name: "Своё поле", emoji: "⚽", text: "+1 бесплатная тренировка «Моего игрока» в день" }],
  all_perks: [
    { code: "training", name: "Своё поле", emoji: "⚽", text: "+1 бесплатная тренировка «Моего игрока» в день", buildings: ["Мини-поле", "Поле для пятёрок"] },
    { code: "travel", name: "Свой транспорт", emoji: "🚁", text: "турне клуба в «Менеджере» дешевле на 20%", buildings: ["Вертолётная площадка"] },
  ],
  party_until: null,
  income: { coins: 60, ready: true, base: 20, per_100: 20, cap: 200 },
  party: { cost: 1000, hours: 24, guest_coins: 30, can_throw: true },
});

vi.mock("@/api/town", () => ({
  fetchVilla: vi.fn(async () => villa()),
  saveVillaLayout: vi.fn(async () => villa()),
  buyVillaItem: vi.fn(), upgradeVilla: vi.fn(), createVillaInvoice: vi.fn(), fetchTownInvoiceStatus: vi.fn(),
  chooseVillaCar: vi.fn(), setVillaStaff: vi.fn(),
  collectVillaIncome: vi.fn(async () => ({ ...villa(), income: { ...villa().income, ready: false }, income_paid: 60, new_balance: 1060 })),
  throwVillaParty: vi.fn(),
}));

describe("villa grid", () => {
  it("checks the layout like the server", () => {
    expect(checkLayout(rect(8, 8), [{ id: 1, code: "villa", x: 1, y: 1, rot: 0, w: 3, h: 3 }])).toBeNull();
    expect(checkLayout(rect(8, 8), [{ id: 1, code: "villa", x: 6, y: 1, rot: 0, w: 3, h: 3 }])).toBe("Предмет выходит за участок");
    expect(checkLayout(rect(8, 8), [
      { id: 1, code: "villa", x: 1, y: 1, rot: 0, w: 3, h: 3 }, { id: 2, code: "palm", x: 3, y: 3, rot: 0, w: 1, h: 1 },
    ])).toBe("Клетки уже заняты");
    expect(checkLayout(rect(8, 8), [{ id: 1, code: "villa", x: null, y: null, rot: 0, w: 3, h: 3 }])).toBe("Виллу и гараж нельзя убрать на склад");
    expect(footprint({ w: 3, h: 2, rot: 1 })).toEqual([2, 3]);
    // The meadow: centre first, the same list as the server (PLOT_CHECK).
    expect(PLOT_CELLS.reduce((sum, [x, y], i) => (sum + (i + 1) * (x * 64 + y)) % 1_000_000_007, 0)).toBe(PLOT_CHECK);
    expect(new Set(PLOT_CELLS.map(([x, y]) => `${x}:${y}`)).size).toBe(PLOT_CELLS.length);
    const spot = freeSpot(openCells(60), [{ id: 9, code: "pool", x: null, y: null, rot: 0, w: 3, h: 2 }], 9);
    expect(spot && checkLayout(cellSet(openCells(60)), [{ id: 9, code: "pool", x: spot[0], y: spot[1], rot: 0, w: 3, h: 2 }])).toBeNull();
    const order = drawOrder([item({ id: 5, x: 4, y: 4 }), item({ id: 6, x: 0, y: 0 }), item({ id: 7, x: null, y: null })]);
    expect(order.map((i) => i.id)).toEqual([6, 5]);
  });

  it("maps the lawn both ways and joins paths", () => {
    for (const [gx, gy] of [[0, 0], [3.5, 7.25], [29, 35], [29, 0]]) {
      const [px, py] = corner(gx, gy);
      const [bx, by] = unproject(px, py);
      expect(bx).toBeCloseTo(gx, 3);
      expect(by).toBeCloseTo(gy, 3);
    }
    // Every meadow cell's middle lies inside the picture.
    for (const [x, y] of PLOT_CELLS) {
      expect(corner(x + 0.5, y + 0.5)[0]).toBeGreaterThan(0);
      expect(corner(x + 0.5, y + 0.5)[0]).toBeLessThan(PLOT_W);
    }
    expect(checkLayout(rect(9, 6), [{ id: 1, code: "villa", x: 6, y: 3, rot: 0, w: 3, h: 3 }])).toBeNull();
    expect(checkLayout(rect(9, 6), [{ id: 1, code: "villa", x: 3, y: 4, rot: 0, w: 3, h: 3 }])).toBe("Предмет выходит за участок");
    const cells = new Set(["2:2", "3:2"]);
    expect(pathKerbs(cells, 2, 2)).toEqual({ n: true, e: false, s: true, w: true });
    const near = zoomView(HOME_VIEW, 2, 540, 700);
    expect(near.w).toBe(PLOT_W / 2);
    expect(zoomView(near, 0.1, 450, 600).w).toBe(PLOT_W);  // never past the whole picture
  });
});

describe("villa fences", () => {
  it("joins sections into lines, corners and gates", () => {
    const cells = new Set(["2:2", "3:2", "4:2", "4:3", "4:4"]);
    expect(fencePieces(cells, 3, 2, false)).toEqual({ full: "b", halves: [], post: false }); // along x
    expect(fencePieces(cells, 4, 3, false)).toEqual({ full: "a", halves: [], post: false }); // along y
    expect(fencePieces(cells, 4, 2, false)).toEqual({ halves: ["s", "w"], post: true }); // the corner
    expect(fencePieces(cells, 2, 2, false)).toEqual({ halves: ["e"], post: true }); // an end
    expect(fencePieces(cells, 3, 2, true).full).toBe("gate_b");
    expect(fencePieces(new Set(["7:7"]), 7, 7, false)).toEqual({ full: "a", halves: [], post: false });
  });
});

describe("villa paths", () => {
  it("knows every kind of path tile and keeps them flat", () => {
    for (const code of ["path", "path_gravel", "path_terracotta", "path_deck", "path_stepping"]) expect(isPath(code)).toBe(true);
    expect(isPath("pool")).toBe(false);
    // kerbs only towards cells without a tile of the same kind
    expect(pathKerbs(new Set(["1:1", "2:1"]), 1, 1)).toEqual({ n: true, e: false, s: true, w: true });
  });
});

describe("TownVillaPage", () => {
  it("places a thing from the build tray, turns it and saves at once", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/town/villa"]}>
          <Routes><Route path="/town/villa" element={<TownVillaPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Престиж 21/)).toBeInTheDocument();
    // The build tray: a palm in storage lands on a free spot, waiting for ✓.
    fireEvent.click(screen.getByRole("button", { name: "Пальма" }));
    expect(screen.getByTestId("villa-mark")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("villa-cell-13-18"));  // under the villa: red, can't put
    expect(screen.getByRole("button", { name: "Поставить" })).toBeDisabled();
    fireEvent.click(screen.getByTestId("villa-cell-16-18"));
    fireEvent.click(screen.getByRole("button", { name: "Повернуть" }));
    fireEvent.click(screen.getByRole("button", { name: "Поставить" }));
    await waitFor(() => expect(saveVillaLayout).toHaveBeenCalledWith([{ id: 2, x: 16, y: 18, rot: 1 }]));
  });

  it("shows the villa in the game: income, the party and the perks", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/town/villa"]}>
          <Routes><Route path="/town/villa" element={<TownVillaPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/доход виллы за сегодня/)).toBeInTheDocument();
    expect(screen.getByText(/Бонусы в игре · 1 из 2/)).toBeInTheDocument();
    expect(screen.getByText(/\+1 бесплатная тренировка/)).toBeInTheDocument();
    expect(screen.getByText(/гостям \+30 за лайк/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/доход виллы за сегодня/));
    await waitFor(() => expect(collectVillaIncome).toHaveBeenCalled());
    expect(await screen.findByText("Доход виллы: +60 монет")).toBeInTheDocument();
  });
});
