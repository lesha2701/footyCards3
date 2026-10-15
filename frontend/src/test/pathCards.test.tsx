import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import MatchSkillNotes from "@/components/cards/MatchSkillNotes";
import PlayerCard from "@/components/cards/PlayerCard";
import MatchPathSummary from "@/components/path/MatchPathSummary";
import PathSheet from "@/components/path/PathSheet";
import TalentBlock from "@/components/path/TalentBlock";
import { losesProgress } from "@/lib/cardStars";
import { isLegendStage, levelFraction, pathFrameClass, pathFraction, talentLevelAt } from "@/lib/pathCards";
import type { MatchEvent, PathCatalog, PathState, PathTalent, Player } from "@/types";

const talent = (over: Partial<PathTalent> = {}): PathTalent => ({
  code: "big_matches", name: "Большие матчи", emoji: "🔥", summary: "Раскрывается против сильных", kind: "static",
  level: 1, level_label: "I", enabled: true,
  levels: [
    { level: 1, label: "I", text: "+3 к рейтингу", unlocked: true, unlock_stage: "Основной" },
    { level: 2, label: "II", text: "+5 к рейтингу", unlocked: false, unlock_stage: "Легенда" },
  ],
  modes: [
    { mode: "arena", label: "Card Arena", text: "Сила соперника больше" },
    { mode: "tactico", label: "Тактико", text: null },
  ],
  ...over,
});

const catalog: PathCatalog = {
  title: "Академия", enabled: true, talent_cap: 8,
  stages: [
    { index: 0, name: "Новичок", max_rating: 65, talent_level: 0 },
    { index: 1, name: "Перспективный", max_rating: 74, talent_level: 0 },
    { index: 2, name: "Основной", max_rating: 84, talent_level: 1 },
    { index: 3, name: "Звезда", max_rating: 89, talent_level: 1 },
    { index: 4, name: "Легенда", max_rating: 96, talent_level: 2 },
  ],
  talents: [talent()],
};

const pathState: PathState = {
  card_id: 7, title: "Академия", enabled: true, player_name: "Юный Форвард", position: "ST",
  base_rating: 60, rating: 68, ceiling: 96, level: 8, max_level: 36, xp: 900, xp_into_level: 40, xp_for_next: 145,
  blocked_by_tasks: false, stage: 1, stage_name: "Перспективный", is_legend: false,
  stages: [
    { index: 0, name: "Новичок", min_rating: 60, max_rating: 65, talent_level: 0, reached: true, current: false, tasks: [] },
    {
      index: 1, name: "Перспективный", min_rating: 66, max_rating: 74, talent_level: 0, reached: false, current: true,
      tasks: [
        { id: 3, metric: "matches", label: "Сыграть матчей", target: 80, progress: 12, applies: true, done: false },
        { id: 4, metric: "wins", label: "Выиграть матчей", target: 30, progress: 30, applies: true, done: true },
      ],
    },
    { index: 2, name: "Основной", min_rating: 75, max_rating: 84, talent_level: 1, reached: false, current: false, tasks: [] },
  ],
  talent: talent({ level: 0, level_label: null, levels: talent().levels.map((l) => ({ ...l, unlocked: false })) }),
  daily: {
    arena_free_total: 10, arena_free_left: 7, bought_attempts: 2, career_total: 2, career_left: 2, ptour_total: 3,
    ptour_left: 1, coin_buys_left: 5, next_coin_price: 300, stars_buys_left: 5, next_stars_price: 3,
  },
  xp_rules: { match: 10, win: 10, draw: 3, goal: 5, assist: 3 },
  totals: {}, hunger_streak: 0, recent: [],
};

vi.mock("@/api/path", () => ({
  fetchPathCatalog: vi.fn(async () => catalog),
  fetchPathState: vi.fn(async () => pathState),
  buyPathAttempt: vi.fn(),
  createPathStarsInvoice: vi.fn(),
  fetchPathStarsInvoiceStatus: vi.fn(),
}));

function withQuery(node: ReactNode) {
  return render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>);
}

const player = {
  id: 1, display_name: "Юный Форвард", rating: 68, position: "ST", rarity: "diamond", club: "К", country: "С",
  attack_rating: 70, defense_rating: 50, image_path: null, collection_name: null, path_talent_code: "big_matches",
} as unknown as Player;

