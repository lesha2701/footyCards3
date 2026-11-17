import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { fetchKontraBattle, kontraAct, kontraAuto, kontraForfeit } from "@/api/kontra";
import { fetchMyProfile } from "@/api/profile";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import { IconChevronLeft, IconCoin } from "@/components/icons";
import BattleStage from "@/components/kontra/arena/BattleStage";
import { fxOf } from "@/components/kontra/arena/battleScript";
import { useBattlePlayer } from "@/components/kontra/arena/useBattlePlayer";
import { turnOrder } from "@/components/kontra/kontraMeta";
import { staticUrl } from "@/lib/api";
import { kontraBossArt } from "@/lib/bossArt";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { KontraAbility, KontraBattle, KontraUnit } from "@/types";

const ALLY_TARGET = new Set(["save", "through_ball"]);
const NO_TARGET = new Set(["hat_trick", "penalty", "conductor", "wall", "offside", "save", "medics", "ult_midfielder", "ult_defender", "ult_goalkeeper"]);
const fmt = (n: number) => n.toLocaleString("ru-RU");

/** «Контратака»: a battle on a 2.5D pitch. The server sends the event log;
 *  the stage plays it beat by beat (useBattlePlayer). On your fighter's
 *  turn: tap a rival (or an ally for «Сейв» / «Пас в разрез»), then an
 *  ability; the leader's «Суперудар» needs the squad's charge full. */
