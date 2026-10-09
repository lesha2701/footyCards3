import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import MatchSkillSummary from "@/components/cards/MatchSkillSummary";
import { skillInactiveReason } from "@/lib/cardSkills";
import type { MatchEvent, SkillCatalogItem } from "@/types";

const dribbler = {
  code: "dribbler", engines: ["tournament"], max_positions: ["LW", "RW", "ST"],
} as unknown as SkillCatalogItem;

describe("skillInactiveReason", () => {
  it("flags a skill that doesn't act in the lineup's match engine", () => {
    expect(skillInactiveReason(dribbler, "arena", "LW", true)).toBe("Не действует в Card Arena");
    expect(skillInactiveReason(dribbler, "tournament", "LW", true)).toBeNull();
  });

  it("flags a position the skill can't fit and a disabled mechanic", () => {
    expect(skillInactiveReason(dribbler, "tournament", "CB", true)).toBe("Не подходит позиции карточки");
    expect(skillInactiveReason(dribbler, "tournament", "LW", false)).toBe("Навыки сейчас отключены");
  });
});

const note = (decisive: boolean) => ({
  code: "sniper", name: "Снайпер", level: 2, level_label: "II", bonus_pp: 4, player: "Ф", decisive,
});
const ev = (skills?: unknown[]): MatchEvent => ({
  minute: 1, event_type: "shot", team: "user", description: "", payload: skills ? { skills } : {},
});

describe("MatchSkillSummary", () => {
  it("rolls up counted and decisive skill notes", () => {
    render(<MatchSkillSummary events={[ev([note(false)]), ev([note(true)]), ev()]} />);
    expect(screen.getByText("Навыки в матче: учтены 2 раз, решили исход 1")).toBeInTheDocument();
    expect(screen.getByText(/Снайпер II/)).toBeInTheDocument();
  });

  it("renders nothing for a match without skill notes", () => {
    const { container } = render(<MatchSkillSummary events={[ev(), ev()]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
