import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ManagerFilialView } from "@/api/manager";
import FilialPanel from "@/components/manager/FilialPanel";

const fetchManagerFilial = vi.fn<() => Promise<ManagerFilialView>>();
const openManagerFilial = vi.fn();
const pickManagerFilial = vi.fn();
const priceManagerAlumnus = vi.fn();
vi.mock("@/api/manager", async (orig) => ({
  ...(await orig<typeof import("@/api/manager")>()),
  fetchManagerFilial: () => fetchManagerFilial(),
  openManagerFilial: (...a: unknown[]) => openManagerFilial(...a),
  pickManagerFilial: (...a: unknown[]) => pickManagerFilial(...a),
  priceManagerAlumnus: (...a: unknown[]) => priceManagerAlumnus(...a),
}));

const base: ManagerFilialView = {
  enabled: true, open_coins: 8000, balance: 20_000,
  start: { contracts: 1, contracts_max: 3, every: 4, every_min: 3, candidates: 2, start_age: 17 },
  regions: [
    { code: "europe", name: "Европа", emoji: "🌍", countries: [{ name: "Россия", flag: "🇷🇺" }, { name: "Украина", flag: "🇺🇦" }] },
    { code: "africa", name: "Африка", emoji: "🌍", countries: [{ name: "Гана", flag: "🇬🇭" }] },
  ],
  filial: null,
  buildings: [{ code: "internat", name: "Интернат", emoji: "🏠", about: "+1 контракт", level: 0, max: 2, price: 6000 }],
  alumni: [], history: [], window_open: true, squad_max: 23,
};

const opened: ManagerFilialView = {
  ...base,
  filial: {
    region: "europe", region_name: "Европа", country: "Украина", flag: "🇺🇦", contracts: 1, used: 0, every: 4, next_in: null,
    sold_this_season: false,
    pending: [
      { name: "Олег Бондаренко", country: "Украина", flag: "🇺🇦", position: "ST", rating: 50, stars: 3, peak_age: 26, retire_age: 35 },
      { name: "Ян Новак", country: "Чехия", flag: "🇨🇿", position: "CB", rating: 48, stars: 2, peak_age: 27, retire_age: 34 },
    ],
  },
};

const withAlumnus: ManagerFilialView = {
  ...opened,
  filial: { ...opened.filial!, used: 1, pending: [] },
  alumni: [{
    id: 7, name: "Олег Бондаренко", country: "Украина", flag: "🇺🇦", position: "ST", age: 17, rating: 50, value: 120_000, stars: 3,
    status: "club", peak_age: 26, retire_in: 18, phase: "рост", price: null, goals: 2, sell_back: 60_000, price_min: 110_000, price_max: 360_000,
  }],
};

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

describe("FilialPanel", () => {
  beforeEach(() => { fetchManagerFilial.mockReset(); openManagerFilial.mockReset(); pickManagerFilial.mockReset(); priceManagerAlumnus.mockReset(); });

  it("opens a filial in a chosen country of a region", async () => {
    fetchManagerFilial.mockResolvedValue(base);
    openManagerFilial.mockResolvedValue(opened);
    wrap(<FilialPanel onError={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "🇺🇦 Украина" }));
    expect(screen.getByTestId("filial-promise")).toHaveTextContent("1 на старте, до 3 с «Интернатом»");
    fireEvent.click(screen.getByRole("button", { name: /Открыть за 8/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Открыть" }));
    await waitFor(() => expect(openManagerFilial).toHaveBeenCalledWith("europe", "Украина"));
    expect(await screen.findByTestId("filial-release")).toBeInTheDocument();
  });

  it("shows the release with stars and no peak, and signs one", async () => {
    fetchManagerFilial.mockResolvedValue(opened);
    pickManagerFilial.mockResolvedValue(withAlumnus);
    wrap(<FilialPanel onError={() => {}} />);
    expect(await screen.findByText("Контракты 0/1", { exact: false })).toBeInTheDocument();
    expect(screen.getByText("★★★☆☆")).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Взять" })[0]);
    fireEvent.click(await screen.findByRole("button", { name: "Подписать" }));
    await waitFor(() => expect(pickManagerFilial).toHaveBeenCalledWith(0));
    expect(await screen.findByTestId("filial-alumni")).toBeInTheDocument();
    expect(screen.getByText(/Все контракты заняты/)).toBeInTheDocument();
  });

  it("lists an alumnus for presidents only within the anti-dump bounds", async () => {
    fetchManagerFilial.mockResolvedValue(withAlumnus);
    priceManagerAlumnus.mockResolvedValue(withAlumnus);
    wrap(<FilialPanel onError={() => {}} />);
    fireEvent.click(await screen.findByRole("button", { name: "⋯" }));
    const slider = screen.getByLabelText("Цена") as HTMLInputElement;
    expect(slider.min).toBe("110000");
    expect(slider.max).toBe("360000");
    fireEvent.click(screen.getByRole("button", { name: "Выставить" }));
    await waitFor(() => expect(priceManagerAlumnus).toHaveBeenCalledWith(7, 110_000));
  });
});
