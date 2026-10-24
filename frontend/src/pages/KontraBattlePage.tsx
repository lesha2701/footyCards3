import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchKontraBattle, kontraAct, kontraAuto, kontraForfeit } from "@/api/kontra";
import { fetchMyProfile } from "@/api/profile";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import { IconChevronLeft, IconCoin } from "@/components/icons";
import FighterCard from "@/components/kontra/FighterCard";
import { describeEvent, turnOrder } from "@/components/kontra/kontraMeta";
import { kontraBossArt } from "@/lib/bossArt";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { KontraBattle, KontraEvent, KontraUnit } from "@/types";

const ALLY_TARGET = new Set(["save", "through_ball"]);
const SHOWN = new Set(["hit", "miss", "heal", "down", "stunned", "passive", "tick"]);
const fmt = (n: number) => n.toLocaleString("ru-RU");

type Shown = Record<string, { hp: number; alive: boolean }>;

function snapshot(units: KontraUnit[]): Shown {
  return Object.fromEntries(units.map((u) => [u.id, { hp: u.hp, alive: u.alive }]));
}

export default function KontraBattlePage() {
  const { battleId } = useParams();
  const id = Number(battleId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [battle, setBattle] = useState<KontraBattle | null>(null);
  const [shown, setShown] = useState<Shown>({});
  const [queue, setQueue] = useState<KontraEvent[]>([]);
  const [ticker, setTicker] = useState<string | null>(null);
  const [flash, setFlash] = useState<{ id: string; text: string; heal: boolean; n: number } | null>(null);
  const [speed, setSpeed] = useState<1 | 2>(1);
  const [target, setTarget] = useState<string | null>(null);
  const [allyTarget, setAllyTarget] = useState<string | null>(null);
  const [dmg, setDmg] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [confirmQuit, setConfirmQuit] = useState(false);
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const { data, isLoading, isError } = useQuery({ queryKey: ["kontra-battle", id], queryFn: () => fetchKontraBattle(id) });
  useEffect(() => {
    if (data && !battle) {
      setBattle(data);
      setShown(snapshot(data.units));
      setDmg(data.damage);
    }
  }, [data, battle]);

  const receive = (b: KontraBattle) => {
    setError(null);
    setTarget(null);
    setAllyTarget(null);
    setQueue(b.events.filter((e) => SHOWN.has(e.kind)));
    setBattle(b);
    queryClient.setQueryData(["kontra-battle", id], b);
    if (b.status === "finished") {
      for (const key of ["kontra-hub", "kontra-arena", "kontra-boss", "kontra-squad", "kontra-gear"]) queryClient.invalidateQueries({ queryKey: [key] });
      fetchMyProfile().then((p) => updateBalance(p.balance)).catch(() => undefined);
    }
  };

  // Play the events one by one: HP bars and the ticker follow the log.
  useEffect(() => {
    if (!battle) return;
    if (!queue.length) {
      setShown(snapshot(battle.units));
      setDmg(battle.damage);
      return;
    }
    const t = setTimeout(() => {
      const [e, ...rest] = queue;
      const units = new Map(battle.units.map((u) => [u.id, u]));
      const names = new Map(battle.units.flatMap((u) => u.abilities.map((a) => [a.code, a.name] as const)));
      setTicker(describeEvent(e, units, names));
      if (e.target && (e.kind === "hit" || e.kind === "heal" || e.kind === "tick" || e.kind === "down")) {
        setShown((s) => ({
          ...s,
          [e.target!]: { hp: e.hp ?? s[e.target!]?.hp ?? 0, alive: e.kind === "down" ? false : s[e.target!]?.alive ?? true },
        }));
        if (e.kind !== "down") {
          setFlash({ id: e.target, text: e.kind === "heal" ? `+${e.amount}` : `−${e.damage}`, heal: e.kind === "heal", n: e.n });
        }
        if (e.kind === "hit" && units.get(e.target)?.side === "foe") setDmg((d) => d + (e.damage ?? 0));
        if (e.kind === "hit") haptic(e.crit ? "heavy" : "light");
      }
      setQueue(rest);
    }, (queue.length > 60 ? 160 : 520) / speed);
    return () => clearTimeout(t);
  }, [queue, battle, speed]);

  useEffect(() => {
    if (battle?.status === "finished" && !queue.length) hapticNotify(battle.result === "win" ? "success" : "error");
  }, [battle?.status, battle?.result, queue.length]);

  const act = useMutation({
    mutationFn: (v: { unit: string; ability: string; target: string | null }) => kontraAct(id, battle!.version, v.unit, v.ability, v.target),
    onSuccess: receive,
    onError: (err) => { setError(formatGameError(err, "Ход не принят")); queryClient.invalidateQueries({ queryKey: ["kontra-battle", id] }); },
  });
  const auto = useMutation({ mutationFn: () => kontraAuto(id, battle!.version), onSuccess: receive, onError: (err) => setError(formatGameError(err, "Не получилось")) });
  const quit = useMutation({ mutationFn: () => kontraForfeit(id), onSuccess: receive });

  const units = useMemo(() => battle?.units ?? [], [battle]);
  if (isLoading || !battle) return isError ? <ErrorScreen message="Бой не найден" /> : <LoadingScreen />;

  const view = (u: KontraUnit) => ({ ...u, hp: shown[u.id]?.hp ?? u.hp, alive: shown[u.id]?.alive ?? u.alive });
  const mine = units.filter((u) => u.side === "me").map(view);
  const foes = units.filter((u) => u.side === "foe").map(view);
  const playing = queue.length > 0;
  const actor = battle.can_act && !playing ? units.find((u) => u.id === battle.turn_of) ?? null : null;
  const order = turnOrder(units.map(view), battle.turn_of);
  const isBoss = battle.mode === "boss";
  const finished = battle.status === "finished" && !playing;

  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(isBoss ? "/play/kontra/boss" : "/play/kontra/arena")} className="flex items-center gap-1 text-xs text-ink-mist">
          <IconChevronLeft size={16} /> {isBoss ? "Босс" : "Арена"}
        </button>
        <span className="truncate text-micro text-ink-mist">{isBoss ? `Раунд ${Math.min(battle.round, battle.max_rounds)}/${battle.max_rounds}` : battle.opponent_name}</span>
      </div>

      {!finished && <div className="flex flex-wrap items-center gap-1">
        <span className="text-micro text-ink-mist">Очередь:</span>
        {order.map((u, i) => (
          <span key={u.id} className={`rounded-full px-2 py-0.5 text-micro font-bold ${
            i === 0 ? "bg-amber-400 text-bg-base" : u.side === "foe" ? "bg-red-900/70 text-red-100" : "bg-white/10 text-ink-chalk"
          }`}>
            {u.side === "foe" && isBoss ? "Босс" : u.card?.position ?? u.name.slice(0, 3)}
          </span>
        ))}
      </div>}

      {/* The pitch: the opponent on top, the centre line, your squad below. */}
      <section className="relative rounded-3xl bg-gradient-to-b from-emerald-950 via-emerald-900/50 to-emerald-950 px-1.5 py-3 ring-1 ring-emerald-700/40">
        <span className="pointer-events-none absolute inset-x-0 top-1/2 h-px bg-white/10" aria-hidden />
        <span className="pointer-events-none absolute left-1/2 top-1/2 h-20 w-20 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/10" aria-hidden />
        <div className="relative flex flex-col gap-1">
          {isBoss ? (
            <section className="rounded-2xl bg-red-950/50 p-3 text-center ring-1 ring-red-500/40">
              {kontraBossArt(null, battle.boss_name) && (
                <motion.img
                  key={`boss-${dmg}`}
                  src={kontraBossArt(null, battle.boss_name)}
                  alt=""
                  animate={dmg ? { x: [0, -5, 5, -3, 0], filter: ["brightness(1)", "brightness(1.6)", "brightness(1)"] } : {}}
                  transition={{ duration: 0.4 }}
                  className="mx-auto mb-2 h-24 w-24 rounded-2xl object-cover ring-1 ring-red-400/30"
                />
              )}
              <p className="font-display text-base font-black text-ink-chalk">{battle.boss_name}</p>
              <p className="text-micro text-ink-mist">{battle.boss_tagline}</p>
              <motion.p key={dmg} initial={{ scale: 1.25 }} animate={{ scale: 1 }} className="mt-1 font-mono text-2xl font-black text-amber-300">
                {fmt(dmg)}
              </motion.p>
              <p className="text-micro text-ink-mist-dim">урон за попытку</p>
              {flash && foes.some((f) => f.id === flash.id) && (
                <motion.span key={flash.n} className="block font-display text-lg font-black text-red-300" initial={{ y: 6, opacity: 0 }} animate={{ y: -6, opacity: [0, 1, 0] }} transition={{ duration: 0.8 }}>
                  {flash.text}
                </motion.span>
              )}
            </section>
          ) : (
            <Row units={foes} flash={flash} onPick={(u) => setTarget(u.id)} picked={target} foe />
          )}

          <div className="flex h-9 items-center justify-center">
            <AnimatePresence mode="wait">
              {ticker && !finished && (
                <motion.p key={ticker + queue.length} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="rounded-full bg-black/50 px-3 py-1 text-center text-xs font-bold text-amber-300">
                  {ticker}
                </motion.p>
              )}
            </AnimatePresence>
          </div>

          <Row units={mine} flash={flash} active={actor?.id} onPick={(u) => setAllyTarget(u.id)} picked={allyTarget} />
        </div>
      </section>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {actor && (
        <>
          <p className="text-center text-micro text-ink-mist">
            Ходит {actor.name} · {target ? "цель выбрана" : "нажми соперника, чтобы выбрать цель"}
          </p>
          <div className="grid grid-cols-3 gap-1.5">
            {actor.abilities.map((a) => (
              <button
                key={a.code}
                onClick={() => act.mutate({ unit: actor.id, ability: a.code, target: ALLY_TARGET.has(a.code) ? allyTarget : target })}
                disabled={!a.ready || act.isPending}
                className={`rounded-xl px-1 py-2 text-xs font-bold active:scale-95 disabled:opacity-35 ${a.code === "strike" ? "bg-white/10 text-ink-chalk" : "bg-amber-400 text-bg-base"}`}
                title={a.description}
              >
                {a.name}
                {!a.ready && <span className="block text-micro font-normal">через {a.cd}</span>}
              </button>
            ))}
            {actor.passive && (
              <span className="rounded-xl bg-white/5 px-1 py-2 text-center text-micro text-ink-mist" title={actor.passive.description}>
                {actor.passive.name}<span className="block">пассивка</span>
              </span>
            )}
          </div>
        </>
      )}

      {!finished && (
        <div className="grid grid-cols-3 gap-1.5">
          <button onClick={() => auto.mutate()} disabled={battle.auto || auto.isPending || playing} className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-chalk active:scale-95 disabled:opacity-40">
            {battle.auto ? "Автобой" : "Авто"}
          </button>
          <button onClick={() => setSpeed(speed === 1 ? 2 : 1)} className={`rounded-xl py-2 text-xs font-semibold active:scale-95 ${speed === 2 ? "bg-amber-400 text-bg-base" : "bg-white/5 text-ink-chalk"}`}>
            Скорость ×{speed === 1 ? 2 : 1}
          </button>
          {playing ? (
            <button onClick={() => setQueue([])} className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-mist active:scale-95">Пропустить</button>
          ) : (
            <button onClick={() => setConfirmQuit(true)} className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-mist active:scale-95">Сдаться</button>
          )}
        </div>
      )}

      <ConfirmDialog
        open={confirmQuit}
        title="Сдаться?"
        description="Бой засчитают поражением без награды."
        confirmLabel="Сдаться"
        danger
        onConfirm={() => { setConfirmQuit(false); quit.mutate(); }}
        onCancel={() => setConfirmQuit(false)}
      />

      {finished && (
        <motion.section initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} className="rounded-3xl bg-bg-surface p-4 text-center">
          <p className="text-4xl">{isBoss ? "💥" : battle.result === "win" ? "🏆" : "😤"}</p>
          <p className="font-display text-xl font-black text-ink-chalk">
            {isBoss ? `Урон: ${fmt(battle.damage)}` : battle.result === "win" ? "Победа!" : "Поражение"}
          </p>
          <div className="mt-2 flex justify-center gap-4 text-sm font-bold">
            <span className="flex items-center gap-1 text-ink-chalk">+{battle.reward_coins} <IconCoin size={13} /></span>
            {!isBoss && (
              <span className={battle.rating_delta >= 0 ? "text-accent-green" : "text-red-400"}>
                {battle.rating_delta >= 0 ? "+" : ""}{battle.rating_delta} рейтинга
              </span>
            )}
          </div>
          {battle.gear_drop && (
            <p className="mt-2 rounded-xl bg-amber-400/10 px-3 py-2 text-xs text-amber-200">
              🎁 Выпало: {battle.gear_drop.slot_label} «{battle.gear_drop.set_name}» · {battle.gear_drop.rarity_label} (+{battle.gear_drop.pct}%)
            </p>
          )}
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button onClick={() => navigate(isBoss ? "/play/kontra/boss" : "/play/kontra/arena")} className="rounded-xl bg-amber-400 py-2.5 text-sm font-bold text-bg-base active:scale-95">
              {isBoss ? "К боссу" : "Ещё бой"}
            </button>
            <button onClick={() => navigate("/play/kontra")} className="rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">К отряду</button>
          </div>
        </motion.section>
      )}
    </div>
  );
}

