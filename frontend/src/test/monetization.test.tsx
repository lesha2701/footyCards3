import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import LoginCalendar from "@/components/profile/LoginCalendar";
import { RewardBundleChips } from "@/components/rewards/RewardBundleView";
import { cardSkinClass, frameClass } from "@/lib/cosmetics";
import { dayRewardLabel, formatCountdown, isEmptyBundle, streakLine } from "@/lib/rewards";
import ClubPassPage from "@/pages/ClubPassPage";
import SeasonPassPage from "@/pages/SeasonPassPage";
import type { CalendarDay, ClubPass, LoginCalendar as Calendar, RewardBundle, SeasonPass } from "@/types";

const bundle = (patch: Partial<RewardBundle> = {}): RewardBundle => ({
  coins: 0, pack_id: null, pack_name: null, card_rarity: null, badge: null, cosmetic: null, ...patch,
});

function day(n: number, status: CalendarDay["status"], reward = bundle({ coins: 50 + n })): CalendarDay {
  return { day: n, date: `2026-10-${String(n).padStart(2, "0")}`, reward, status, claim_method: status === "claimed" ? "login" : null, is_big: n % 7 === 0 };
}

const calendar: Calendar = {
  month: "2026-10-01", today: "2026-10-16",
  days: Array.from({ length: 31 }, (_, i) => day(i + 1, i + 1 < 16 ? (i + 1 === 3 ? "missed" : "claimed") : i + 1 === 16 ? "today" : "future")),
  claimed_count: 14, days_in_month: 31, already_claimed_today: false,
  month_bonus: bundle({ coins: 2000, card_rarity: "legendary" }), month_bonus_claimed: false,
  catchup_coins: 150, catchup_stars: 10, catchups_left: 5, free_catchups_left: 0,
};

const api = vi.hoisted(() => ({
  catchUpDay: vi.fn(),
  claimDailyReward: vi.fn(),
  claimClubPassDaily: vi.fn(),
  setClubPassAutoRenew: vi.fn(),
}));

vi.mock("@/api/dailyRewards", () => ({
  fetchDailyRewardCalendar: async () => calendar,
  claimDailyReward: api.claimDailyReward,
  catchUpDay: api.catchUpDay,
  createCatchUpStarsInvoice: vi.fn(),
}));

const clubPass: ClubPass = {
  enabled: true, stars_price: 199, is_active: false, expires_at: null, auto_renew: false, daily_claimed_today: false,
  perks: {
    daily_coins: 150, daily_pack: bundle({ pack_id: 1, pack_name: "Базовый" }), extra_rewarded_attempts: 2, frame: null, badge: null,
    ad_free: true, status: 50, monthly_bonus: bundle({ coins: 2000, card_rarity: "epic" }), season_xp_bonus_pct: 50, free_catchups: 3,
  },
};
let clubPassState = clubPass;

const season: SeasonPass = {
  enabled: true, season_id: 1, name: "Осень", starts_at: "2026-10-01T00:00:00Z", ends_at: "2026-11-01T00:00:00Z",
  premium_stars: 399, xp: 40, level: 1, next_level_xp: 100, is_premium: false, claimable: 1, locked_premium: 1,
  xp_per_game: 10, xp_per_daily_claim: 25, premium_status: 30,
  levels: [
    { level: 1, xp_required: 10, reached: true, free: bundle({ coins: 100 }), premium: bundle({ coins: 300 }), free_claimed: false, premium_claimed: false },
    { level: 2, xp_required: 100, reached: false, free: bundle({ coins: 200 }), premium: bundle({ card_rarity: "epic" }), free_claimed: false, premium_claimed: false },
  ],
};

vi.mock("@/api/monetization", () => ({
  fetchClubPass: async () => clubPassState,
  createClubPassInvoice: vi.fn(),
  claimClubPassDaily: api.claimClubPassDaily,
  setClubPassAutoRenew: api.setClubPassAutoRenew,
  fetchSeasonPass: async () => season,
  claimSeasonReward: vi.fn(),
  createSeasonPassInvoice: vi.fn(),
}));

