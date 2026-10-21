import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ManagerClub, ManagerContract, ManagerLeague, ManagerView } from "@/api/manager";
import { eur } from "@/lib/managerMoney";
import ManagerPage from "@/pages/ManagerPage";

const fetchManager = vi.fn<() => Promise<ManagerView>>();
const fetchManagerMarket = vi.fn();
const fetchManagerCatalog = vi.fn();
const fetchManagerPopular = vi.fn();
const fetchManagerClubCard = vi.fn();
const foundManagerClub = vi.fn();
const offerManagerContract = vi.fn();
const respondManagerOffer = vi.fn();
const signManagerNpc = vi.fn();
const buyManagerCosmetic = vi.fn();
const buyManagerMerch = vi.fn();
const updateManagerClub = vi.fn();
vi.mock("@/api/manager", async (orig) => ({
  ...(await orig<typeof import("@/api/manager")>()),
  fetchManager: () => fetchManager(),
  fetchManagerMarket: () => fetchManagerMarket(),
  fetchManagerCatalog: (...args: unknown[]) => fetchManagerCatalog(...args),
  fetchManagerPopular: () => fetchManagerPopular(),
  fetchManagerClubCard: (...args: unknown[]) => fetchManagerClubCard(...args),
  foundManagerClub: (...args: unknown[]) => foundManagerClub(...args),
  offerManagerContract: (...args: unknown[]) => offerManagerContract(...args),
  respondManagerOffer: (...args: unknown[]) => respondManagerOffer(...args),
  signManagerNpc: (...args: unknown[]) => signManagerNpc(...args),
  buyManagerCosmetic: (...args: unknown[]) => buyManagerCosmetic(...args),
  buyManagerMerch: (...args: unknown[]) => buyManagerMerch(...args),
  updateManagerClub: (...args: unknown[]) => updateManagerClub(...args),
}));

const LOOK = {
  shape: "shield", symbol: "⚽", color: "#1f8a4c", color2: "#f5f5f5", kit: "plain", kit_color: "#1f8a4c", kit_color2: "#f5f5f5",
  frame: "classic", theme: "night",
};
const TACTICS = {
  edge_pct: 4,
  styles: [
    { value: "attacking" as const, label: "Атака", about: "Нападение +6%", beats: "defensive" as const, beats_label: "Оборона", reason: "штурм" },
    { value: "possession" as const, label: "Владение", about: "Полузащита +6%", beats: "counter" as const, beats_label: "Контратака", reason: "мяч" },
    { value: "defensive" as const, label: "Оборона", about: "Защита +6%", beats: "possession" as const, beats_label: "Владение", reason: "блок" },
    { value: "counter" as const, label: "Контратака", about: "Атака и защита +3%", beats: "attacking" as const, beats_label: "Атака", reason: "пространство" },
  ],
  formations: [{ value: "4-3-3", label: "4-3-3", attack: 0, defense: 0 }, { value: "3-4-3", label: "3-4-3", attack: 4, defense: -4 }],
};

const base: ManagerView = {
  enabled: true, has_player: true, balance: 5000, level: 4, market_open: false, my_value: 3_500_000, my_rating: 70, my_trend_pct: 12,
  season: { key: "2026-W43", phase: "preseason", preseason_ends_at: "2026-10-21T21:00:00Z", first_round_at: "2026-10-22T10:00:00Z", slots: ["13:00", "17:00", "21:00"], rounds: 15 },
  pyramid: [
    { division: 1, name: "Дивизион 1", clubs: 0, capacity: 16, grant: 120_000_000, rating: 80 },
    { division: 2, name: "Дивизион 2", clubs: 3, capacity: null, grant: 70_000_000, rating: 77 },
  ],
  rules: {
    found_cost: 1500, min_level: 3, max_live: 5, squad_max: 22, live_wage_max: 3000, wage_eur_per_coin: 1000, contract_seasons: [1, 2, 3],
    league_size: 16, promote: 2, place_rewards: [1000, 600, 300], place_budget: [3_000_000, 2_000_000, 1_000_000], rounds: 15, divisions: 2,
    promotion_bonus_pct: 50, parachute_pct: 33, tactics: TACTICS,
  },
  club: null, contract: null, offers: [], league: null,
  shop: {
    cosmetics: [
      { code: "symbol_ball", kind: "symbol", name: "Мяч", value: "⚽", coins: 0, stars: 0, owned: false, usable: true },
      { code: "symbol_lion", kind: "symbol", name: "Лев", value: "🦁", coins: 1500, stars: 20, owned: false, usable: false },
    ],
    palette: ["#1f8a4c", "#c62828"], merch_items: [], my_merch: [], pro_stars: 149, pro_days: 30,
  },
};

