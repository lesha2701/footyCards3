import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { fetchMuses, type Muse } from "@/api/muses";
import MuseTile from "@/components/muses/MuseTile";
import ProfileMuse from "@/components/muses/ProfileMuse";
import { museHeartState } from "@/lib/museDate";
import MusesPage from "@/pages/MusesPage";

const muse = (over: Partial<Muse>): Muse => ({
  id: 1, name: "Изабелла", title: "модель из Милана", description: null, icon: "👸", image_path: null,
  rarity: "legendary", collection_id: 1, effect: "daily_coins", effect_value: 300, effect_label: "+360 монет в день",
  base_effect_label: "+300 монет в день", boosted_value: 360, boost_pct: 20, owned: true, user_muse_id: 5, copies: 2,
  is_active: true, accessory_ids: [9], spare_coins: 3000, ...over,
});

const { claimMuseDaily, setActiveMuse } = vi.hoisted(() => ({ claimMuseDaily: vi.fn(), setActiveMuse: vi.fn() }));

vi.mock("@/api/muses", () => ({
  fetchMuses: vi.fn(async () => ({
    enabled: true,
    collections: [{
      id: 1, name: "Звёздные музы", description: null, image_path: null,
      muses: [
        muse({}),
        muse({ id: 2, name: "Камила", owned: false, copies: 0, is_active: false, accessory_ids: [] }),
        muse({ id: 3, name: "Нина", owned: true, copies: 1, is_active: false, accessory_ids: [], effect_label: "+2 свежести в час" }),
      ],
    }],
    active: muse({}),
    owned_count: 2,
    total_count: 3,
    daily: { coins: 360, claimed_today: false, claimed_coins: 0 },
    date: { today: null, coins: 150, required: true, inspiration_hours: 36, inspired_until: null },
    accessories: [
      { id: 9, name: "Сумка", description: null, icon: "👜", image_path: null, kind: "bag", kind_label: "Сумка",
        rarity: "epic", boost_pct: 20, coins_price: 8000, stars_price: 150 },
      { id: 10, name: "Букет роз", description: null, icon: "🌹", image_path: null, kind: "other", kind_label: "Подарок",
        rarity: "common", boost_pct: 5, coins_price: 500, stars_price: 0 },
    ],
    caps: { stat: 6, pp: 12, xp_pct: 30, daily_coins: 1000, accessory_pct: 100 },
  })),
  claimMuseDaily,
  setActiveMuse,
  sellSpareMuse: vi.fn(),
  buyMuseGift: vi.fn(),
  createMuseGiftStarsInvoice: vi.fn(),
  startMuseDate: vi.fn(async () => ({ game: "pairs", game_title: "Найди пару", path: "/play/pairs?muse=1", completed: false, coins: 0 })),
}));

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <MusesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("Музы", () => {
  it("shows the active Muse, her daily coins and the album progress", async () => {
    renderPage();
    expect(await screen.findByText("Активная муза")).toBeInTheDocument();
    expect(screen.getAllByText("+360 монет в день").length).toBeGreaterThan(0);
    expect(screen.getByText(/Забрать 360/)).toBeInTheDocument();
    expect(screen.getByText("2/3")).toBeInTheDocument();
    expect(screen.getByText("Камила")).toBeInTheDocument();
  });

  it("opens a Muse with her gifts: given ones are marked, others can be bought", async () => {
    renderPage();
    fireEvent.click((await screen.findAllByText("Изабелла"))[1]);
    expect(await screen.findByText("✓ подарено")).toBeInTheDocument();
    expect(screen.getByText("Букет роз")).toBeInTheDocument();
    expect(screen.getByText(/Продать лишнюю \+3000/)).toBeInTheDocument();
    expect(screen.getByText("Активна · снять")).toBeInTheDocument();
  });

  it("claims the daily coins", async () => {
    claimMuseDaily.mockImplementationOnce(async () => ({ ...(await fetchMuses()), claimed: 360, new_balance: 1360 }));
    renderPage();
    fireEvent.click(await screen.findByText(/Забрать 360/));
    await waitFor(() => expect(claimMuseDaily).toHaveBeenCalled());
    expect(await screen.findByText("+360 монет от музы")).toBeInTheDocument();
  });

  it("pack recap tile names the Muse and her bonus", () => {
    render(<MuseTile opened={{ muse: muse({}), is_new: true, copies: 1 }} />);
    expect(screen.getByText("Изабелла")).toBeInTheDocument();
    expect(screen.getByText("NEW")).toBeInTheDocument();
    expect(screen.getByText(/Муза · \+360 монет в день/)).toBeInTheDocument();
  });

  it("profile: the big portrait opens the picker of own Muses and switches the active one", async () => {
    setActiveMuse.mockImplementationOnce(async () => await fetchMuses());
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <ProfileMuse />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByRole("button", { name: /Сменить музу: сейчас Изабелла/ }));
    expect(await screen.findByText("Выбери музу")).toBeInTheDocument();
    expect(screen.queryByText("Камила")).not.toBeInTheDocument(); // not owned — not offered
    fireEvent.click(screen.getByText("Нина"));
    await waitFor(() => expect(setActiveMuse).toHaveBeenCalledWith(3));
  });

  it("date: a missing date is shown and the button opens today's game", async () => {
    renderPage();
    expect(await screen.findByText(/Муза скучает/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Свидание: случайная мини-игра/));
    const { startMuseDate } = await import("@/api/muses");
    await waitFor(() => expect(startMuseDate).toHaveBeenCalled());
  });

  it("heart: red while today's date waits, gradient when inspired, black when she misses you", () => {
    const today = { game: "pairs", game_title: "Найди пару", path: "/play/pairs?muse=1", completed: true, coins: 150 };
    const date = { today: null, coins: 150, required: true, inspiration_hours: 36, inspired_until: null };
    expect(museHeartState({ date })).toBe("date");
    expect(museHeartState({ date: { ...date, today: { ...today, completed: false } } })).toBe("date");
    expect(museHeartState({ date: { ...date, today, inspired_until: "2026-10-24T20:00:00+00:00" } })).toBe("inspired");
    expect(museHeartState({ date: { ...date, today } })).toBe("bored");
  });

  it("/muses?open=<id> (home «Профиль музы») opens her card", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/muses?open=1"]}>
          <MusesPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(await screen.findByText("✓ подарено")).toBeInTheDocument();
  });
});
