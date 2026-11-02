import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { CareerSeason, FlankDuel, TacticsCatalog } from "@/api/career";
import { FlankDuelsCard, HalftimeDuelsPanel, PlayedDuels } from "@/components/career/FlankDuels";
import { presetOf, previewFamiliarity, samePresetAxes } from "@/lib/careerTactics";

const duel = (over: Partial<FlankDuel>): FlankDuel => ({
  attacker: "Ламин Ямаль", defender: "Нуну Мендеш", attacker_card_id: 1, defender_card_id: null,
  attacker_style: "speed", defender_style: "speed", pp: -10, verdict: "hard",
  reasons: ["известное противостояние"], record: [5, 20], flank: "right", ...over,
});

const { setCareerLineup } = vi.hoisted(() => ({ setCareerLineup: vi.fn(async () => ({})) }));

vi.mock("@/api/career", () => ({
  fetchCareerDuels: vi.fn(async () => ({
    enabled: true, opponent: "Порту", flank: "both",
    attack: [duel({}), duel({ attacker: "Рафинья", defender: "Дало", pp: 4, verdict: "easy", flank: "left", reasons: [] })],
    defence: [duel({ attacker: "Пепе", defender: "Кунде", pp: 6, verdict: "easy", flank: "left", reasons: [] })],
    centre: [duel({ attacker: "Левандовски", defender: "Отаменди", pp: 3, verdict: "easy", flank: "centre", reasons: [] })],
    hints: [{
      text: "Ламин Ямаль тяжело против Нуну Мендеш (-10 п.п.) — переведи атаки на левый фланг или сыграй через центр, либо поставь другого игрока.",
      actions: [{ kind: "flank", value: "left", label: "Атаковать: левый" }, { kind: "squad", label: "Сменить игрока" }],
    }],
  })),
  setCareerLineup,
}));

describe("Дуэли на флангах", () => {
  const season = {
    id: 1, rounds_played: 2, lineup: { FWD1: 7 }, formation: "4-3-3", mentality: "BALANCED", playstyle: "CENTRAL_PLAY",
    tactic: { direction: "wings", flank: "both" },
  } as unknown as CareerSeason;
  const onView = vi.fn();
  const onSquad = vi.fn();

  it("shows our and their duels with the verdict, the edge and a hint", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <FlankDuelsCard season={season} onView={onView} onError={vi.fn()} onSquad={onSquad} />
      </QueryClientProvider>,
    );
    expect(await screen.findByText("Дуэли на флангах")).toBeInTheDocument();
    expect(screen.getByText("😰 -10")).toBeInTheDocument();
    expect(screen.getByText("😎 +4")).toBeInTheDocument();
    expect(screen.getByText("Их атаки")).toBeInTheDocument();
    // Their attacker's easy duel is a hard one for our defender.
    expect(screen.getByText("😰 -6")).toBeInTheDocument();
    expect(screen.getByText(/переведи атаки на левый фланг/)).toBeInTheDocument();
    expect(screen.getByText("В центре")).toBeInTheDocument();
    expect(screen.getByText("Центр")).toBeInTheDocument();

    // One tap: the flank is saved with the rest of the tactic, the squad opens.
    fireEvent.click(screen.getByText("Атаковать: левый"));
    await waitFor(() => expect(setCareerLineup).toHaveBeenCalledWith({
      slots: { FWD1: 7 }, formation: "4-3-3", mentality: "BALANCED", playstyle: "CENTRAL_PLAY",
      tactic: { direction: "wings", flank: "left" }, round_index: 2,
    }));
    await waitFor(() => expect(onView).toHaveBeenCalled());
    fireEvent.click(screen.getByText("Сменить игрока"));
    expect(onSquad).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Кто кого обыгрывает"));
    expect(screen.getByText(/⚡ Скоростной/)).toBeInTheDocument();
  });

  it("after the match: who won the duels my players were in", () => {
    render(<PlayedDuels duels={[{ attacker: "Ламин Ямаль", defender: "Нуну Мендеш", attacker_wins: 1, defender_wins: 4, mine: "attack" }]} />);
    expect(screen.getByText("Ключевые дуэли")).toBeInTheDocument();
    expect(screen.getByText("1:4")).toHaveClass("text-red-400");
  });

  it("after the match: the duel stories", () => {
    render(<PlayedDuels duels={[]} stories={["Ямаль переиграл своего «палача» Мендеш: 3:1."]} />);
    expect(screen.getByText(/переиграл своего «палача»/)).toBeInTheDocument();
  });

  it("at the break: first-half duels and a one-tap flank for the orders", () => {
    const onFlank = vi.fn();
    const duels = {
      duels: [{ attacker: "Ямаль", defender: "Мендеш", attacker_wins: 0, defender_wins: 4, mine: "attack" as const }],
      hints: [{ text: "Ямаль проигрывает Мендеш 0:4 — переведи атаки на левый фланг или замени игрока.", flank: "left" as const }],
    };
    const { rerender } = render(<HalftimeDuelsPanel duels={duels} flank="both" onFlank={onFlank} />);
    expect(screen.getByText("Дуэли первого тайма")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Атаковать: левый"));
    expect(onFlank).toHaveBeenCalledWith("left");
    rerender(<HalftimeDuelsPanel duels={duels} flank="left" onFlank={onFlank} />);
    expect(screen.getByText("Фланг выбран — отдай указания")).toBeDisabled();
  });
});

describe("Фланг атак в тактике", () => {
  const catalog = {
    axes: [{ key: "direction", label: "", values: [] }, { key: "flank", label: "", values: [] }],
    presets: [{ code: "WING_PLAY", label: "Фланговая игра", tactic: { direction: "wings" } }],
    interactions: [],
  } as unknown as TacticsCatalog;

  it("a preset is still that preset down either flank", () => {
    expect(presetOf(catalog, { direction: "wings", flank: "right" })).toBe("Фланговая игра");
    expect(samePresetAxes({ direction: "wings" }, { direction: "wings", flank: "left" })).toBe(true);
    expect(samePresetAxes({ direction: "wings" }, { direction: "center", flank: "left" })).toBe(false);
  });

  it("switching the flank costs no familiarity", () => {
    expect(previewFamiliarity(10, 50, 80, "4-3-3", { direction: "wings", flank: "both" }, "4-3-3",
      { direction: "wings", flank: "right" })).toBe(10);
    expect(previewFamiliarity(10, 50, 80, "4-3-3", { direction: "wings" }, "4-3-3", { direction: "center" })).toBe(8);
  });
});
