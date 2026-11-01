import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { ManagerEvents } from "@/api/manager";
import MatchPlanPanel from "@/components/manager/MatchPlanPanel";

const fetchManagerEvents = vi.fn<() => Promise<ManagerEvents>>();
const setManagerPlan = vi.fn();
const chooseManagerEvent = vi.fn();
vi.mock("@/api/manager", () => ({
  fetchManagerEvents: () => fetchManagerEvents(),
  setManagerPlan: (...a: unknown[]) => setManagerPlan(...a),
  chooseManagerEvent: (...a: unknown[]) => chooseManagerEvent(...a),
}));

const VIEW: ManagerEvents = {
  plans: [{ code: "press", name: "Высокий прессинг", emoji: "🔥", about: "Давим", mods: { GK: 0, DEF: 0, MID: 4, FWD: 4 }, injury_x: 1.5 }],
  plan: "normal", can_plan: true, form_pct: 3,
  events: [{
    id: 7, code: "raise", title: "Звезда просит прибавку", text: "Агент звонит", emoji: "💰", status: "offered", choice: null, result: null,
    options: [
      { code: "pay", label: "Поднять зарплату", money: -120_000, fans: 0, form_pct: 3, form_rounds: 3 },
      { code: "refuse", label: "Отказать", money: 0, fans: 0, form_pct: -2, form_rounds: 2 },
    ],
  }],
  recent: [],
};

function wrap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}><MatchPlanPanel onError={() => {}} /></QueryClientProvider>);
}

describe("MatchPlanPanel", () => {
  it("shows the event's choices with their effects and the plans for the next match", async () => {
    fetchManagerEvents.mockResolvedValue(VIEW);
    setManagerPlan.mockResolvedValue({ ...VIEW, plan: "press" });
    chooseManagerEvent.mockResolvedValue({ ...VIEW, events: [] });
    wrap();
    expect(await screen.findByText("💰 Звезда просит прибавку")).toBeInTheDocument();
    expect(screen.getByText("−€120 тыс")).toBeInTheDocument();
    expect(screen.getByText("форма +3% на 3 тура")).toBeInTheDocument();
    expect(screen.getByText("форма +3%")).toBeInTheDocument();
    expect(screen.getByText("травмы ×1.5")).toBeInTheDocument();
    fireEvent.click(screen.getByText("🔥 Высокий прессинг"));
    await waitFor(() => expect(setManagerPlan).toHaveBeenCalledWith("press", expect.anything()));
    fireEvent.click(screen.getByText("Отказать"));
    await waitFor(() => expect(chooseManagerEvent).toHaveBeenCalledWith(7, "refuse"));
  });
});
