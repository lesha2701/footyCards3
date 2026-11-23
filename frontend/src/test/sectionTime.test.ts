import { describe, expect, it } from "vitest";

import { IDLE_MS, SectionClock, sectionOf } from "@/lib/sectionTime";

describe("sectionOf", () => {
  it("names a section by its first segment, games by the game", () => {
    expect(sectionOf("/")).toBe("home");
    expect(sectionOf("/packs/3/open")).toBe("packs");
    expect(sectionOf("/clubs/war")).toBe("clubs");
    expect(sectionOf("/play/penalty/matches/12")).toBe("play/penalty");
    expect(sectionOf("/play")).toBe("play");
    expect(sectionOf("/admin/analytics")).toBeNull();
    expect(sectionOf("/Ünicode")).toBe("other");
  });
});

describe("SectionClock", () => {
  it("counts visible, non-idle time per section", () => {
    const c = new SectionClock("home", 0);
    c.tick(5_000, true);
    c.setSection("play/penalty", 8_000, true);
    c.tick(13_000, true);
    expect(c.take()).toEqual({ home: 8, "play/penalty": 5 });
    expect(c.take()).toEqual({});
  });

  it("does not count a hidden page", () => {
    const c = new SectionClock("home", 0);
    c.tick(5_000, false);
    expect(c.take()).toEqual({});
  });

  it("stops counting when the player is idle and resumes on input", () => {
    const c = new SectionClock("home", 0);
    for (let t = 5_000; t <= IDLE_MS + 30_000; t += 5_000) c.tick(t, true);
    const idle = c.take().home;
    expect(idle).toBeLessThanOrEqual(IDLE_MS / 1000);
    c.input(IDLE_MS + 35_000, true); // the 5 s before the touch were idle
    c.tick(IDLE_MS + 40_000, true);
    expect(c.take()).toEqual({ home: 5 });
  });

  it("caps a late tick", () => {
    const c = new SectionClock("home", 0);
    c.input(1, true);
    c.tick(60_000, true);
    expect(c.take().home).toBe(10);
  });

  it("keeps the fractions for the next batch", () => {
    const c = new SectionClock("home", 0);
    c.tick(1_500, true);
    expect(c.take()).toEqual({ home: 1 });
    c.tick(3_000, true);
    expect(c.take()).toEqual({ home: 2 });
  });
});
