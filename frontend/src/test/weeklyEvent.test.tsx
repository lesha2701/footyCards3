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

  it("is hidden while the bingo is off", () => {
    const { container } = show(bingo({ is_enabled: false }));
    expect(container).toBeEmptyDOMElement();
  });
});
