import { useState } from "react";

import { uiArt } from "@/components/magic/art/pngArt";
import CreatureCard from "@/components/magic/CreatureCard";
import { MagicPackOffer } from "@/components/magic/MagicPack";
import { RACE } from "@/components/magic/magicMeta";
import type { MagicHub } from "@/types";

/** Creature cards: the «Магический пак» on top, then the collection the army is built from. */
export function MagicCollection({ hub }: { hub: MagicHub }) {
  const [race, setRace] = useState<string>("all");
  const all = hub.creatures ?? [];
  const shown = race === "all" ? all : all.filter((c) => c.faction === race);
  const total = all.reduce((s, c) => s + c.fighters, 0);
  return (
    <>
      <MagicPackOffer hub={hub} />
      <section className="rounded-3xl bg-bg-surface p-3">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-xs font-bold text-ink-chalk">🃏 Коллекция существ</p>
          <span className="font-mono text-micro text-ink-mist">{all.length} видов · {total} бойцов</span>
        </div>
        <div className="mb-2 grid grid-cols-4 gap-1">
          {[["all", "Все"], ["dawn", RACE.dawn], ["ash", RACE.ash], ["wild", RACE.wild]].map(([k, label]) => (
            <button key={k} onClick={() => setRace(k)}
              className={`flex items-center justify-center gap-1 rounded-full py-1 text-micro font-bold active:scale-95 ${race === k ? "bg-amber-400 text-black" : "bg-white/10 text-ink-mist"}`}>
              {uiArt(`emblem_${k}`) && <img src={uiArt(`emblem_${k}`)!} alt="" className="h-4 w-4 object-contain" />}{label}
            </button>
          ))}
        </div>
        {shown.length === 0 ? (
          <p className="py-3 text-center text-caption text-ink-mist">Здесь пока пусто — открой магический пак.</p>
        ) : (
          <div className="grid grid-cols-4 gap-1.5">
            {shown.map((c) => <CreatureCard key={c.unit} c={c} />)}
          </div>
        )}
        <p className="mt-2 text-micro text-ink-mist-dim">
          Армия собирается из любых существ коллекции — любой расы. Раса героя даёт только заклинания.
        </p>
      </section>
    </>
  );
}
