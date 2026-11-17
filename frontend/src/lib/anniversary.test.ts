import { describe, expect, it } from "vitest";

import { anniversaryClaimable, anniversaryPhase, bundleLabel, communityPct, daysWord } from "@/lib/anniversary";
import type { AnniversaryState } from "@/types";

const base: AnniversaryState = {
  enabled: true, active: false, finished: false, starts_at: null, ends_at: null, claim_until: null, teaser_days: 3,
  calendar: [], calendar_claimed: 0, calendar_ready: false, day_resets_at: null, community: null,
  recap_coins: 100, recap_claimed: false, collection: null, pack_id: null,
};
const bundle = { coins: 0, pack_id: null, pack_name: null, card_rarity: null, badge: null, cosmetic: null };

describe("anniversary", () => {
  it("shows the teaser only in the last days before the start", () => {
    const now = Date.parse("2026-11-19T12:00:00Z");
    expect(anniversaryPhase({ ...base, starts_at: "2026-11-21T00:00:00Z" }, now)).toBe("teaser");
    expect(anniversaryPhase({ ...base, starts_at: "2026-11-30T00:00:00Z" }, now)).toBeNull();
    expect(anniversaryPhase({ ...base, active: true }, now)).toBe("live");
    expect(anniversaryPhase({ ...base, enabled: false, active: true }, now)).toBeNull();
  });

  it("keeps the banner after the end only while a tier waits", () => {
    const community = { total: 10, goal: 10, my_games: 3, min_games: 3, tiers: [], claimable: true };
    expect(anniversaryPhase({ ...base, finished: true, community })).toBe("leftovers");
    expect(anniversaryPhase({ ...base, finished: true, community: { ...community, claimable: false } })).toBeNull();
  });

  it("counts what can be taken now", () => {
    expect(anniversaryClaimable({ ...base, active: true, calendar_ready: true })).toBe(2);
    expect(anniversaryClaimable({ ...base, active: true, recap_claimed: true })).toBe(0);
    expect(anniversaryClaimable(base)).toBe(0);
  });

  it("caps the community progress at 100%", () => {
    expect(communityPct({ total: 12500, goal: 50000, my_games: 0, min_games: 3, tiers: [], claimable: false })).toBe(25);
    expect(communityPct({ total: 70000, goal: 50000, my_games: 0, min_games: 3, tiers: [], claimable: false })).toBe(100);
    expect(communityPct(null)).toBe(0);
  });

  it("names a reward and agrees the number", () => {
    expect(bundleLabel({ ...bundle, coins: 1500 })).toBe(`${(1500).toLocaleString("ru-RU")} 💰`);
    expect(bundleLabel({ ...bundle, card_rarity: "epic" })).toBe("эпик-карта");
    expect(bundleLabel(bundle)).toBe("сюрприз");
    expect([1, 3, 5, 11, 21, 100].map(daysWord)).toEqual(["день", "дня", "дней", "дней", "день", "дней"]);
  });
});