describe("path helpers", () => {
  it("computes progress fractions and talent levels by stage", () => {
    expect(pathFraction({ base_rating: 60, rating: 78, ceiling: 96 })).toBeCloseTo(0.5);
    expect(levelFraction({ xp_into_level: 50, xp_for_next: 200 })).toBe(0.25);
    expect(levelFraction({ xp_into_level: 0, xp_for_next: null })).toBe(1);
    expect(talentLevelAt(catalog, 1)).toBe(0);
    expect(talentLevelAt(catalog, 3)).toBe(1);
    expect(talentLevelAt(catalog, 4)).toBe(2);
    expect(isLegendStage(catalog, 4)).toBe(true);
    expect(isLegendStage(catalog, 3)).toBe(false);
  });

  it("gives the legend a gold frame and warns about losing path progress", () => {
    expect(pathFrameClass(4)).toContain("amber");
    expect(pathFrameClass(1)).toContain("emerald");
    expect(losesProgress({ skill_code: null, stars: 0, star_progress: 0, path_level: 3 })).toBe(true);
    expect(losesProgress({ skill_code: null, stars: 0, star_progress: 0, path_level: 0, path_stage: 0 })).toBe(false);
  });
});

describe("path card UI", () => {
  it("draws the sprout mark on a path card without hiding the rating or name", async () => {
    withQuery(<PlayerCard player={player} pathStage={2} />);
    expect(screen.getByText("68")).toBeInTheDocument();
    expect(screen.getByText("Юный Форвард")).toBeInTheDocument();
    expect(await screen.findByLabelText("Большие матчи")).toBeInTheDocument();
    expect(await screen.findByText("I")).toBeInTheDocument();
  });

  it("explains the talent, its locked level and where it does not work", () => {
    render(<TalentBlock talent={talent()} />);
    expect(screen.getByText("Большие матчи")).toBeInTheDocument();
    expect(screen.getByText(/Откроется на этапе «Легенда»/)).toBeInTheDocument();
    expect(screen.getByText("не действует")).toBeInTheDocument();
  });

  it("shows the road with the current stage, its tasks and today's attempts", async () => {
    withQuery(<PathSheet cardId={7} player={player} onClose={() => {}} />);
    expect(await screen.findByText("Ты здесь")).toBeInTheDocument();
    expect(screen.getByText("12/80")).toBeInTheDocument();
    expect(screen.getByText("Пройден ✓")).toBeInTheDocument();
    expect(screen.getByText("7/10")).toBeInTheDocument();
    expect(screen.getByText("⭐ 3")).toBeInTheDocument();
  });
});

describe("match log", () => {
  it("names a talent only on events where it changed the roll", () => {
    const event = (talents?: unknown[]): MatchEvent => ({
      minute: 70, event_type: "goal", team: "user", description: "Гол!", payload: talents ? { talents } : {},
    });
    const { container, rerender } = render(<MatchSkillNotes event={event()} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<MatchSkillNotes event={event([{ code: "second_wind", name: "Второе дыхание", emoji: "💨", level: 1, level_label: "I", player: "Юный", bonus: 3 }])} />);
    expect(screen.getByText(/Талант «Второе дыхание» I \(Юный\): \+3 к рейтингу/)).toBeInTheDocument();
  });

  it("sums up experience and explains when none was given", () => {
    render(
      <MatchPathSummary
        match={{
          reward_coins: 50,
          talent_notes: [{ code: "captain", name: "Капитан", emoji: "🎖️", level: 1, level_label: "I", player: "Кэп", bonus: 4, aura: true }],
          path_progress: [
            { user_card_id: 1, status: "awarded", xp: 25, levels: [66], stages: [1] },
            { user_card_id: 2, status: "no_attempts", xp: 0, levels: [], stages: [] },
          ],
        }}
      />,
    );
    expect(screen.getByText(/\+25 опыта/)).toBeInTheDocument();
    expect(screen.getByText(/новый этап!/)).toBeInTheDocument();
    expect(screen.getByText(/попытки на сегодня закончились/)).toBeInTheDocument();
    expect(screen.getByText(/\+4 соседям/)).toBeInTheDocument();
  });
});
