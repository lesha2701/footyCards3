import { describe, expect, it } from "vitest";

import { parseStartLink } from "@/lib/startLink";

describe("parseStartLink", () => {
  it("opens the penalty shootout and keeps the channel's label", () => {
    expect(parseStartLink("penalty_vans")).toEqual({ source: "penalty_vans", path: "/play/penalty/3d" });
    expect(parseStartLink("penalty")).toEqual({ source: "penalty", path: "/play/penalty/3d" });
  });

  it("keeps a label without a target", () => {
    expect(parseStartLink("ad_meta")).toEqual({ source: "ad_meta", path: undefined });
  });

  it("ignores anything outside Telegram's alphabet", () => {
    expect(parseStartLink("../admin")).toEqual({});
    expect(parseStartLink(null)).toEqual({});
  });
});
