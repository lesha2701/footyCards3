import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ManagerDecisions } from "@/api/manager";
import { AchievementsPanel, BudgetPanel } from "@/components/manager/PresidentDecisions";
import { goTo, parseGo, useFocusTarget } from "@/lib/managerFocus";

const api = vi.hoisted(() => ({
  fetchManagerDecisions: vi.fn(),
  setManagerBudget: vi.fn(),
  claimManagerAchievement: vi.fn(),
}));
vi.mock("@/api/manager", () => api);

const ROW = (code: string, name: string) => ({ code, name, emoji: "💶", plan: null, spent: 0, left: null, over: false });
const DECISIONS: ManagerDecisions = {
  budget: {
    key: "2026-W47", window: true, pot: 1_000_000, plan: null, reserve: null,
    articles: [ROW("wages", "Зарплаты"), ROW("transfers", "Трансферы"), ROW("club", "Клуб")],
    suggest: { wages: 550_000, transfers: 250_000, club: 100_000 },
    tolerance_pct: 10, fans_penalty: 150, bonus_pct: 10, bonus_max: 50_000, result: null, last: null,
    acts: { me: 4, assistant: 1, total: 5, share: 80 }, hands_on: { fans: 240, money: 24_000 }, hands_on_min: 5,
  },
  achievements: [
    { code: "first_profit", emoji: "💰", name: "Первая прибыль", about: "Закрой сезон в плюс", goal: 1, progress: 1, done: true, claimed: false, reward: 40_000 },
    { code: "ipo", emoji: "📈", name: "IPO", about: "Выведи клуб на биржу", goal: 1, progress: 0, done: false, claimed: false, reward: 80_000 },
  ],
  analyst: false,
  review: null,
};

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

beforeEach(() => {
  api.fetchManagerDecisions.mockResolvedValue(DECISIONS);
  api.setManagerBudget.mockResolvedValue(DECISIONS);
  api.claimManagerAchievement.mockResolvedValue(DECISIONS);
});

describe("«Бюджет»", () => {
  it("starts the plan from the suggestion, saves it, shows hands-on", async () => {
    wrap(<BudgetPanel onError={() => {}} onTab={() => {}} />);
    fireEvent.click(await screen.findByTestId("budget-edit"));
    expect(screen.getByTestId("budget-editor")).toHaveTextContent("Резерв");
    fireEvent.click(screen.getByTestId("budget-save"));
    await waitFor(() => expect(api.setManagerBudget).toHaveBeenCalledWith({ wages: 550_000, transfers: 250_000, club: 100_000 }, expect.anything()));
    expect(screen.getByTestId("hands-on")).toHaveTextContent("Сам принял 80% решений");
  });
});

describe("«Достижения»", () => {
  it("claims a done achievement", async () => {
    wrap(<AchievementsPanel onError={() => {}} />);
    fireEvent.click(await screen.findByTestId("claim-first_profit"));
    await waitFor(() => expect(api.claimManagerAchievement).toHaveBeenCalledWith("first_profit", expect.anything()));
    expect(screen.queryByTestId("claim-ipo")).toBeNull();
  });
});

function Tab({ onOpen }: { onOpen: (t: string) => void }) {
  useFocusTarget(onOpen);
  return <div data-focus="budget">план</div>;
}

describe("managerFocus", () => {
  it("parses ?go=tab:target", () => {
    expect(parseGo("?go=office%3Abudget")).toEqual({ tab: "office", target: "budget" });
    expect(parseGo("?go=club")).toEqual({ tab: "club", target: undefined });
    expect(parseGo("")).toBeNull();
  });

  it("tells the tab to open its section and lights the target", () => {
    const onOpen = vi.fn();
    Element.prototype.scrollIntoView = vi.fn();
    render(<Tab onOpen={onOpen} />);
    act(() => goTo("budget"));
    expect(onOpen).toHaveBeenCalledWith("budget");
    expect(screen.getByText("план")).toHaveClass("ring-accent-lime");
  });
});
