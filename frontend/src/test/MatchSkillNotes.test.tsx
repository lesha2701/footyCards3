import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MatchSkillNotes from "@/components/cards/MatchSkillNotes";
import type { MatchEvent } from "@/types";

const note = (decisive: boolean) => ({
  code: "sniper", name: "Снайпер", level: 2, level_label: "II", bonus_pp: 4, player: "Форвард", decisive,
});

const event = (skills?: unknown[]): MatchEvent => ({
  minute: 10, event_type: "goal", team: "user", description: "Гол!", payload: skills ? { skills } : {},
});

describe("MatchSkillNotes", () => {
  it("renders nothing for an event without skill notes (old matches included)", () => {
    const { container } = render(<MatchSkillNotes event={event()} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("claims the outcome only when the server marked the skill decisive", () => {
    render(<MatchSkillNotes event={event([note(true)])} />);
    expect(screen.getByText(/решил исход эпизода/)).toBeInTheDocument();
  });

  it("otherwise only says the skill was counted, with its bonus", () => {
    render(<MatchSkillNotes event={event([note(false)])} />);
    expect(screen.getByText(/учтён: 4 п\.п\./)).toBeInTheDocument();
    expect(screen.queryByText(/решил исход/)).not.toBeInTheDocument();
  });
});
