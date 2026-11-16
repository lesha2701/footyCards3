import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { saveVillaLayout, type VillaItem, type VillaState } from "@/api/town";
import { checkLayout, corner, drawOrder, footprint, pathKerbs, unproject, zoomView, HOME_VIEW, PLOT_W } from "@/lib/villa";
import TownVillaPage from "@/pages/TownVillaPage";

const item = (over: Partial<VillaItem>): VillaItem => ({
  id: 1, code: "villa", name: "Вилла", emoji: "🏡", kind: "villa", w: 3, h: 3, x: 1, y: 1, rot: 0, serial: null, level: 1, ...over,
});

const villa = (): VillaState => ({
  villa_level: 1, garage_level: 0, grid: 8, grid_max: 12,
  combos: [], all_combos: [{ a: "pool", b: "palm", name: "Тропики", emoji: "🌴", a_name: "Бассейн", b_name: "Пальма" }],
  prestige_combo: 5, prestige_staff: 15,
  items: [item({}), item({ id: 2, code: "palm", name: "Пальма", emoji: "🌴", kind: "yard", w: 1, h: 1, x: null, y: null, level: null })],
  car: null, staff: [], prestige: 21, prestige_pct: 0, user_id: 1, likes_total: 4,
  next_villa: { level: 2, price: 15000, grid: 9 }, next_garage: { level: 1, price: 8000, slots: 1 },
  garage_slots: 0, cars: 0,
  shop: [{ code: "palm", name: "Пальма", emoji: "🌴", kind: "yard", w: 1, h: 1, coins: 600, stars: 0, prestige: 1, owned: 1, supply: 0, sold: 0, can_buy: true, reason: "" }],
  posts: [{ post: "security", name: "Охрана", emoji: "🛡️", workplace: [] }], candidates: [],
  prestige_per_pct: 60, prestige_max_pct: 5, max_items: 120,
});

vi.mock("@/api/town", () => ({
  fetchVilla: vi.fn(async () => villa()),
  saveVillaLayout: vi.fn(async () => villa()),
  buyVillaItem: vi.fn(), upgradeVilla: vi.fn(), createVillaInvoice: vi.fn(), fetchTownInvoiceStatus: vi.fn(),
  chooseVillaCar: vi.fn(), setVillaStaff: vi.fn(),
}));

describe("villa grid", () => {
  it("checks the layout like the server", () => {
    expect(checkLayout(8, [{ id: 1, code: "villa", x: 1, y: 1, rot: 0, w: 3, h: 3 }])).toBeNull();
    expect(checkLayout(8, [{ id: 1, code: "villa", x: 6, y: 1, rot: 0, w: 3, h: 3 }])).toBe("Предмет выходит за участок");
    expect(checkLayout(8, [
      { id: 1, code: "villa", x: 1, y: 1, rot: 0, w: 3, h: 3 }, { id: 2, code: "palm", x: 3, y: 3, rot: 0, w: 1, h: 1 },
    ])).toBe("Клетки уже заняты");
    expect(checkLayout(8, [{ id: 1, code: "villa", x: null, y: null, rot: 0, w: 3, h: 3 }])).toBe("Виллу и гараж нельзя убрать на склад");
    expect(footprint({ w: 3, h: 2, rot: 1 })).toEqual([2, 3]);
    const order = drawOrder([item({ id: 5, x: 4, y: 4 }), item({ id: 6, x: 0, y: 0 }), item({ id: 7, x: null, y: null })]);
    expect(order.map((i) => i.id)).toEqual([6, 5]);
  });

  it("maps the lawn both ways and joins paths", () => {
    for (const [gx, gy] of [[0, 0], [3.5, 7.25], [12, 12], [12, 0]]) {
      const [px, py] = corner(12, gx, gy);
      const [bx, by] = unproject(12, px, py);
      expect(bx).toBeCloseTo(gx, 3);
      expect(by).toBeCloseTo(gy, 3);
    }
    // The back corner lies above the front one, the grid inside the picture.
    expect(corner(12, 0, 0)[1]).toBeLessThan(corner(12, 12, 12)[1]);
    expect(corner(12, 0, 12)[0]).toBeGreaterThan(0);
    expect(corner(12, 12, 0)[0]).toBeLessThan(PLOT_W);
    const cells = new Set(["2:2", "3:2"]);
    expect(pathKerbs(cells, 2, 2)).toEqual({ n: true, e: false, s: true, w: true });
    const near = zoomView(HOME_VIEW, 2, 450, 600);
    expect(near.w).toBe(450);
    expect(zoomView(near, 0.1, 450, 600).w).toBe(PLOT_W);  // never past the whole picture
  });
});

describe("TownVillaPage", () => {
  it("places a thing from storage on a free cell and saves", async () => {
    render(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <MemoryRouter initialEntries={["/town/villa"]}>
          <Routes><Route path="/town/villa" element={<TownVillaPage />} /></Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText(/Престиж 21/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Пальма/ }));
    fireEvent.click(screen.getByTestId("villa-cell-2-2"));  // under the villa
    expect(screen.getByText("Клетки уже заняты")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("villa-cell-6-6"));
    expect(screen.getAllByTestId("villa-item-palm")).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: /Сохранить/ }));
    await waitFor(() => expect(saveVillaLayout).toHaveBeenCalledWith([{ id: 2, x: 6, y: 6, rot: 0 }]));
  });
});
