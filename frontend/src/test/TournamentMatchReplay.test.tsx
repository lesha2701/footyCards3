import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TournamentMatchReplay } from "@/components/clubs/TournamentMatchReplay";
import type { MatchEvent } from "@/types";

const events: MatchEvent[] = [
  { minute: 5, event_type: "shot", team: "a", description: "🎯 Реал бьёт — мимо ворот" },
  { minute: 20, event_type: "goal", team: "a", description: "⚽ Гол! Реал открывает счёт!" },
  { minute: 40, event_type: "save", team: "b", description: "🧤 Вратарь Барселоны спасает!" },
  { minute: 70, event_type: "goal", team: "b", description: "⚽ ГОЛ! Барселона забивает!" },
];

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe("TournamentMatchReplay", () => {
  it("reveals events one at a time in order, climbing the live score", async () => {
    render(<TournamentMatchReplay events={events} clubAName="Реал" clubBName="Барселона" scoreA={2} scoreB={2} />);

    expect(screen.getByText("0 : 0")).toBeInTheDocument();
    await vi.advanceTimersByTimeAsync(950);
    expect(screen.getByText(/Реал бьёт/)).toBeInTheDocument();
    expect(screen.getByText("0 : 0")).toBeInTheDocument();

    await vi.advanceTimersByTimeAsync(950);
    expect(screen.getByText(/Реал открывает счёт/)).toBeInTheDocument();
    expect(screen.getByText("1 : 0")).toBeInTheDocument();
  });

  it("reaches a stable end state matching the final score after all events reveal", async () => {
    render(<TournamentMatchReplay events={events} clubAName="Реал" clubBName="Барселона" scoreA={2} scoreB={2} />);
    await vi.advanceTimersByTimeAsync(950 * events.length);
    expect(screen.getByText("Матч завершён")).toBeInTheDocument();
    // The fixture only has one goal per team, so the live event-derived score
    // tops out at 1:1 — distinct from the final scoreA/scoreB props (2:2)
    // shown in "Итоговый счёт", which reflect the server-resolved result.
    expect(screen.getByText("1 : 1")).toBeInTheDocument();
    expect(screen.getByText("Итоговый счёт: 2 : 2")).toBeInTheDocument();
    // Advancing further must not throw or reveal past the end (caughtUp gates the effect's setTimeout).
    await vi.advanceTimersByTimeAsync(950 * 5);
    expect(screen.getByText("1 : 1")).toBeInTheDocument();
  });

  it("skip button jumps straight to the final state without waiting out every timer", () => {
    render(<TournamentMatchReplay events={events} clubAName="Реал" clubBName="Барселона" scoreA={2} scoreB={2} />);
    fireEvent.click(screen.getByText("Пропустить"));
    // Clicking skip settles the component straight to the caught-up final state
    // without any fake-timer advancement, proving no per-event wait was needed.
    expect(screen.getByText("Матч завершён")).toBeInTheDocument();
    expect(screen.getByText("1 : 1")).toBeInTheDocument();
  });
});