function wrap(node: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter>{node}</MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("reward helpers", () => {
  it("labels a reward slot and the calendar line", () => {
    expect(dayRewardLabel(bundle({ coins: 85 }))).toBe("85 монет");
    expect(dayRewardLabel(bundle({ coins: 300, pack_name: "Базовый" }))).toBe("300 монет + пак «Базовый»");
    expect(streakLine(calendar, true)).toBe("14/31 дней · сегодня: 66 монет");
    expect(streakLine({ ...calendar, already_claimed_today: true }, false)).toBe("Забрано · завтра: 67 монет");
    expect(isEmptyBundle(bundle())).toBe(true);
    expect(formatCountdown(3_723_000)).toBe("01:02:03");
    expect(formatCountdown(-5)).toBe("00:00:00");
  });

  it("knows every cosmetic style the migration seeds", () => {
    for (const key of ["gold", "neon", "fire", "club_pass", "starter"]) expect(frameClass(key)).toBeTruthy();
    for (const key of ["chrome", "holo"]) expect(cardSkinClass(key)).toBeTruthy();
    expect(frameClass(null)).toBeNull();
  });

  it("shows what is inside a bundle", () => {
    render(<RewardBundleChips bundle={bundle({ coins: 2000, card_rarity: "legendary", pack_name: "Премиум" })} />);
    expect(screen.getByText("2000")).toBeInTheDocument();
    expect(screen.getByText("Пак «Премиум»")).toBeInTheDocument();
    expect(screen.getByText(/Карточка: легенд/i)).toBeInTheDocument();
  });
});

describe("login calendar", () => {
  it("renders the month and offers a catch-up for a missed day", async () => {
    api.catchUpDay.mockResolvedValue({ day: 3, granted: { coins: 53, pack_name: null, cards: [], badge: null, cosmetic: null, new_balance: 1 }, month_bonus: null, new_balance: 1 });
    wrap(<LoginCalendar />);
    expect(await screen.findByText("Календарь наград")).toBeInTheDocument();
    expect(screen.getByText("Забрать награду")).toBeEnabled();
    fireEvent.click(screen.getByLabelText("3 число"));
    expect(screen.getByText("Пропущено")).toBeInTheDocument();
    expect(screen.getByText(/Догнать за 10 ⭐/)).toBeInTheDocument();
    fireEvent.click(screen.getByText(/Догнать за 150/));
    await waitFor(() => expect(api.catchUpDay).toHaveBeenCalledWith("2026-10-03"));
    expect(await screen.findByText("Награда получена!")).toBeInTheDocument();
  });
});

describe("club pass page", () => {
  it("lists the perks and the price before buying", async () => {
    clubPassState = clubPass;
    wrap(<ClubPassPage />);
    expect(await screen.findByText("Оформить за 199 ⭐ / месяц")).toBeInTheDocument();
    expect(screen.getByText("+150 монет каждый день")).toBeInTheDocument();
    expect(screen.getByText("Бесплатный пак «Базовый» каждый день")).toBeInTheDocument();
    expect(screen.getByText(/Сразу и каждый месяц: 2000 монет \+ эпическая карточка/i)).toBeInTheDocument();
    expect(screen.getByText("+50% опыта сезонного пропуска")).toBeInTheDocument();
    expect(screen.getByText("+50 статуса «Моему игроку», пока абонемент активен")).toBeInTheDocument();
    expect(screen.getByText(/Звёзды не выводятся/)).toBeInTheDocument();
  });

  it("lets a subscriber claim the daily bonus and turn auto-renew off", async () => {
    clubPassState = { ...clubPass, is_active: true, auto_renew: true, expires_at: "2026-11-15T00:00:00Z" };
    api.claimClubPassDaily.mockResolvedValue({ coins: 150, pack_name: null, cards: [], badge: null, cosmetic: null, new_balance: 9 });
    api.setClubPassAutoRenew.mockResolvedValue({ ...clubPassState, auto_renew: false });
    wrap(<ClubPassPage />);
    fireEvent.click(await screen.findByText("Забрать ежедневный бонус"));
    await waitFor(() => expect(api.claimClubPassDaily).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Отключить автопродление"));
    await waitFor(() => expect(api.setClubPassAutoRenew).toHaveBeenCalledWith(false));
  });
});

describe("season pass page", () => {
  it("shows earned-but-locked premium rewards with the price", async () => {
    wrap(<SeasonPassPage />);
    expect(await screen.findByText("Открыть за 399 ⭐")).toBeInTheDocument();
    expect(screen.getByText(/Уже заработано премиум-наград: 1/)).toBeInTheDocument();
    expect(screen.getAllByText("Пропуск").length).toBe(2);
    expect(screen.getAllByText("Забрать")).toHaveLength(1);
  });
});
