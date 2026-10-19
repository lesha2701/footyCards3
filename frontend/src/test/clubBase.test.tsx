import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import BaseHomeCard from "@/components/home/BaseHomeCard";
import { formatBuildTime, hoursLabel, upgradeBlocker } from "@/lib/clubBase";
import ClubBasePage from "@/pages/ClubBasePage";
import type { ClubBaseBuilding, ClubBaseCode, ClubBaseState } from "@/types";

const building = (code: ClubBaseCode, name: string, level: number, extra: Partial<ClubBaseBuilding> = {}): ClubBaseBuilding => ({
  code, name, emoji: "🏠", about: "о корпусе", group: ["marketing", "shop", "accounting"].includes(code) ? "finance" : "core",
  level, max_level: 5, cap_level: 2, effects: level ? [`эффект ${name} ${level}`] : [], next_effects: [`эффект ${name} ${level + 1}`],
  next_cost: 4000, next_cost_full: 4000, next_hours: 24, locked: false, building: false, ...extra,
});

const state: ClubBaseState = {
  enabled: true, level: 4, max_level: 50, academy_level: 3, academy_max_level: 25, total_level: 7,
  buildings: [
    building("hq", "Штаб-квартира", 2),
    building("stadium", "Стадион", 1, { building: true }),
    building("hotel", "Клубный отель", 0),
    building("training", "Тренировочный центр", 1),
    building("medical", "Медцентр", 0),
    building("analytics", "Аналитический центр", 0),
    building("media", "Медиацентр", 0),
    building("marketing", "Отдел маркетинга", 0),
    building("shop", "Клубный магазин", 0),
    building("accounting", "Бухгалтерия", 2, { locked: true }),
  ],
  construction: {
    owner: "base", building_code: "stadium", name: "Стадион", emoji: "🏟️", to_level: 2,
    ends_at: new Date(Date.now() + 3 * 3_600_000).toISOString(), remaining_seconds: 10_800, speedup_stars: 3,
  },
  income: { daily: 80, pending: 120, cap: 240, max_days: 3 },
  stadium: {
    level: 1, capacity: 8000, matchday_income: 20, look: { seats: "blue", roof: "none", lights: false, screen: false },
    seat_colors: ["red", "blue"], unlocks: { roof_canopy: 2, roof_full: 4, lights: 3, screen: 5 },
  },
  effects: { matchday: 20, daily: 80 },
  art: { background: null, buildings: {} },
};

vi.mock("@/api/clubBase", () => ({
  fetchClubBase: vi.fn(async () => state),
  upgradeClubBaseBuilding: vi.fn(), claimClubBaseIncome: vi.fn(), setStadiumLook: vi.fn(),
  createClubBaseSpeedupInvoice: vi.fn(), fetchClubBaseInvoiceStatus: vi.fn(),
}));

function wrap(node: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

describe("Клубная база", () => {
  it("draws the campus, shows the construction with a Stars speed-up and the income", async () => {
    wrap(<ClubBasePage />);
    expect(await screen.findByText(/Стадион → уровень 2/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /Клубная база, уровень 7/ })).toBeInTheDocument();
    expect(screen.getByText("Ускорить ⭐ 3")).toBeEnabled();
    expect(screen.getByText(/накоплено/)).toHaveTextContent("накоплено 120 из 240");
    expect(screen.getByText("Забрать")).toBeEnabled();
    expect(screen.getByRole("button", { name: "Академия" })).toBeInTheDocument();
  });

  it("a building sheet explains why it cannot be upgraded now", async () => {
    wrap(<ClubBasePage />);
    fireEvent.click(await screen.findByRole("button", { name: /Медцентр, уровень 0/ }));
    const dialog = await screen.findByRole("dialog", { name: "Медцентр" });
    expect(dialog).toHaveTextContent("Бригада занята: Стадион");
    expect(screen.getByText(/Построить ·/).closest("button")).toBeDisabled();
  });

  it("home tile invites to collect the income", async () => {
    wrap(<BaseHomeCard />);
    expect(await screen.findByText(/Доход готов: \+120/)).toBeInTheDocument();
    expect(screen.getByText(/Клубная база · ур\. 7/)).toBeInTheDocument();
  });

  it("helpers: time left, build hours and the upgrade blocker", () => {
    expect(formatBuildTime(2 * 86400 + 5 * 3600)).toBe("2 д 5 ч");
    expect(formatBuildTime(3 * 3600 + 5 * 60)).toBe("3 ч 05 мин");
    expect(formatBuildTime(249)).toBe("4:09");
    expect(hoursLabel(48)).toBe("2 д");
    expect(hoursLabel(8)).toBe("8 ч");
    const free = { ...state, construction: null };
    const accounting = state.buildings.find((b) => b.code === "accounting")!;
    expect(upgradeBlocker(free, accounting, 10_000)).toBe("Нужна штаб-квартира ур. 3");
    const hotel = state.buildings.find((b) => b.code === "hotel")!;
    expect(upgradeBlocker(free, hotel, 100)).toBe("Не хватает монет");
    expect(upgradeBlocker(free, hotel, 10_000)).toBeNull();
    expect(upgradeBlocker({ ...free, enabled: false }, hotel, 10_000)).toBe("База временно закрыта");
  });
});
