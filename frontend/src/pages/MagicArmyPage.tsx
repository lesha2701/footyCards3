import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { autoMagicArmy, fetchMagicArmy, saveMagicArmy } from "@/api/magic";
import { Skeleton } from "@/components/common/Skeleton";
import { IconChevronLeft } from "@/components/icons";
import { CaptainsPanel, GuardPanel } from "@/components/magic/CaptainsGuard";
import StackToken from "@/components/magic/StackToken";
import { pngArt, uiArt } from "@/components/magic/art/pngArt";
import { LossWarning } from "@/components/magic/MagicLosses";
import { ROMAN } from "@/components/magic/magicMeta";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { hapticSelection } from "@/lib/telegram";
import { usePersistentState } from "@/lib/usePersistentState";
import type { MagicArmy, MagicArmyPick, MagicCaptain, MagicHeroClassCode, MagicModeCode } from "@/types";

const RACE_LABEL: Record<string, string> = { dawn: "Рассвет", ash: "Пепел", wild: "Дикие" };
const RACE_TINT: Record<string, string> = {
  dawn: "from-sky-500/20 ring-sky-300/30", ash: "from-red-600/20 ring-red-400/30", wild: "from-lime-500/15 ring-lime-300/30",
};
const POS_TRAIT: Record<string, string> = {
  ST: "бьёт сильнее", CF: "бьёт сильнее", LW: "бьёт сильнее", RW: "бьёт сильнее",
  CB: "крепче", LB: "крепче", RB: "крепче", GK: "отвечает на каждый удар",
};

function Photo({ path, size = 28 }: { path?: string | null; size?: number }) {
  return path
    ? <img src={staticUrl(path)} alt="" style={{ width: size, height: size }} className="shrink-0 rounded-full object-cover ring-1 ring-amber-300/60" />
    : <span style={{ width: size, height: size }} className="flex shrink-0 items-center justify-center rounded-full bg-white/10 text-xs">🎖</span>;
}

/** The army: up to five stacks of creatures from the collection (any race), each led by a
 *  footballer captain; the hero's leadership limits how strong a set marches in order. */