function Row({ units, flash, active, onPick, picked, foe = false }: {
  units: KontraUnit[];
  flash: { id: string; text: string; heal: boolean; n: number } | null;
  active?: string;
  onPick: (u: KontraUnit) => void;
  picked: string | null;
  foe?: boolean;
}) {
  return (
    <div className="grid grid-cols-5 gap-1">
      {units.map((u, i) => (
        <div key={u.id} className="relative">
          <motion.div
            key={flash?.id === u.id ? `f${flash.n}` : u.id}
            animate={flash?.id === u.id && !flash.heal ? { x: [0, -6, 5, 0] } : {}}
            transition={{ duration: 0.3 }}
          >
            <FighterCard
              card={u.card} tier={u.tier} name={u.name} hp={u.hp} maxHp={u.max_hp} foe={foe} alive={u.alive}
              leader={u.leader} active={active === u.id} targeted={picked === u.id} effects={u.effects}
              edge={i === 0 ? "left" : i === units.length - 1 ? "right" : undefined}
              onTap={u.alive ? () => onPick(u) : undefined}
            />
          </motion.div>
          <AnimatePresence>
            {flash?.id === u.id && (
              <motion.span
                key={flash.n}
                className={`pointer-events-none absolute inset-x-0 top-1/3 z-20 text-center font-display text-lg font-black drop-shadow-[0_2px_4px_rgba(0,0,0,0.9)] ${flash.heal ? "text-emerald-300" : "text-white"}`}
                initial={{ y: 6, opacity: 0, scale: 0.8 }}
                animate={{ y: -14, opacity: [0, 1, 1, 0], scale: [0.8, 1.25, 1] }}
                transition={{ duration: 0.85 }}
              >
                {flash.text}
              </motion.span>
            )}
          </AnimatePresence>
        </div>
      ))}
    </div>
  );
}
