import { resolveShot } from "./aim";
import { PASS_CROSS, PASS_CUTBACK, PASS_GROUND, PASS_THROUGH, createTeamEpisode, inChipZone, initTeamState, pickMate, teamAdvance, type TeamSetup } from "./team";
import { TICK, type EpisodeEnd, type EpisodeState } from "./engine";

const run = (setup: TeamSetup, s: EpisodeState, ticks: number, hold = 1) => {
  for (let i = 0; i < ticks && !s.ended; i++) teamAdvance(setup, s, { hold, steer: 0, feint: 0, shot: null });
};

/** Runs on, plays the pass, and stops the moment the ball has left. */
function played(kind: Parameters<typeof createTeamEpisode>[0], seed: number, at: number, mode: number, power: number) {
  const setup = createTeamEpisode(kind, seed, 80);
  const s = initTeamState(setup);
  run(setup, s, at);
  const r = s.team!;
  if (s.ended) return null;
  teamAdvance(setup, s, { hold: 1, steer: 0, feint: 0, shot: null, pass: { target: pickMate(s, 0), mode, power } });
  run(setup, s, 12);
  return r.pass ? { s, r, pass: r.pass } : null;
}

describe("running back", () => {
  it("turns him round through the side and takes him away from goal", () => {
    const setup = createTeamEpisode("two_v_one", 42, 80);
    const s = initTeamState(setup);
    run(setup, s, 20);
    const z = s.z;
    run(setup, s, 60, 3);
    expect(s.ended).toBeNull();
    expect(s.hz).toBeGreaterThan(0.9);
    expect(s.z).toBeGreaterThan(z);
  });

  it("the stick pulled back looks for the man behind him", () => {
    const setup = createTeamEpisode("three_v_two", 7, 80);
    const s = initTeamState(setup);
    run(setup, s, 10);
    const r = s.team!;
    r.men[0].z = s.z + 6;
    r.men[1].z = s.z - 2;
    expect(pickMate(s, 0, true)).toBe(0);
  });
});

describe("the pass orders", () => {
  it("a through ball goes ahead of him, into the space towards goal", () => {
    const seed = 42;
    const ground = played("three_v_two", seed, 40, PASS_GROUND, 0);
    const through = played("three_v_two", seed, 40, PASS_THROUGH, 0);
    expect(ground && through).toBeTruthy();
    expect(through!.pass.toZ).toBeLessThan(ground!.pass.toZ - 3);
  });

  it("along the ground it is always weighted for him to get to", () => {
    for (let seed = 1; seed < 60; seed++) {
      const p = played("two_v_one", seed, 40, PASS_THROUGH, 0);
      if (p) expect(p.pass.reach).toBe(true);
    }
  });
});

describe("the lofted button", () => {
  it("chips in front of the goal and crosses from wide or far out", () => {
    const setup = createTeamEpisode("cross", 42, 80);
    const s = initTeamState(setup);
    expect(inChipZone(s)).toBe(false);
    s.x = 2;
    s.z = 14;
    expect(inChipZone(s)).toBe(true);
    s.x = 18;
    expect(inChipZone(s)).toBe(false);
  });

  it("a tap's chip scoops harder from further out, to the open side", () => {
    const setup = createTeamEpisode("two_v_one", 42, 80);
    const s = initTeamState(setup);
    s.kx = 2;
    s.kz = 4;
    s.x = 0;
    s.z = 9;
    const near = resolveShot(setup, s, { kind: "auto", chip: true });
    s.z = 18;
    const far = resolveShot(setup, s, { kind: "auto", chip: true });
    expect(far.dy).toBeLessThan(near.dy);
    expect(near.dx).toBeLessThan(0);
  });

  it("a cut-back reaches him sooner than the ordinary pass, on the ground", () => {
    let faster = 0;
    for (let seed = 1; seed < 40; seed++) {
      const ground = played("cross", seed, 110, PASS_GROUND, 0);
      const cut = played("cross", seed, 110, PASS_CUTBACK, 0);
      if (!ground || !cut) continue;
      expect(cut.pass.high).toBe(false);
      if (cut.pass.total < ground.pass.total) faster += 1;
    }
    expect(faster).toBeGreaterThan(0);
  });
});

describe("the cross", () => {
  it("the bar sets how high it comes and how far it carries", () => {
    const low = played("cross", 42, 90, PASS_CROSS, 10);
    const high = played("cross", 42, 90, PASS_CROSS, 90);
    expect(low && high).toBeTruthy();
    expect(low!.pass.contactY).toBeLessThan(1);
    expect(high!.pass.contactY).toBeGreaterThan(1.8);
    expect(low!.pass.total * TICK).toBeGreaterThan(0);
    const reach = (p: NonNullable<typeof low>) => Math.hypot(p.pass.toX - p.pass.fromX, p.pass.toZ - p.pass.fromZ);
    expect(reach(high!)).toBeGreaterThan(reach(low!));
  });

  it("never sends him into the net", () => {
    for (let seed = 1; seed < 120; seed++) {
      for (const power of [10, 55, 100]) {
        const setup = createTeamEpisode("cross", seed, 80);
        const s = initTeamState(setup);
        run(setup, s, 110);
        if (s.ended) continue;
        teamAdvance(setup, s, { hold: 1, steer: 0, feint: 0, shot: null, pass: { target: pickMate(s, 0), mode: PASS_CROSS, power } });
        for (let i = 0; i < 80 && !s.ended; i++) {
          run(setup, s, 1);
          if (s.team?.pass) expect(s.z).toBeGreaterThan(2.5);
        }
      }
    }
  });

  it("the keeper comes for a ball dropping in his zone and deals with it", () => {
    let claimed = 0;
    for (let seed = 1; seed < 150; seed++) {
      const setup = createTeamEpisode("cross", seed, 80);
      const s = initTeamState(setup);
      run(setup, s, 110);
      if (s.ended) continue;
      teamAdvance(setup, s, { hold: 1, steer: 0, feint: 0, shot: null, pass: { target: pickMate(s, 0), mode: PASS_CROSS, power: 100 } });
      run(setup, s, 12);
      const p = s.team?.pass;
      if (!p?.claim) continue;
      const out = s.kz;
      run(setup, s, p.total);
      const ended = s.ended as EpisodeEnd | null;
      if (ended?.outcome === "tackle" || ended?.outcome === "cleared") claimed += 1;
      expect(s.kz).toBeGreaterThanOrEqual(out - 3);
    }
    expect(claimed).toBeGreaterThan(0);
  });

  it("not struck, he brings it down and plays on", () => {
    let controlled = 0;
    for (let seed = 1; seed < 150; seed++) {
      const setup = createTeamEpisode("cross", seed, 80);
      const s = initTeamState(setup);
      run(setup, s, 90);
      if (s.ended) continue;
      teamAdvance(setup, s, { hold: 1, steer: 0, feint: 0, shot: null, pass: { target: pickMate(s, 0), mode: PASS_CROSS, power: 45 } });
      for (let i = 0; i < 160 && !s.ended && !(s.team?.passes && !s.team.pass && s.team.windup === 0); i++) run(setup, s, 1);
      if (!s.ended) {
        controlled += 1;
        expect(s.free).toBeNull();
      }
    }
    expect(controlled).toBeGreaterThan(0);
  });
});
