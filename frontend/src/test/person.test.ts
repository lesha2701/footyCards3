import { describe, expect, it } from "vitest";

import { collapseCopies, personKey } from "@/lib/person";
import type { UserCard } from "@/types";

const card = (id: number, playerId: number, extra: Partial<UserCard> = {}) =>
  ({ id, stars: 0, player: { id: playerId, display_name: "Неста" }, ...extra }) as unknown as UserCard;

describe("one footballer once", () => {
  it("keys a footballer like the backend: person_key, else the trimmed lower-case name", () => {
    expect(personKey({ display_name: "  Алессандро   Неста " })).toBe("алессандро неста");
    expect(personKey({ display_name: "Месси", person_key: "Лионель Месси" })).toBe("лионель месси");
    expect(personKey({ display_name: "Пётр" })).toBe(personKey({ display_name: "Петр" }));
  });

  it("collapses identical copies and keeps a preferred one", () => {
    const groups = collapseCopies([card(1, 7), card(2, 7), card(3, 7, { stars: 2 }), card(4, 8)], [2]);
    expect(groups.map((g) => [g.card.id, g.count])).toEqual([[2, 2], [3, 1], [4, 1]]);
  });
});
