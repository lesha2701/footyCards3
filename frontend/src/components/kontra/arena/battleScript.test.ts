import { describe, expect, it } from "vitest";

import type { KontraEvent, KontraUnit } from "@/types";

import { applyImpact, planBeat, snapshot, spots, toBeats } from "./battleScript";

const ev = (n: number, kind: KontraEvent["kind"], extra: Partial<KontraEvent> = {}): KontraEvent => ({ n, kind, ...extra });

const unit = (id: string, side: "me" | "foe", role = "attacker"): KontraUnit => ({
  id, side, name: id, card: null, role, tier: "epic", hp: 500, max_hp: 1000, meter_pct: 0, alive: true, leader: false,
  effects: [], abilities: [], passive: null,
});

describe("toBeats", () => {
  it("groups an action with what it caused and splits turns, ticks and stuns", () => {
    const beats = toBeats([
      ev(1, "turn", { actor: "m1" }),
      ev(2, "ability", { actor: "m1", ability: "hat_trick", name: "Хет-трик" }),
      ev(3, "hit", { actor: "m1", target: "f1", damage: 10, hp: 90 }),
      ev(4, "hit", { actor: "m1", target: "f2", damage: 12, hp: 88 }),
      ev(5, "down", { target: "f2" }),
      ev(6, "turn", { actor: "f1" }),
      ev(7, "tick", { target: "f1", damage: 5, hp: 85 }),
      ev(8, "stunned", { target: "f3" }),
      ev(9, "heal", { actor: "m2", target: "m2", amount: 30, hp: 100 }),
      ev(10, "ability", { actor: "m1", ability: "ult_attacker", name: "Удар в девятку", ult: true }),
      ev(11, "end", { winner: "me" }),
    ]);
    expect(beats.map((b) => b.kind)).toEqual(["action", "tick", "stunned", "heal", "action"]);
    expect(beats[0].events.map((e) => e.kind)).toEqual(["hit", "hit", "down"]);
    expect(beats[4].ult).toBe(true);
  });
});

describe("planBeat", () => {
  it("lands every shot after it is launched, the knock-down after the last hit", () => {
    const [beat] = toBeats([
      ev(1, "ability", { actor: "m1", ability: "hat_trick", name: "Хет-трик" }),
      ev(2, "hit", { actor: "m1", target: "f1", damage: 10 }),
      ev(3, "hit", { actor: "m1", target: "f2", damage: 10 }),
      ev(4, "down", { target: "f2" }),
    ]);
    const plan = planBeat(beat);
    const [a, b, down] = plan.impacts;
    expect(a.launch).toBeDefined();
    expect(a.at).toBeGreaterThan(a.launch!);
    expect(b.launch!).toBeGreaterThan(a.launch!);
    expect(down.at).toBeGreaterThan(b.at);
    expect(plan.duration).toBeGreaterThan(down.at);
  });

  it("puts the ultimate's cut-in first", () => {
    const [beat] = toBeats([
      ev(1, "ability", { actor: "m1", ability: "ult_attacker", ult: true }),
      ev(2, "hit", { actor: "m1", target: "f1", damage: 99 }),
    ]);
    const plan = planBeat(beat);
    expect(plan.intro).toBeGreaterThan(0);
    expect(plan.impacts[0].launch!).toBeGreaterThanOrEqual(plan.intro);
  });
});

describe("applyImpact", () => {
  const units = [unit("m1", "me"), unit("m2", "me"), unit("f1", "foe")];

  it("starts a fresh battle from full HP and follows hits and knock-downs", () => {
    let shown = snapshot(units, true);
    expect(shown.f1.hp).toBe(1000);
    shown = applyImpact(shown, ev(1, "hit", { target: "f1", damage: 300, hp: 700 }), units, "me");
    expect(shown.f1.hp).toBe(700);
    shown = applyImpact(shown, ev(2, "down", { target: "f1" }), units, "me");
    expect(shown.f1).toMatchObject({ hp: 0, alive: false, effects: [] });
  });

  it("spreads team effects over the actor's side and cleanses negatives", () => {
    let shown = snapshot(units, true);
    shown = applyImpact(shown, ev(1, "effect", { target: "foes", effect: "blind" }), units, "foe");
    expect(shown.m1.effects.map((e) => e.code)).toEqual(["blind"]);
    shown = applyImpact(shown, ev(2, "effect", { target: "team", effect: "shield" }), units, "me");
    shown = applyImpact(shown, ev(3, "effect", { target: "team", effect: "cleanse" }), units, "me");
    expect(shown.m1.effects.map((e) => e.code)).toEqual(["shield"]);
    expect(shown.f1.effects).toEqual([]);
  });
});

describe("spots", () => {
  it("puts my squad below and the rivals above, the boss big in the middle", () => {
    const s = spots([unit("m1", "me"), unit("m2", "me"), unit("b", "foe", "boss")]);
    expect(s.m1.y).toBeGreaterThan(s.b.y);
    expect(s.b).toMatchObject({ x: 50 });
    expect(s.b.w).toBeGreaterThan(s.m1.w);
  });
});