export default function KontraBattlePage() {
  const { battleId } = useParams();
  const id = Number(battleId);
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const [battle, setBattle] = useState<KontraBattle | null>(null);
  const [speed, setSpeed] = useState<1 | 2>(1);
  const [target, setTarget] = useState<string | null>(null);
  const [allyTarget, setAllyTarget] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmQuit, setConfirmQuit] = useState(false);
  const [hint, setHint] = useState<KontraAbility | null>(null);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const player = useBattlePlayer(battle, speed);

  const { data, isLoading, isError } = useQuery({ queryKey: ["kontra-battle", id], queryFn: () => fetchKontraBattle(id) });
  useEffect(() => {
    if (data && !battle) {
      setBattle(data);
      // Straight from «Начать бой»: play the opening from full HP.
      const fresh = Boolean((location.state as { play?: boolean } | null)?.play) && data.events.length > 0;
      if (fresh) {
        player.start(data, data.events, true);
        if (data.status === "finished") fetchMyProfile().then((p) => updateBalance(p.balance)).catch(() => undefined);
        navigate(location.pathname, { replace: true, state: null });
      } else {
        player.reset(data);
      }
    }
  }, [data, battle, location.state, location.pathname, navigate, player, updateBalance]);

  const receive = (b: KontraBattle) => {
    setError(null);
    setTarget(null);
    setAllyTarget(null);
    setHint(null);
    player.start(b, b.events, false);
    setBattle(b);
    queryClient.setQueryData(["kontra-battle", id], b);
    if (b.status === "finished") {
      for (const key of ["kontra-hub", "kontra-arena", "kontra-boss", "kontra-squad", "kontra-gear"]) queryClient.invalidateQueries({ queryKey: [key] });
      fetchMyProfile().then((p) => updateBalance(p.balance)).catch(() => undefined);
    }
  };

  const finished = battle?.status === "finished" && !player.busy;
  useEffect(() => {
    if (finished) hapticNotify(battle?.mode === "boss" || battle?.result === "win" ? "success" : "error");
  }, [finished, battle?.mode, battle?.result]);

  const act = useMutation({
    mutationFn: (v: { unit: string; ability: string; target: string | null }) => kontraAct(id, battle!.version, v.unit, v.ability, v.target),
    onSuccess: receive,
    onError: (err) => { setError(formatGameError(err, "Ход не принят")); queryClient.invalidateQueries({ queryKey: ["kontra-battle", id] }); },
  });
  const auto = useMutation({ mutationFn: () => kontraAuto(id, battle!.version), onSuccess: receive, onError: (err) => setError(formatGameError(err, "Не получилось")) });
  const quit = useMutation({ mutationFn: () => kontraForfeit(id), onSuccess: receive });

  const units = useMemo(() => battle?.units ?? [], [battle]);
  if (isLoading || !battle) return isError ? <ErrorScreen message="Бой не найден" /> : <LoadingScreen />;

  const isBoss = battle.mode === "boss";
  const actor = battle.can_act && !player.busy ? units.find((u) => u.id === battle.turn_of) ?? null : null;
  const aliveFoes = units.filter((u) => u.side === "foe" && (player.shown[u.id]?.alive ?? u.alive));
  const defaultTarget = aliveFoes.length ? aliveFoes.reduce((a, b) => ((player.shown[a.id]?.hp ?? a.hp) <= (player.shown[b.id]?.hp ?? b.hp) ? a : b)).id : null;
  const shownTarget = actor ? target ?? defaultTarget : null;
  const order = turnOrder(units.map((u) => ({ ...u, alive: player.shown[u.id]?.alive ?? u.alive })), battle.turn_of, 6);
  const bossArt = kontraBossArt(battle.boss_code, battle.boss_name);
  const regular = actor?.abilities.filter((a) => !a.ult) ?? [];
  const ult = actor?.abilities.find((a) => a.ult) ?? null;

  const fire = (a: KontraAbility) => {
    if (!actor || !a.ready || act.isPending) return;
    haptic("medium");
    act.mutate({ unit: actor.id, ability: a.code, target: ALLY_TARGET.has(a.code) ? allyTarget : NO_TARGET.has(a.code) ? null : shownTarget });
  };
  const tap = (u: KontraUnit) => {
    haptic("light");
    if (u.side === "foe") setTarget(u.id);
    else setAllyTarget(u.id);
  };

  return (
    <div className="-mx-1 flex flex-col gap-2">
      <div className="flex items-center justify-between px-1">
        <button onClick={() => navigate(isBoss ? "/play/kontra/boss" : "/play/kontra/arena")} className="flex items-center gap-1 text-xs text-ink-mist">
          <IconChevronLeft size={16} /> {isBoss ? "Босс" : "Арена"}
        </button>
        <span className="min-w-0 truncate text-micro font-semibold text-ink-mist">
          {battle.revenge && <span className="mr-1 rounded-full bg-red-500/20 px-1.5 py-0.5 text-red-300">⚔ Реванш</span>}
          {isBoss ? `Раунд ${Math.min(battle.round, battle.max_rounds)}/${battle.max_rounds}` : `vs ${battle.opponent_name}`}
        </span>
      </div>

      <BattleStage
        units={units} shown={player.shown} playing={player.playing} pulse={player.pulse}
        activeId={actor?.id ?? (player.playing?.beat.actor ?? null)}
        targetId={shownTarget} allyTargetId={allyTarget}
        pickFoes={Boolean(actor)} pickAllies={Boolean(actor?.abilities.some((a) => ALLY_TARGET.has(a.code) && a.ready))}
        boss={isBoss} bossArt={bossArt} onTap={tap}
      >
        {/* top bar: turn order + tactics */}
        {!finished && (
          <div className="pointer-events-none absolute inset-x-2 top-2 z-[150] flex items-start justify-between gap-2">
            <div className="flex -space-x-1.5">
              {order.map((u, i) => <OrderChip key={u.id} u={u} first={i === 0} boss={u.role === "boss"} />)}
            </div>
            {(battle.tactic_me || battle.tactic_foe) && <TacticBadge battle={battle} />}
          </div>
        )}
        {isBoss && !finished && (
          <div className="pointer-events-none absolute inset-x-0 top-[44%] z-[150] text-center">
            <motion.p key={player.dealt} initial={{ scale: 1.25 }} animate={{ scale: 1 }}
              className="font-mono text-2xl font-black text-amber-300 drop-shadow-[0_2px_0_rgba(0,0,0,0.8)]">
              {fmt(player.dealt)}
            </motion.p>
            <p className="text-[10px] font-bold uppercase tracking-widest text-white/70">урон по боссу</p>
          </div>
        )}
        {/* the squad's ultimate charge */}
        {!finished && (
          <div className="pointer-events-none absolute inset-x-3 bottom-2 z-[150] flex items-center gap-2">
            <ChargeBar value={player.charge.me} label="Суперудар" mine />
            {!isBoss && <ChargeBar value={player.charge.foe} label="соперник" />}
          </div>
        )}
        <AnimatePresence>{finished && <ResultOverlay battle={battle} isBoss={isBoss} />}</AnimatePresence>
      </BattleStage>

      {error && <p className="mx-1 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {/* the dock: whose turn and what they can do */}
      {!finished && (
        <section className="mx-1 rounded-2xl bg-bg-surface p-2.5 ring-1 ring-white/5">
          {actor ? (
            <>
              <div className="mb-2 flex items-center gap-2">
                {actor.card?.image_path && <img src={staticUrl(actor.card.image_path)} alt="" className="h-9 w-7 rounded-md object-cover object-top ring-1 ring-amber-300" />}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-bold text-ink-chalk">Ходит {actor.name}</p>
                  <p className="truncate text-micro text-ink-mist">
                    {hint ? hint.description : "Нажми соперника — цель, потом приём. Удержи приём — описание"}
                  </p>
                </div>
              </div>
              <div className={`grid gap-1.5 ${ult ? "grid-cols-4" : "grid-cols-3"}`}>
                {regular.map((a) => <AbilityButton key={a.code} a={a} busy={act.isPending} onFire={fire} onHint={setHint} />)}
                {ult && <AbilityButton a={ult} busy={act.isPending} onFire={fire} onHint={setHint} charge={battle.charge_me} />}
              </div>
              {actor.passive && <p className="mt-1.5 text-center text-micro text-amber-200/80">Пассивка: {actor.passive.name}</p>}
            </>
          ) : (
            <p className="py-2 text-center text-xs text-ink-mist">
              {player.busy ? "Идёт розыгрыш…" : battle.auto ? "Автобой" : "Ход соперника"}
            </p>
          )}
          <div className="mt-2 grid grid-cols-3 gap-1.5">
            <button onClick={() => auto.mutate()} disabled={battle.auto || auto.isPending || player.busy} className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-chalk active:scale-95 disabled:opacity-40">
              {battle.auto ? "Автобой" : "🤖 Авто"}
            </button>
            <button onClick={() => setSpeed(speed === 1 ? 2 : 1)} className={`rounded-xl py-2 text-xs font-semibold active:scale-95 ${speed === 2 ? "bg-amber-400 text-bg-base" : "bg-white/5 text-ink-chalk"}`}>
              ⏩ ×{speed === 1 ? 2 : 1}
            </button>
            {player.busy ? (
              <button onClick={player.skip} className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-mist active:scale-95">Пропустить</button>
            ) : (
              <button onClick={() => setConfirmQuit(true)} className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-mist active:scale-95">Сдаться</button>
            )}
          </div>
        </section>
      )}

      {finished && (
        <div className="mx-1 grid grid-cols-2 gap-2">
          <button onClick={() => navigate(isBoss ? "/play/kontra/boss" : "/play/kontra/arena")} className="rounded-2xl bg-amber-400 py-3 text-sm font-black text-bg-base active:scale-95">
            {isBoss ? "К боссу" : "Ещё бой"}
          </button>
          <button onClick={() => navigate("/play/kontra")} className="rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist active:scale-95">К отряду</button>
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
    </div>
  );
}

function AbilityButton({ a, busy, onFire, onHint, charge }: {
  a: KontraAbility; busy: boolean; onFire: (a: KontraAbility) => void; onHint: (a: KontraAbility | null) => void; charge?: number;
}) {
  const fx = fxOf(a.code);
  const ult = Boolean(a.ult);
  const ready = a.ready && !busy;
  const press = useRef<ReturnType<typeof setTimeout> | null>(null);
  const held = useRef(false);
  const stop = () => { if (press.current) clearTimeout(press.current); press.current = null; };
  return (
    <button
      onClick={() => { if (held.current) { held.current = false; return; } onFire(a); }}
      onPointerDown={() => { held.current = false; press.current = setTimeout(() => { held.current = true; onHint(a); }, 380); }}
      onPointerUp={stop}
      onPointerLeave={stop}
      onContextMenu={(e) => e.preventDefault()}
      disabled={!ready}
      title={a.description}
      className={`relative flex flex-col items-center justify-center overflow-hidden rounded-2xl px-1 py-2 text-center active:scale-95 disabled:opacity-40 ${
        ult ? "text-bg-base" : a.code === "strike" ? "bg-white/10 text-ink-chalk" : "bg-white/5 text-ink-chalk ring-1"
      }`}
      style={ult
        ? { background: a.ready ? "linear-gradient(135deg,#fde047,#f97316)" : "rgba(255,255,255,0.06)", boxShadow: a.ready ? "0 0 18px rgba(249,115,22,0.7)" : undefined }
        : a.code === "strike" ? undefined : { ["--tw-ring-color" as string]: `${fx.color}88` }}
    >
      {ult && !a.ready && (
        <span className="absolute inset-x-0 bottom-0 bg-amber-400/25" style={{ height: `${charge ?? 0}%` }} />
      )}
      <span className="relative text-xl leading-none">{fx.icon}</span>
      <span className={`relative mt-1 line-clamp-2 text-[10px] font-bold leading-tight ${ult && !a.ready ? "text-ink-mist" : ""}`}>{a.name}</span>
      {!a.ready && !ult && (
        <span className="absolute inset-0 flex items-center justify-center bg-black/55 font-display text-lg font-black text-white">{a.cd}</span>
      )}
      {ult && !a.ready && <span className="relative font-mono text-[9px] text-ink-mist">{charge ?? 0}%</span>}
    </button>
  );
}

function OrderChip({ u, first, boss }: { u: KontraUnit; first: boolean; boss: boolean }) {
  return (
    <span className={`relative flex h-7 w-7 items-center justify-center overflow-hidden rounded-full text-[9px] font-black ring-2 ${
      first ? "z-10 scale-110 ring-amber-300" : u.side === "foe" ? "ring-red-500/80" : "ring-emerald-400/80"
    } bg-bg-raised text-white`}>
      {boss ? "👹" : u.card?.image_path
        ? <img src={staticUrl(u.card.image_path)} alt="" className="h-full w-full object-cover object-top" />
        : (u.card?.position ?? u.name.slice(0, 2))}
    </span>
  );
}

function TacticBadge({ battle }: { battle: KontraBattle }) {
  const me = battle.tactic_me;
  const foe = battle.tactic_foe;
  const win = me && foe && me.beats === foe.code;
  const lose = me && foe && foe.beats === me.code;
  return (
    <span className={`rounded-full px-2 py-1 text-[10px] font-bold backdrop-blur ${win ? "bg-emerald-500/30 text-emerald-100" : lose ? "bg-red-500/30 text-red-100" : "bg-black/50 text-white/85"}`}>
      {me?.name ?? "—"}{foe ? ` vs ${foe.name}` : ""}{win ? ` · +${battle.tactic_edge_pct}%` : lose ? ` · −` : ""}
    </span>
  );
}

function ChargeBar({ value, label, mine = false }: { value: number; label: string; mine?: boolean }) {
  const full = value >= 100;
  return (
    <div className={`${mine ? "flex-[2]" : "flex-1"} rounded-full bg-black/55 p-0.5 backdrop-blur`}>
      <div className="relative h-3 overflow-hidden rounded-full bg-white/10">
        <motion.div className={`h-full rounded-full ${mine ? "bg-gradient-to-r from-amber-400 to-orange-500" : "bg-gradient-to-r from-rose-500 to-red-600"}`}
          initial={false} animate={{ width: `${Math.min(100, value)}%` }} transition={{ duration: 0.5 }} />
        <span className={`absolute inset-0 flex items-center justify-center text-[8px] font-black uppercase tracking-wider ${full ? "text-bg-base" : "text-white/80"}`}>
          {full ? (mine ? "🔥 суперудар готов" : "⚠ заряжен") : label}
        </span>
      </div>
    </div>
  );
}

const CONFETTI = Array.from({ length: 26 }, (_, i) => ({
  x: (i * 37) % 100, d: (i % 7) * 0.08, c: ["#fde047", "#4ade80", "#38bdf8", "#f472b6", "#fb923c"][i % 5], r: (i * 47) % 360,
}));

function ResultOverlay({ battle, isBoss }: { battle: KontraBattle; isBoss: boolean }) {
  const win = battle.result === "win";
  return (
    <motion.div className="absolute inset-0 z-[300] flex flex-col items-center justify-center bg-black/55 px-4 text-center backdrop-blur-[2px]"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      {(win || isBoss) && CONFETTI.map((p, i) => (
        <motion.span key={i} className="absolute top-0 h-2.5 w-1.5 rounded-[1px]" style={{ left: `${p.x}%`, background: p.c }}
          initial={{ y: -20, rotate: p.r, opacity: 1 }} animate={{ y: 520, rotate: p.r + 540, opacity: [1, 1, 0] }}
          transition={{ delay: p.d, duration: 2.2, ease: "easeIn" }} />
      ))}
      <motion.p initial={{ scale: 2.4, opacity: 0, rotate: -8 }} animate={{ scale: 1, opacity: 1, rotate: -3 }}
        transition={{ type: "spring", stiffness: 200, damping: 14 }}
        className={`font-display text-4xl font-black uppercase drop-shadow-[0_4px_0_rgba(0,0,0,0.6)] ${isBoss ? "text-amber-300" : win ? "text-emerald-300" : "text-red-400"}`}>
        {isBoss ? "Урон!" : win ? "Победа!" : "Поражение"}
      </motion.p>
      {isBoss && <p className="mt-1 font-mono text-3xl font-black text-white">{fmt(battle.damage)}</p>}
      <motion.div initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} transition={{ delay: 0.35 }}
        className="mt-3 flex flex-wrap justify-center gap-2 text-sm font-bold">
        <span className="flex items-center gap-1 rounded-full bg-black/50 px-3 py-1 text-ink-chalk">+{battle.reward_coins} <IconCoin size={13} /></span>
        {!isBoss && (
          <span className={`rounded-full bg-black/50 px-3 py-1 ${battle.rating_delta >= 0 ? "text-accent-green" : "text-red-400"}`}>
            {battle.rating_delta >= 0 ? "+" : ""}{battle.rating_delta} рейтинга{battle.revenge && win ? " · реванш!" : ""}
          </span>
        )}
      </motion.div>
      {battle.gear_drop && (
        <motion.div initial={{ scale: 0.5, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 0.6, type: "spring" }}
          className="mt-3 rounded-2xl bg-amber-400/15 px-3 py-2 text-xs text-amber-100 ring-1 ring-amber-300/50">
          🎁 Выпало: {battle.gear_drop.slot_label} «{battle.gear_drop.set_name}» · {battle.gear_drop.rarity_label} (+{battle.gear_drop.pct}%)
        </motion.div>
      )}
    </motion.div>
  );
}
