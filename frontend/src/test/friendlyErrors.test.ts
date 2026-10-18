import { describe, expect, it } from "vitest";

import { friendlyMessage } from "@/lib/friendlyErrors";

describe("friendly error messages", () => {
  it("keeps Russian server messages as they are", () => {
    expect(friendlyMessage("Не хватает монет на балансе", 409, true)).toBe("Не хватает монет на балансе");
  });

  it("translates known English server messages", () => {
    expect(friendlyMessage("Not enough coins", 409, true)).toBe("Не хватает монет");
    expect(friendlyMessage("Card is used in an active lineup", 409, true)).toMatch(/в составе/);
  });

  it("never shows raw axios / unknown English text", () => {
    expect(friendlyMessage(undefined, 500, false)).toMatch(/Сервер/);
    expect(friendlyMessage(undefined, undefined, false)).toMatch(/Нет связи/);
    expect(friendlyMessage("Some unexpected English", 409, true)).toMatch(/Сейчас это сделать нельзя/);
    expect(friendlyMessage("Telegram auth failed: init_data expired", 401, true)).toMatch(/перезапусти|снова открой/);
  });
});
