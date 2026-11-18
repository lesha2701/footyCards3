import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import TodayCard from "@/components/home/TodayCard";

const claimTask = vi.fn();
let taskList: Record<string, unknown> = {};
vi.mock("@/api/tasks", () => ({ fetchTasks: () => Promise.resolve(taskList), claimTask: (id: number) => claimTask(id) }));
vi.mock("@/api/dailyRewards", () => ({
  fetchDailyRewardCalendar: () => Promise.resolve({ already_claimed_today: true, claimed_count: 3, days_in_month: 30 }),
  claimDailyReward: vi.fn(),
}));
vi.mock("@/api/freePack", () => ({
  fetchFreePackStatus: () => Promise.resolve({ available: false, available_at: null }),
  claimFreePack: vi.fn(),
}));

const task = (id: number, over: Record<string, unknown> = {}) => ({
  user_task_id: id, code: `t${id}`, name: `Задание ${id}`, is_completed: true, is_claimed: false, reward_coins: 100, ...over,
});

function wrap() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route path="/" element={<TodayCard />} />
          <Route path="/tasks" element={<p>Страница заданий</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("TodayCard tasks tile", () => {
  it("opens «Задания» instead of claiming a subscription task (the player may have left the channel)", async () => {
    // What the bot leaves after an unsubscribe: the premium task reset to "claim again".
    taskList = { regular: [task(1, { is_completed: false })], weekly: [], premium: [task(2, { is_required: true })] };
    wrap();
    fireEvent.click(await screen.findByText("Задания"));
    expect(await screen.findByText("Страница заданий")).toBeInTheDocument();
    expect(claimTask).not.toHaveBeenCalled();
    expect(screen.queryByText("Забрать всё")).toBeNull();
  });
});
