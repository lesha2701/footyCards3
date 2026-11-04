import { useState } from "react";
import { useNavigate } from "react-router-dom";

import AttackRun from "@/components/oneOnOne/AttackRun";
import { TEAM_KINDS, createTeamEpisode, replayTeam, type TeamKind } from "@/lib/oneOnOne/team";
import type { OneOnOneOutcome, OneOnOneResult } from "@/types";

const TITLE: Record<TeamKind, string> = {
  two_v_one: "2 на 1",
  three_v_two: "3 на 2",
  through_ball: "Пас в разрез",
  cross: "Навес / прострел",
};

const newSeed = () => Math.floor(Math.random() * 2147483646) + 1;

/** Dev only: the team episodes played against the local engine, no server,
 * no rewards. Their real home is «Ответка». */
export default function TeamEpisodesLabPage() {
  const navigate = useNavigate();
  const [kind, setKind] = useState<TeamKind | null>(null);
  const [seed, setSeed] = useState(newSeed);
  const [results, setResults] = useState<OneOnOneOutcome[]>([]);

  if (!kind) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <p className="font-display text-xl font-bold text-ink-chalk">Новые эпизоды</p>
        {TEAM_KINDS.map((k) => (
          <button key={k} type="button" onClick={() => setKind(k)} className="rounded-2xl bg-accent px-5 py-3 font-semibold text-black">
            {TITLE[k]}
          </button>
        ))}
      </div>
    );
  }
  return (
    <AttackRun
      seed={seed}
      kind={kind}
      index={results.length % 5}
      total={5}
      rating={80}
      name={TITLE[kind]}
      coins={0}
      results={results.slice(-(results.length % 5 || 5))}
      nextLabel="Ещё раз"
      submit={async (timeline) => {
        const end = replayTeam(createTeamEpisode(kind, seed, 80), timeline);
        const r: OneOnOneResult = {
          outcome: end.outcome, bonuses: [], feint: end.feint, coins_this_attack: 0, total_coins: 0, is_finished: false, next_attack: null,
        };
        return r;
      }}
      onBack={() => (kind ? setKind(null) : navigate("/play"))}
      onFeint={() => undefined}
      onResult={(r) => setResults((p) => [...p, r.outcome])}
      onNext={() => setSeed(newSeed())}
    />
  );
}