const contract: ManagerContract = {
  id: 5, user_id: 2, kind: "sign", status: "active", fee: 0, wage: 600, wage_eur: 600_000, seasons_total: 2, seasons_left: 2, club_agreed: true,
  player_agreed: true, matches_played: 0, goals: 0, assists: 0, earned: 0, player_name: "Мария Гол", owner_name: "Маша",
  position: "CB", rating: 71, value: 4_500_000, club_name: "Ночные Совы", club_owner: "Dev",
};

const club: ManagerClub = {
  id: 1, name: "Ночные Совы", formation: "4-3-3", style: "possession", budget: 2_500_000, division: 2, division_name: "Дивизион 2",
  playing: false, seasons_played: 0, titles: 0, best_division: 2,
  base: { level: 5, stadium: 3, marketing: 2, shop: 0, matchday_pct: 4, discount_pct: 0, capacity: 9000 },
  next_grant: { grant: 2_000_000, bonus: 300_000, bonus_raw: 300_000, total: 2_300_000 }, ticket_per_home_match: 62_000,
  squad: {
    rating: 60, kids: 8, bench: [], formation: "4-3-3",
    xi: [
      { slot: "GK", kind: "kid", name: "А. Новиков", position: "GK", rating: 54 },
      { slot: "DEF2", kind: "live", name: "Мария Гол", position: "CB", rating: 71, user_id: 2, owner_name: "Маша", value: 4_500_000 },
      { slot: "MID2", kind: "academy", name: "Свой Воспитанник", position: "CM", rating: 64, value: 1_000_000, photo: "players/kid.webp" },
      { slot: "FWD2", kind: "own", name: "Виктор", position: "ST", rating: 74, user_id: 1, value: 9_800_000 },
    ],
  },
  contracts: [contract], offers_sent: [], incoming: [], npcs: [], wages_per_season: 600_000, squad_value: 15_300_000, live_count: 1,
  next_match: null,
  academy_card_id: null, academy_options: [{ card_id: 9, name: "Свой Воспитанник", position: "CM", rating: 64 }],
  look: LOOK, owned_cosmetics: [], stadium_name: null, pro: false, pro_until: null, merch: { sold: 0, eur_season: 0, cap_eur: 15_000_000 },
};

