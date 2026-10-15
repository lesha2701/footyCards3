import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import AcademyHomeCard from "@/components/home/AcademyHomeCard";
import AcademyPage from "@/pages/AcademyPage";
import type { AcademyState } from "@/types";

const wing = (code: string, name: string, level: number, building = false) => ({
  code, name, emoji: "🏠", about: "о корпусе", level, max_level: 5, effect: level ? `эффект ${level}` : null,
  next_effect: `эффект ${level + 1}`, next_cost: 2000, next_hours: 4, building,
});

const state: AcademyState = {
  enabled: true, level: 3, max_level: 25,
  wings: [wing("scout", "Скаутский отдел", 1), wing("training", "Тренировочная база", 2, true), wing("dorm", "Интернат", 0),
    wing("staff", "Тренерский штаб", 0), wing("hall", "Зал славы", 0)] as AcademyState["wings"],
  construction: { building_code: "training", to_level: 3, ends_at: new Date(Date.now() + 3_600_000).toISOString(), remaining_seconds: 3600, speedup_stars: 2 },
  scout_report: { chance_pct: 15, consolation_coins: 200, cooldown_days: 7, available: true, next_at: null },
  effects: { scout: 1, training: 8, dorm: 0, staff: 0, hall: 0 }, showcase_slots: 3, academy_cards: 0, cards: [],
};

vi.mock("@/api/academy", () => ({
  fetchAcademy: vi.fn(async () => state),
  upgradeAcademyWing: vi.fn(), claimScoutReport: vi.fn(), createAcademySpeedupInvoice: vi.fn(), fetchAcademyInvoiceStatus: vi.fn(),
}));

function wrap(node: React.ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>);
}

describe("Академия", () => {
  it("shows the campus, the construction with a Stars speed-up and blocks a second build", async () => {
    wrap(<AcademyPage />);
    expect(await screen.findByText(/Тренировочная база → уровень 3/)).toBeInTheDocument();
    expect(screen.getByText("Ускорить ⭐ 2")).toBeEnabled();
    expect(screen.getByRole("img", { name: /уровень 3/ })).toBeInTheDocument();
    for (const button of screen.getAllByText(/Улучшить|Построить|Строится/)) expect(button.closest("button")).toBeDisabled();
    expect(screen.getByText("Получить")).toBeEnabled();
  });

  it("home tile invites to claim the scouting report", async () => {
    wrap(<AcademyHomeCard />);
    expect(await screen.findByText(/Скаутский отчёт готов/)).toBeInTheDocument();
    expect(screen.getByText(/Академия · ур\. 3/)).toBeInTheDocument();
  });
});
