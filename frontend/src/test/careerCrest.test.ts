import { describe, expect, it } from "vitest";

import { careerCrest } from "@/lib/careerCrest";

describe("career crest", () => {
  it("is the same for the same club wherever it is shown", () => {
    expect(careerCrest("Текстильщик")).toEqual(careerCrest(" текстильщик "));
  });

  it("takes the symbol from a word in the name", () => {
    expect(careerCrest("Сокол").symbol).toBe("img_hawk");
    expect(careerCrest("Горняк").symbol).toBe("img_mountain");
    expect(careerCrest("Арсенал Озёрный").symbol).toBe("img_crossed_swords");
  });

  it("tells clubs apart", () => {
    const names = ["Сатурн", "Северсталь", "Спартак Заречье", "Dev FC", "Текстильщик", "Горняк", "Сокол", "Арсенал Озёрный"];
    const looks = new Set(names.map((n) => JSON.stringify(careerCrest(n))));
    expect(looks.size).toBe(names.length);
  });
});