const league: ManagerLeague = {
  id: 3, season_key: "2026-W43", division: 2, division_name: "Дивизион 2", status: "active", rounds_played: 3, total_rounds: 15,
  next_round_at: "2026-10-22T10:00:00Z", rounds: [], players: [], champion: null,
  table: [
    { team_index: 0, played: 3, won: 3, drawn: 0, lost: 0, gf: 6, ga: 1, points: 9, name: "Ястребы", owner_name: "Коля", club_id: 7,
      is_mine: false, is_live: true, zone: "up" },
    { team_index: 1, played: 3, won: 2, drawn: 0, lost: 1, gf: 4, ga: 2, points: 6, name: "Ночные Совы", owner_name: "Dev", club_id: 1,
      is_mine: true, is_live: true, zone: "up" },
  ],
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ManagerPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("eur", () => {
  it("formats club money like Transfermarkt", () => {
    expect(eur(3_500_000)).toBe("€3,5 млн");
    expect(eur(160_000_000)).toBe("€160 млн");
    expect(eur(12_000_000)).toBe("€12 млн");
    expect(eur(150_000)).toBe("€150 тыс");
  });
});

describe("ManagerPage", () => {
  beforeEach(() => {
    [fetchManager, fetchManagerMarket, fetchManagerCatalog, fetchManagerPopular, fetchManagerClubCard, foundManagerClub, offerManagerContract,
      respondManagerOffer, signManagerNpc, buyManagerCosmetic, buyManagerMerch, updateManagerClub].forEach((f) => f.mockReset());
    fetchManagerPopular.mockResolvedValue({ clubs: [] });
  });

  it("founds a club for the configured price", async () => {
    fetchManager.mockResolvedValue(base);
    foundManagerClub.mockResolvedValue({ ...base, club });
    renderPage();
    expect(await screen.findByText("Трансферное окно открыто")).toBeInTheDocument();
    const button = await screen.findByRole("button", { name: /Основать за 1/ });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText("Название клуба"), { target: { value: "Ночные Совы" } });
    fireEvent.click(button);
    await waitFor(() => expect(foundManagerClub).toHaveBeenCalledWith("Ночные Совы"));
    expect(await screen.findByTestId("pitch")).toBeInTheDocument();
  });

  it("shows the pitch with own, academy, live players, values in euros and the budget breakdown", async () => {
    fetchManager.mockResolvedValue({ ...base, club });
    renderPage();
    const pitch = await screen.findByTestId("pitch");
    expect(pitch).toHaveTextContent("Мой игрок");
    expect(pitch).toHaveTextContent("Академия");
    expect(pitch).toHaveTextContent("€9,8 млн");
    expect(screen.getByText(/8 мест пустует/)).toBeInTheDocument();
    expect(screen.getByText(/Бюджет на сезон: €2,3 млн/)).toBeInTheDocument();
  });

  it("buys a player of another club with a transfer fee", async () => {
    fetchManager.mockResolvedValue({ ...base, club: { ...club, budget: 30_000_000 } });
    fetchManagerMarket.mockResolvedValue({
      players: [{
        user_id: 9, player_name: "Пётр Сейв", owner_name: "Петя", position: "GK", rating: 70, level: 5, value: 16_000, trend_pct: 5,
        is_friend: false, looking: false, offered: false, club: { name: "Ястребы", seasons_left: 2, on_loan: false, division: 2 },
      }],
    });
    offerManagerContract.mockResolvedValue({ ...base, club });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Трансферы" }));
    expect(await screen.findByText("▲ +5%")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: "Купить или арендовать" }));
    fireEvent.click(screen.getByRole("button", { name: "2 сезона" }));
    fireEvent.click(screen.getByRole("button", { name: "Отправить предложение" }));
    await waitFor(() => expect(offerManagerContract).toHaveBeenCalledWith({ user_id: 9, wage: 1000, seasons: 2, fee: 16_000, kind: "transfer" }));
  });

  it("loans a catalog footballer", async () => {
    fetchManager.mockResolvedValue({ ...base, club });
    fetchManagerCatalog.mockResolvedValue({
      players: [{
        player_id: 77, name: "Каталожный Форвард", position: "ST", rating: 68, club: "ФК", country: "", value: 2_400_000, wage: 240_000,
        wage_now: 240_000, loan_fee: 480_000, sell_back: 1_200_000, taken_by: null, mine: false,
      }],
    });
    signManagerNpc.mockResolvedValue({ ...base, club });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Трансферы" }));
    fireEvent.click(screen.getByRole("button", { name: /Футболисты/ }));
    fireEvent.click(await screen.findByText("Каталожный Форвард"));
    fireEvent.click(screen.getByRole("button", { name: /Аренда · €480 тыс/ }));
    await waitFor(() => expect(signManagerNpc).toHaveBeenCalledWith(77, "loan", 1));
  });

  it("shows the league with zones and the pyramid, opens a club card and buys its merch", async () => {
    fetchManager.mockResolvedValue({ ...base, club, league });
    const card = {
      id: 7, name: "Ястребы", owner_name: "Коля", division: 2, division_name: "Дивизион 2", titles: 1, seasons_played: 3, look: LOOK,
      stadium_name: "Ястреб Арена", pro: true, rating: 66, fans: 4, is_mine: false, xi: [],
      merch: [{ code: "scarf", name: "Шарф", emoji: "🧣", coins: 200, eur: 300_000, bought: false }],
    };
    fetchManagerClubCard.mockResolvedValue(card);
    buyManagerMerch.mockResolvedValue({ ...card, fans: 5, merch: [{ ...card.merch[0], bought: true }] });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Лига" }));
    expect(screen.getByTestId("pyramid")).toHaveTextContent("Дивизион 2 · ты");
    fireEvent.click(screen.getByText(/👤 Ястребы/));
    expect(await screen.findByText("🏟 Ястреб Арена")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Шарф/ }));
    await waitFor(() => expect(buyManagerMerch).toHaveBeenCalledWith(7, "scarf"));
  });

  it("buys a style item for coins", async () => {
    fetchManager.mockResolvedValue({ ...base, club });
    buyManagerCosmetic.mockResolvedValue({ ...base, club });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Стиль" }));
    expect(screen.getByTestId("manager-style")).toHaveTextContent("Менеджер Pro");
    fireEvent.click(screen.getByRole("button", { name: /1500/ }));
    await waitFor(() => expect(buyManagerCosmetic).toHaveBeenCalledWith("symbol_lion"));
  });

  it("shows my value with the trend and accepts an incoming offer as a player", async () => {
    const offer: ManagerContract = { ...contract, id: 7, status: "offered", player_agreed: false, club_name: "Ястребы", club_owner: "Коля" };
    fetchManager.mockResolvedValue({ ...base, offers: [offer] });
    respondManagerOffer.mockResolvedValue({ ...base, contract: { ...offer, status: "active" } });
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: /Я игрок/ }));
    expect(screen.getByTestId("my-value")).toHaveTextContent("€3,5 млн");
    expect(screen.getByTestId("my-value")).toHaveTextContent("▲ +12%");
    fireEvent.click(screen.getByRole("button", { name: "Согласен" }));
    await waitFor(() => expect(respondManagerOffer).toHaveBeenCalledWith(7, true));
    expect(await screen.findByText("Менеджер Коля")).toBeInTheDocument();
  });

  it("picks a style and a formation and shows the next opponent with the style edge", async () => {
    fetchManager.mockResolvedValue({
      ...base,
      club: {
        ...club,
        next_match: {
          opponent: "Ястребы", owner_name: "Коля", rating: 66, home: true, at: null, style: "defensive", formation: "5-3-2",
          edge: "win", mods: { FWD: 10, MID: 6, DEF: 0, GK: 0 },
        },
      },
    });
    updateManagerClub.mockResolvedValue({ ...base, club: { ...club, style: "attacking" } });
    renderPage();
    const panel = await screen.findByTestId("tactics");
    expect(panel).toHaveTextContent("твой стиль бьёт их (+4% ко всем)");
    expect(panel).toHaveTextContent("Атака +10%");
    fireEvent.click(screen.getByRole("button", { name: /⚔️ Атака/ }));
    await waitFor(() => expect(updateManagerClub.mock.calls[0]?.[0]).toEqual({ style: "attacking" }));
    fireEvent.click(screen.getByRole("button", { name: /3-4-3/ }));
    await waitFor(() => expect(updateManagerClub.mock.calls.map((c) => c[0])).toContainEqual({ formation: "3-4-3" }));
    fireEvent.click(screen.getByRole("button", { name: "Как считается матч?" }));
    expect(screen.getByTestId("match-help")).toHaveTextContent("Как считается матч");
  });

  it("draws faces on the pitch: card photos and initials of academy kids", async () => {
    fetchManager.mockResolvedValue({ ...base, club });
    const { container } = renderPage();
    await screen.findByTestId("pitch");
    expect(container.querySelector('img[src$="players/kid.webp"]')).not.toBeNull();
  });
});
