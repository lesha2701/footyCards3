import { describe, expect, it } from "vitest";

import type { UserCard } from "@/types";

import { compareRows } from "./cardCompare";

const card = (rating: number, rarity: string, extra: Partial<UserCard> = {}) =>
  ({ player: { rating, attack_rating: rating, defense_rating: 50, rarity }, stars: 0, ...extra }) as unknown as UserCard;

describe("compareRows", () => {
  it("marks the better side on every line", () => {
    const rows = Object.fromEntries(compareRows(card(88, "epic", { stars: 2 }), card(91, "legendary", { finish: "gold" })).map((r) => [r.label, r]));
    expect(rows["Рейтинг"].win).toBe("b");
    expect(rows["Защита"].win).toBeNull();
    expect(rows["Звёзды"].win).toBe("a");
    expect(rows["Редкость"].win).toBe("b");
    expect(rows["Версия"].win).toBe("b");
  });
});
