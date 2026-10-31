import { describe, expect, it } from "vitest";

import { cardHalloweenSkin, pumpkinsWord, timeLeft } from "@/lib/halloween";

describe("halloween helpers", () => {
  it("declines pumpkins", () => {
    expect(pumpkinsWord(1)).toBe("тыква");
    expect(pumpkinsWord(3)).toBe("тыквы");
    expect(pumpkinsWord(5)).toBe("тыкв");
    expect(pumpkinsWord(11)).toBe("тыкв");
    expect(pumpkinsWord(22)).toBe("тыквы");
  });

  it("formats the time left", () => {
    const now = Date.parse("2026-10-31T12:00:00Z");
    expect(timeLeft("2026-11-02T15:30:00Z", now)).toBe("2 д 3 ч");
    expect(timeLeft("2026-10-31T13:05:00Z", now)).toBe("1 ч 5 мин");
    expect(timeLeft("2026-10-31T11:00:00Z", now)).toBe("меньше минуты");
  });

  it("picks the collection skin, else the zombie trick", () => {
    expect(cardHalloweenSkin({ id: 1, collection_skin: "vampire" }, 1)).toBe("vampire");
    expect(cardHalloweenSkin({ id: 2, collection_skin: null }, 2)).toBe("zombie");
    expect(cardHalloweenSkin({ id: 3 }, 2)).toBeNull();
    expect(cardHalloweenSkin({ id: 3 }, null)).toBeNull();
  });
});
