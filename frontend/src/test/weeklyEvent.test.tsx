import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import WeeklyEventStrip from "@/components/home/WeeklyEventStrip";
import type { BingoCurrent } from "@/types";

const bingo = (patch: Partial<BingoCurrent>): BingoCurrent => ({
  is_enabled: true, week_number: 1, starts_at: null, ends_at: new Date(Date.now() + 2 * 86_400_000 + 3_600_000).toISOString(),
  goals: [
    { goal_type: "packs_opened", target_value: 5, current_value: 5, is_completed: true },
    { goal_type: "rare_drops", target_value: 3, current_value: 1, is_completed: false },
  ] as BingoCurrent["goals"],
  all_goals_completed: false, reward_coins: 500, reward_pack_id: null, reward_pack_name: null,
  reward_pack_image_path: null, has_claimed: false, ...patch,
});

const show = (b: BingoCurrent | null) => render(<MemoryRouter><WeeklyEventStrip bingo={b} /></MemoryRouter>);

describe("Событие недели", () => {
  it("shows goals done and time left", () => {
    show(bingo({}));
    expect(screen.getByText("Бинго недели")).toBeInTheDocument();
    expect(screen.getByText("Целей: 1/2")).toBeInTheDocument();
    expect(screen.getByText(/2 дн\./)).toBeInTheDocument();
  });

  it("invites to claim once every goal is done", () => {
    show(bingo({ all_goals_completed: true }));
    expect(screen.getByText("Награда готова — забрать")).toBeInTheDocument();
  });

  it("shows the player's own card and invites to claim a closed line", () => {
    const cell = (done: boolean, free = false) => ({
      metric: free ? "free" : "game:penalty", label: "x", path: null, target: 2, value: done ? 2 : 0, done, free,
    });
    const cardBase = {
      cells: [cell(true), cell(true), cell(true), cell(false), cell(true, true), cell(false), cell(false), cell(false), cell(false)],
      lines: [[0, 1, 2], [3, 4, 5], [6, 7, 8]],
      lines_done: [0], lines_claimed: [], full_done: false, full_claimed: false, line_coins: 150, full_coins: 800,
      full_pack_name: null, claimable_coins: 150, can_claim: false, community_eligible: true,
    };
    const { unmount } = show(bingo({ card: cardBase }));
    expect(screen.getByText("Рядов: 1/3 · клеток 4/9")).toBeInTheDocument();
    unmount();
    show(bingo({ card: { ...cardBase, can_claim: true } }));
    expect(screen.getByText("Награда готова — забрать")).toBeInTheDocument();
  });

  it("keeps the common reward from a player without a closed line", () => {
    const card = {
      cells: [], lines: [], lines_done: [], lines_claimed: [], full_done: false, full_claimed: false,
      line_coins: 150, full_coins: 800, full_pack_name: null, claimable_coins: 0, can_claim: false, community_eligible: false,
    };
    show(bingo({ all_goals_completed: true, card }));
    expect(screen.queryByText("Награда готова — забрать")).toBeNull();
  });

  it("is hidden while the bingo is off", () => {
    const { container } = show(bingo({ is_enabled: false }));
    expect(container).toBeEmptyDOMElement();
  });
});