export default function MagicArmyPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [heroClass] = usePersistentState<MagicHeroClassCode>("magic.heroClass", "knight");
  const [runMode] = usePersistentState<MagicModeCode>("magic.mode", "quick");
  const { data: army } = useQuery({ queryKey: ["magic-army", heroClass], queryFn: () => fetchMagicArmy(heroClass) });
  const [picks, setPicks] = useState<MagicArmyPick[]>([]);
  const [captainFor, setCaptainFor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reset = (a: MagicArmy) => setPicks(a.stacks.map((s) => ({ unit: s.unit, captain: s.captain?.player_id ?? null })));
  useEffect(() => { if (army) reset(army); }, [army]);

  const done = (a: MagicArmy) => {
    queryClient.setQueryData(["magic-army", heroClass], a);
    queryClient.invalidateQueries({ queryKey: ["magic-hub"] });
    setError(null);
  };
  const save = useMutation({
    mutationFn: () => saveMagicArmy(picks, heroClass),
    onSuccess: (a) => { done(a); navigate("/play/magic"); },
    onError: (err) => setError(formatGameError(err, "Не удалось сохранить армию")),
  });
  const auto = useMutation({ mutationFn: () => autoMagicArmy(heroClass), onSuccess: (a) => { done(a); reset(a); } });

  if (!army) return <div className="flex flex-col gap-2"><Skeleton className="h-8 w-40" />{Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-14 rounded-2xl" />)}</div>;

  const creature = (unit: string) => army.creatures.find((c) => c.unit === unit);
  const captain = (id: number | null) => (id == null ? undefined : army.captains.find((c) => c.card.player_id === id));
  let used = 0;
  const rows = picks.map((p) => {
    const c = creature(p.unit);
    const cost = c ? army.costs[c.tier] : 0;
    used += cost;
    const full = Math.min(army.stack_cap, c?.fighters ?? 0);
    const unruly = used > army.leadership;
    return { p, c, cost, unruly, count: unruly ? Math.max(1, Math.floor(full / 2)) : full, cap: captain(p.captain) };
  });
  const free = army.creatures.filter((c) => !picks.some((p) => p.unit === c.unit));
  const changed = JSON.stringify(picks) !== JSON.stringify(army.stacks.map((s) => ({ unit: s.unit, captain: s.captain?.player_id ?? null })));

  const add = (unit: string) => {
    hapticSelection();
    setError(null);
    if (picks.length >= army.max_stacks) return setError(`В армии до ${army.max_stacks} отрядов — сначала убери один`);
    setPicks([...picks, { unit, captain: null }]);
  };
  const remove = (unit: string) => { hapticSelection(); setPicks(picks.filter((p) => p.unit !== unit)); };
  const move = (i: number, d: number) => {
    const j = i + d;
    if (j < 0 || j >= picks.length) return;
    hapticSelection();
    const next = [...picks];
    [next[i], next[j]] = [next[j], next[i]];
    setPicks(next);
  };
  const setCaptain = (unit: string, id: number | null) => {
    hapticSelection();
    setPicks(picks.map((p) => (p.unit === unit ? { ...p, captain: id } : p.captain === id && id != null ? { ...p, captain: null } : p)));
    setCaptainFor(null);
  };
  const pct = Math.min(100, Math.round((used / Math.max(1, army.leadership)) * 100));
  const pickingTier = captainFor ? creature(captainFor)?.tier ?? 1 : 1;
  const eligible: MagicCaptain[] = army.captains.filter((c) => c.cap >= pickingTier);

  return (
    <div className="flex flex-col gap-3 pb-36">
      <button onClick={() => navigate("/play/magic")} className="flex items-center gap-1 self-start text-xs text-ink-mist">
        <IconChevronLeft size={16} /> Мяч и Магия
      </button>
      <div>
        <h1 className="font-display text-xl font-black text-ink-chalk">Армия</h1>
        <p className="text-caption text-ink-mist">
          До {army.max_stacks} отрядов из твоей коллекции, любой расы. Каждому отряду — капитан-футболист.
          {army.auto ? " Сейчас армия собирается автоматически." : ""}
        </p>
      </div>

      <LossWarning mode={runMode} compact />

      {/* Leadership */}
      <section className="rounded-2xl bg-bg-surface p-3">
        <div className="flex items-center justify-between text-xs font-bold">
          <span className="flex items-center gap-1 text-ink-chalk">{uiArt("icon_leadership") ? <img src={uiArt("icon_leadership")!} alt="" className="h-5 w-5" /> : "👑"} Лидерство героя</span>
          <span className={used > army.leadership ? "text-red-300" : "text-amber-200"}>{used} / {army.leadership}</span>
        </div>
        <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-white/10">
          <div className={`h-full rounded-full ${used > army.leadership ? "bg-red-400" : "bg-amber-300"}`} style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-1.5 text-micro text-ink-mist-dim">
          Цена отряда: {[1, 2, 3, 4, 5].map((t) => `${ROMAN[t]} — ${army.costs[t]}`).join(" · ")}. Растёт с уровнем героя; рыцарь +3, маг −2.
          Отряды сверх лимита не слушаются и идут вполсилы — порядок важен.
        </p>
      </section>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {/* The stacks */}
      <section className="flex flex-col gap-1.5">
        <p className="text-xs font-bold uppercase tracking-wide text-ink-mist">Отряды {picks.length}/{army.max_stacks}</p>
        {rows.length === 0 && <p className="rounded-2xl bg-bg-surface p-3 text-caption text-ink-mist">Добавь существ из коллекции ниже.</p>}
        {rows.map(({ p, c, cost, unruly, count, cap }, i) => (
          <motion.div layout key={p.unit}
            className={`flex items-center gap-2 rounded-2xl px-2.5 py-2 ring-1 ${unruly ? "bg-red-500/10 ring-red-400/40" : "bg-bg-surface ring-white/5"}`}>
            <div className="flex flex-col">
              <button onClick={() => move(i, -1)} disabled={i === 0} className="px-1 text-xs text-ink-mist disabled:opacity-20">▲</button>
              <button onClick={() => move(i, 1)} disabled={i === rows.length - 1} className="px-1 text-xs text-ink-mist disabled:opacity-20">▼</button>
            </div>
            <StackToken unit={p.unit} tier={c?.tier ?? 1} count={count} image={cap?.card.image_path} size={44} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-bold text-ink-chalk">
                {c?.name ?? p.unit} <span className="font-normal text-ink-mist-dim">{ROMAN[c?.tier ?? 1]} · {RACE_LABEL[c?.faction ?? "wild"]}</span>
              </p>
              <p className={`text-micro ${unruly ? "text-red-300" : "text-ink-mist"}`}>
                {count} бойцов · 👑 {cost}{unruly ? " · не слушается" : ""}
              </p>
              <button onClick={() => setCaptainFor(p.unit)}
                className="mt-1 flex max-w-full items-center gap-1.5 rounded-full bg-white/10 py-0.5 pl-0.5 pr-2 text-micro font-bold text-ink-chalk active:scale-95">
                <Photo path={cap?.card.image_path} size={18} />
                <span className="truncate">{cap ? `${cap.card.name} · ${cap.card.rating}` : "Назначить капитана"}</span>
                {cap && <span className="rounded-full bg-amber-300 px-1 text-[8px] font-black text-black">ур. {cap.level ?? 1}</span>}
              </button>
            </div>
            <button onClick={() => remove(p.unit)} className="h-7 w-7 shrink-0 rounded-full bg-white/10 text-xs text-ink-mist active:scale-90">✕</button>
          </motion.div>
        ))}
      </section>

      <CaptainsPanel army={army} ids={picks.map((p) => p.captain).filter((x): x is number => x != null)} onArmy={done} />

      <GuardPanel army={army} onArmy={done} hardcore={runMode === "hardcore"} />

      {/* The collection */}
      <section>
        <p className="mb-1.5 text-xs font-bold uppercase tracking-wide text-ink-mist">Коллекция</p>
        {free.length === 0 ? (
          <p className="text-caption text-ink-mist">Все существа уже в армии. Больше — в магическом паке.</p>
        ) : (
          <div className="grid grid-cols-4 gap-1.5">
            {free.map((c) => {
              const img = pngArt(`creatures/${c.unit}`);
              return (
                <button key={c.unit} onClick={() => add(c.unit)}
                  className={`relative flex flex-col items-center rounded-2xl bg-gradient-to-b to-transparent p-1.5 ring-1 active:scale-95 ${RACE_TINT[c.faction] ?? RACE_TINT.wild}`}>
                  <span className="absolute left-1.5 top-1 font-mono text-[9px] font-bold text-ink-mist">{ROMAN[c.tier]}</span>
                  <span className="absolute right-1.5 top-1 font-mono text-[9px] text-amber-200">👑{army.costs[c.tier]}</span>
                  {img ? <img src={img} alt="" className="h-11 w-11 object-contain drop-shadow" /> : <span className="text-3xl">{c.emoji}</span>}
                  <span className="w-full truncate text-center text-[9px] font-bold text-ink-chalk">{c.name}</span>
                  <span className="font-mono text-[9px] text-ink-mist">×{c.fighters}</span>
                </button>
              );
            })}
          </div>
        )}
      </section>

      <div className="safe-bottom fixed inset-x-0 bottom-20 z-30 mx-auto flex max-w-md gap-2 rounded-2xl bg-bg-base/95 px-4 py-2 backdrop-blur">
        <button onClick={() => auto.mutate()} className="flex-1 rounded-xl bg-white/10 py-3 text-sm font-semibold text-ink-chalk active:scale-95">Авто</button>
        <button onClick={() => save.mutate()} disabled={!picks.length || !changed || save.isPending}
          className="flex-[2] rounded-xl bg-amber-400 py-3 text-sm font-bold text-black active:scale-95 disabled:opacity-40">
          Сохранить ({picks.length}/{army.max_stacks})
        </button>
      </div>

      {/* Captain picker */}
      <AnimatePresence>
        {captainFor && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setCaptainFor(null)}
            className="fixed inset-0 z-50 flex items-end justify-center bg-black/70">
            <motion.div initial={{ y: 60 }} animate={{ y: 0 }} exit={{ y: 60 }} onClick={(e) => e.stopPropagation()}
              className="max-h-[75vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-bg-base p-4 pb-24">
              <p className="font-display text-base font-black text-ink-chalk">Капитан отряда</p>
              <p className="mb-2 text-micro text-ink-mist">
                Отряд уровня {ROMAN[pickingTier]}: вести могут футболисты, чья редкость позволяет (обычный — до II, редкий — до III, эпический — до IV, легендарный — до V).
              </p>
              <button onClick={() => setCaptain(captainFor, null)} className="mb-1.5 w-full rounded-2xl bg-white/5 px-3 py-2 text-left text-xs text-ink-mist active:scale-[0.99]">
                Без капитана
              </button>
              {eligible.length === 0 && <p className="text-caption text-ink-mist">Нет футболистов нужной редкости.</p>}
              <div className="flex flex-col gap-1">
                {eligible.map((c) => {
                  const busy = picks.find((p) => p.captain === c.card.player_id && p.unit !== captainFor);
                  const on = picks.find((p) => p.unit === captainFor)?.captain === c.card.player_id;
                  const bonus = Math.max(-3, Math.min(5, Math.floor((c.card.rating - 75) / 4)));
                  return (
                    <button key={c.card.player_id} onClick={() => setCaptain(captainFor, c.card.player_id)}
                      className={`flex items-center gap-2.5 rounded-2xl px-3 py-2 text-left ring-1 active:scale-[0.99] ${on ? "bg-amber-300/10 ring-amber-300/60" : "bg-bg-surface ring-white/5"}`}>
                      <Photo path={c.card.image_path} size={34} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-xs font-bold text-ink-chalk">
                          {c.card.name} <span className="font-normal text-ink-mist-dim">{c.card.position} · {c.card.rating}</span>
                          {(c.level ?? 1) > 1 && <span className="ml-1 rounded-full bg-amber-300 px-1 text-[9px] font-black text-black">ур. {c.level}</span>}
                        </p>
                        <p className="text-micro text-ink-mist">
                          {bonus >= 0 ? "+" : ""}{bonus} атака и защита{POS_TRAIT[c.card.position] ? ` · ${POS_TRAIT[c.card.position]}` : ""} · до {ROMAN[c.cap]}
                          {busy ? ` · ведёт «${creature(busy.unit)?.name ?? busy.unit}»` : ""}
                        </p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
