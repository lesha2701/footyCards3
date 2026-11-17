import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  type MagicActInput,
  fetchMagicRun,
  magicAccept,
  magicAct,
  magicAuto,
  magicBuy,
  magicCast,
  magicChoose,
  magicEndDay,
  magicForfeit,
  magicLeaveBattle,
  magicMove,
  magicRetry,
  magicRetryInvoice,
} from "@/api/magic";
import { fetchMyProfile } from "@/api/profile";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import { IconChevronLeft, IconCoin } from "@/components/icons";
import BattleField from "@/components/magic/BattleField";
import Coach, { type CoachStep } from "@/components/magic/Coach";
import IsoMap from "@/components/magic/IsoMap";
import { CasualtiesBlock } from "@/components/magic/MagicLosses";
import StackToken from "@/components/magic/StackToken";
import { ArtIcon, CastleArt, HeroArt, MapObjectArt } from "@/components/magic/art/mapObjects";
import { mapPath } from "@/components/magic/mapPath";
import { setSoundOn, sfx, soundOn } from "@/components/magic/sound";
import { useCoach } from "@/components/magic/useCoach";
import { fmt } from "@/components/magic/magicMeta";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify, hapticSelection } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { MagicEvent, MagicMapObject, MagicNotice, MagicRun } from "@/types";

const MAP_COACH: CoachStep[] = [
  { icon: "🗺️", title: "Твой поход", text: "Карту двигай пальцем, приближай кнопками «+» и «−». Туман прячет то, где герой ещё не был — иди и разведывай." },
  { icon: "👆", title: "Куда идти", text: "Нажми сундук, лагерь или любое место — покажу путь и что там, потом «Идти». Тёплый свет на земле — докуда хватит шагов сегодня." },
  { icon: "💰", title: "Сундуки и рынок", text: "В сундуке выбираешь: золото или опыт героя. На золото рынок нанимает отряды, а остаток в конце похода станет монетами." },
  { icon: "⚔️", title: "Лагеря", text: "Лагерь — это бой. Смотри охрану и цвет опасности: зелёный — легко, красный — твоя армия может пасть. Победа поднимает боевой дух до конца похода." },
  { icon: "🏟️", title: "Здания", text: "Тренировочная база — +10% урона, прожектор снимает туман далеко вокруг, лазарет лечит всю армию, тоннель переносит на другой край карты, святилище даёт оберег от гипноза." },
  { icon: "🌙", title: "Дни", text: "Шаги кончились — жми «Завершить день». Когда дни выйдут, будет финальная битва. Подсказки снова открываются кнопкой «?» вверху." },
];

// The first run of a bigger mode: what is different there (shown once per mode).
const MODE_COACH: Record<string, CoachStep[]> = {
  hardcore: [
    { icon: "🔥", title: "Хардкор", text: "Огромная карта и вдвое больше дней. Соперник тоже растёт — не отставай." },
    { icon: "☠️", title: "Павшие гибнут все", text: "Здесь нет раненых: каждый павший уходит из коллекции навсегда. Зато награда в 2,5 раза больше." },
  ],
  adventure: [
    { icon: "🧭", title: "Приключение", text: "Соперника нет: целый месяц собирай силу. Чем дальше от дома, тем сильнее лагеря." },
    { icon: "🌙", title: "Ночной отдых", text: "Каждую ночь армия восстанавливает часть павших. Лазарет лечит всех сразу, но потом отдыхает несколько дней." },
    { icon: "🎭", title: "Потерявшие всё", text: "В дальней части карты — логова Потерявших: сильные одиночки разных уровней со своими умениями. Святилище подскажет, кто в ближайшем." },
    { icon: "👁️", title: "Безликий", text: "В конце ждёт Безликий в логове наверху. Его гипноз переманивает твой сильнейший отряд — оберег святилища сгорит вместо него." },
  ],
};

/** Mounted once the run (and so its mode) is known: the hints remember the mode they were shown for. */
function ModeCoach({ mode, ready }: { mode: string; ready: boolean }) {
  const c = useCoach(`magic_coach_mode_${mode}_v1`);
  return <Coach open={ready && c.open} steps={MODE_COACH[mode] ?? []} onClose={c.close} />;
}


function Sheet({ children, onClose }: { children: ReactNode; onClose?: () => void }) {
  // Android Chrome fires the tap's click ~40ms after touchend, re-hit-tested onto
  // this freshly opened backdrop, which would close the sheet the tap just opened.
  const opened = useRef(Date.now());
  return (
    <motion.div
      className="absolute inset-0 z-30 flex items-end justify-center bg-black/40"
      initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
      onClick={() => { if (Date.now() - opened.current > 400) onClose?.(); }}
      onPointerDown={(e) => e.stopPropagation()}
    >
      <motion.section
        initial={{ y: 60 }} animate={{ y: 0 }} exit={{ y: 60 }} transition={{ type: "spring", stiffness: 260, damping: 26 }}
        onClick={(e) => e.stopPropagation()}
        className="safe-bottom w-full max-w-md rounded-t-3xl bg-bg-surface px-4 pb-4 pt-3 ring-1 ring-white/10"
      >
        <div className="mx-auto mb-2 h-1 w-10 rounded-full bg-white/15" />
        {children}
      </motion.section>
    </motion.div>
  );
}

function ObjectIcon({ run, o, size = 64 }: { run: MagicRun; o: MagicMapObject; size?: number }) {
  if (o.kind === "castle") {
    return <ArtIcon size={size}><CastleArt faction={o.owner === "me" ? run.faction : run.rival} skin={o.owner === "me" ? run.castle_skin : run.mode === "adventure" ? "victor" : "default"} rival={o.owner !== "me"} /></ArtIcon>;
  }
  return <ArtIcon size={size} tight><MapObjectArt kind={o.kind} variant={o.variant ?? undefined} level={o.level ?? undefined} taken={!!o.taken_by && !["market", "medic", "tunnel"].includes(o.kind)} faction={run.faction} style={o.style} /></ArtIcon>;
}

const NOTICE_ICON: Record<string, string> = {
  chest: "💰", well: "🔮", artifact: "✨", tribune: "🏟️", reinforce: "🎺", camp: "🏆", mine: "⛏️", hired: "🤝", day: "🌅",
  quest: "📜", perk: "⭐", training: "🎽", floodtower: "💡", medic: "⛑️", tunnel: "🌀", shrine: "🕯️",
};

/** Coins or mana sparks flying from the middle of the screen into their counter. */
function FlyReward({ kind, to, onDone }: { kind: "gold" | "mana"; to: DOMRect | null; onDone: () => void }) {
  useEffect(() => {
    const t = setTimeout(onDone, 1100);
    return () => clearTimeout(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  if (!to) return null;
  const sx = window.innerWidth / 2;
  const sy = window.innerHeight * 0.45;
  return (
    <div className="pointer-events-none fixed inset-0 z-[60]">
      {Array.from({ length: 9 }, (_, i) => (
        <motion.span key={i} className="absolute text-lg"
          initial={{ x: sx + (i % 3 - 1) * 26, y: sy + (Math.floor(i / 3) - 1) * 22, scale: 1, opacity: 1 }}
          animate={{ x: to.left + to.width / 2 - 9, y: to.top + to.height / 2 - 10, scale: 0.5, opacity: [1, 1, 0.2] }}
          transition={{ duration: 0.7, delay: i * 0.04, ease: "easeIn" }}>
          {kind === "gold" ? "🪙" : "✨"}
        </motion.span>
      ))}
    </div>
  );
}

export default function MagicRunPage() {
  const { runId } = useParams();
  const id = Number(runId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [run, setRun] = useState<MagicRun | null>(null);
  const [events, setEvents] = useState<MagicEvent[]>([]);
  const [selected, setSelected] = useState<[number, number] | null>(null);
  const [walk, setWalk] = useState<[number, number][] | null>(null);
  const [notice, setNotice] = useState<MagicNotice | null>(null);
  const [marketOpen, setMarketOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmQuit, setConfirmQuit] = useState(false);
  // "Out of steps — end the day?" after a walk that used the last move.
  const [tired, setTired] = useState(false);
  const [showResult, setShowResult] = useState(false);
  // While the battle replays its log, results and notices wait for it.
  const [replaying, setReplaying] = useState(false);
  const [paying, setPaying] = useState(false);
  const coach = useCoach("magic_coach_map_v3");
  const [journal, setJournal] = useState(false);
  const [night, setNight] = useState(false);
  const [fly, setFly] = useState<{ kind: "gold" | "mana"; n: number } | null>(null);
  const [sound, setSound] = useState(soundOn);
  const goldChip = useRef<HTMLSpanElement>(null);
  const manaChip = useRef<HTMLSpanElement>(null);

  const { data, isError } = useQuery({ queryKey: ["magic-run", id], queryFn: () => fetchMagicRun(id) });
  useEffect(() => {
    if (!data || run) return;
    setRun(data);
    if (data.hero.goal && data.phase === "map") setSelected([data.hero.goal[0], data.hero.goal[1]]);
  }, [data, run]);

  const receive = (r: MagicRun, route: [number, number][] | null = null) => {
    setError(null);
    setSelected(null);
    setTired(false);
    setEvents(r.events);
    if (r.phase === "map" && r.status === "in_progress") {
      // A long walk keeps its target: the route stays on the map for tomorrow.
      if (r.hero.goal) setSelected([r.hero.goal[0], r.hero.goal[1]]);
      if (route && r.hero.moves === 0 && !r.notice) setTimeout(() => setTired(true), Math.min(2000, route.length * 170) + 150);
    }
    if (route) {
      const end = route.findIndex(([x, y]) => x === r.hero.x && y === r.hero.y);
      setWalk(end > 0 ? route.slice(0, end + 1) : null);
    } else {
      setWalk(null);
    }
    setRun(r);
    queryClient.setQueryData(["magic-run", id], r);
    const dawn = night ? 900 : 0;
    if (night) setTimeout(() => setNight(false), 650);
    if (route && route.length > 1) sfx("step");
    if (r.notice) {
      const n = r.notice;
      const wait = (route ? Math.min(2000, route.length * 170) : 0) + dawn;
      if (n.kind === "market" && n.object) setMarketOpen(n.object);
      else setTimeout(() => setNotice(n), wait);
      setTimeout(() => {
        if (n.gold) { setFly({ kind: "gold", n: Date.now() }); sfx("coin"); }
        else if (n.kind === "well") { setFly({ kind: "mana", n: Date.now() }); sfx("spell"); }
        else if (n.kind === "chest" || n.kind === "artifact" || n.kind === "perk" || n.kind === "quest") sfx("chest");
        else if (n.kind === "day") sfx("day");
      }, wait + 250);
      hapticNotify("success");
    }
    if (r.status === "finished") {
      queryClient.invalidateQueries({ queryKey: ["magic-hub"] });
      // The result opens once the battle's replay is over (see `replaying`).
      setTimeout(() => {
        setShowResult(true);
        sfx(r.result === "win" ? "win" : "lose");
        hapticNotify(r.result === "win" ? "success" : "error");
        fetchMyProfile().then((p) => updateBalance(p.balance)).catch(() => undefined);
      }, 600);
    }
  };
  const fail = (err: unknown) => {
    setError(formatGameError(err, "Ход не принят"));
    setNight(false);
    fetchMagicRun(id).then((r) => { setRun(r); setEvents([]); }).catch(() => undefined);
  };
  const call = useMutation({
    mutationFn: ({ fn }: { fn: () => Promise<MagicRun>; route?: [number, number][] | null }) => fn(),
    onSuccess: (r, vars) => receive(r, vars.route ?? null),
    onError: fail,
  });
  const act = (fn: () => Promise<MagicRun>, route?: [number, number][] | null) => call.mutate({ fn, route });

  useEffect(() => { if (run?.status === "finished" && !events.length) setShowResult(true); }, [run?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!run) return isError ? <ErrorScreen message="Поход не найден" /> : <LoadingScreen />;

  const v = run.version;
  const objAt = (x: number, y: number) => run.objects.find((o) => o.x === x && o.y === y);
  const reachable = new Set(run.reachable.map(([x, y]) => `${x},${y}`));
  const sel = selected ? objAt(...selected) : undefined;
  const selBot = !!selected && run.bot.visible && selected[0] === run.bot.x && selected[1] === run.bot.y;
  const selPath = selected ? mapPath(run, selected) : null;
  const selSteps = selPath ? selPath.length - 1 : null;
  const canGo = selected ? reachable.has(`${selected[0]},${selected[1]}`) : false;
  // Too far for today: walk what the moves allow, the rest tomorrow.
  const canGoPart = !canGo && selSteps !== null && selSteps > 0 && run.hero.moves > 0;
  const outOfSteps = !canGo && selSteps !== null && selSteps > 0 && run.hero.moves === 0;
  const endDay = () => {
    setNight(true);
    act(() => magicEndDay(id, v));
  };
  const questsDone = (run.quests ?? []).filter((q) => q.done).length;
  const inBattle = !!run.battle && (run.phase === "battle" || run.phase === "battle_over" || run.phase === "final_lost" || (run.status === "finished" && (!showResult || replaying) && events.length > 0));
  const lastDay = run.day >= run.days;
  const isHere = (o?: MagicMapObject) => !!o && o.x === run.hero.x && o.y === run.hero.y;
  const market = marketOpen ? run.objects.find((o) => o.id === marketOpen) : undefined;

  const onCell = (x: number, y: number) => {
    hapticSelection();
    if (run.phase !== "map") return;
    const o = objAt(x, y);
    if (o?.kind === "market" && isHere(o)) {
      setMarketOpen(o.id);
      return;
    }
    const isBot = run.bot.visible && x === run.bot.x && y === run.bot.y;
    // A second tap on an empty reachable place walks there.
    if (reachable.has(`${x},${y}`) && !o && !isBot && selected?.[0] === x && selected?.[1] === y) {
      act(() => magicMove(id, v, x, y), mapPath(run, [x, y]));
      return;
    }
    setSelected(selected && selected[0] === x && selected[1] === y ? null : [x, y]);
  };
  const go = () => selected && act(() => magicMove(id, v, selected[0], selected[1]), selPath);

  const payRetryStars = async () => {
    setPaying(true);
    try {
      const res = await payShopWithStars(() => magicRetryInvoice(id));
      if (res === "paid") act(() => magicRetry(id, v, "credit"));
    } catch (err) {
      setError(formatGameError(err, "Покупка не прошла"));
    } finally {
      setPaying(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[#05070d]">
      {/* Top bar */}
      <div className="safe-top relative z-20 flex items-center gap-1.5 bg-gradient-to-b from-black/85 to-black/40 px-2 pb-1.5 pt-1.5">
        <button onClick={() => navigate("/play/magic")} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-ink-chalk active:scale-90" aria-label="Назад">
          <IconChevronLeft size={18} />
        </button>
        <div className="grid flex-1 grid-cols-4 gap-1">
          {[
            ["☀️", `${run.day}/${run.days}`],
            ["👣", `${run.hero.moves}`],
            ["💰", fmt(run.hero.gold)],
            ["✨", `${run.hero.mana}/${run.hero.max_mana}`],
          ].map(([icon, text]) => (
            <span key={icon} ref={icon === "💰" ? goldChip : icon === "✨" ? manaChip : undefined}
              className="rounded-full bg-white/10 py-1 text-center text-[11px] font-black text-ink-chalk">{icon} {text}</span>
          ))}
        </div>
        <button onClick={() => setJournal(true)} className="relative flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-sm active:scale-90" aria-label="Журнал похода">
          📜
          {(run.quests?.length ?? 0) > 0 && (
            <span className="absolute -right-1 -top-1 rounded-full bg-amber-400 px-1 text-[9px] font-black leading-4 text-black">{questsDone}/{run.quests!.length}</span>
          )}
        </button>
        <button onClick={() => { setSoundOn(!sound); setSound(!sound); }} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-sm active:scale-90" aria-label="Звук">
          {sound ? "🔊" : "🔇"}
        </button>
        <button onClick={coach.show} className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/10 text-sm font-black text-amber-200 active:scale-90" aria-label="Подсказки">?</button>
      </div>

      {error && (
        <button onClick={() => setError(null)} className="absolute left-3 right-3 top-14 z-40 rounded-xl bg-red-600/90 px-3 py-2 text-left text-xs font-semibold text-white shadow-lg">
          {error}
        </button>
      )}

      {inBattle && run.battle ? (
        <div className="safe-bottom relative flex min-h-0 flex-1 flex-col px-2 pb-2 pt-1">
          <p className={`mb-1 text-center text-[9px] ${run.mode === "hardcore" ? "text-red-300" : "text-amber-200/80"}`}>
            {run.mode === "hardcore" ? "🔥 Хардкор: павшие в этом бою погибнут навсегда" : "⚠️ Павшие в бою уйдут из коллекции: половина навсегда, остальные ранены"}
          </p>
          <BattleField
            battle={run.battle}
            events={events}
            version={v}
            spells={run.hero.spells}
            mana={run.hero.mana}
            busy={call.isPending}
            onAct={(input: MagicActInput) => act(() => magicAct(id, v, input))}
            onCast={(spell, target) => act(() => magicCast(id, v, spell, target))}
            onAuto={() => act(() => magicAuto(id, v))}
            biome={run.biome}
            onReplay={setReplaying}
          />
        </div>
      ) : (
        <>
          <div className="relative flex-1">
            <IsoMap run={run} selected={selected} path={selPath} walk={walk} onCell={onCell} />
            {/* Rival strength and morale, small, over the map */}
            <div className="pointer-events-none absolute left-2 top-2 flex flex-col gap-1">
              {run.event && <span className="rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-bold text-sky-200">{run.event.icon} {run.event.title}</span>}
              {run.hero.morale > 0 && <span className="rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-bold text-orange-200">🔥 дух +{run.hero.morale}%</span>}
              {run.bot.gain_pct > 0 && <span className="rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-bold text-red-300">🚩 соперник +{run.bot.gain_pct}%</span>}
              {run.mode === "adventure" && <span className="rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-bold text-violet-300">🎭 Безликий ждёт в логове наверху</span>}
              <span className="rounded-full bg-black/60 px-2 py-0.5 text-[10px] font-bold text-amber-100">⭐ {run.score}</span>
            </div>
          </div>

          {/* Bottom bar: the army and the day's end — always on screen. */}
          <div className="safe-bottom relative z-20 bg-gradient-to-t from-black/95 to-black/70 px-2 pt-1.5">
            <div className="flex items-center gap-2 overflow-x-auto pb-1.5 pt-1">
              {run.army.map((s) => (
                <div key={s.id} className="shrink-0"><StackToken unit={s.unit} tier={s.tier} count={s.count} image={s.card?.image_path} size={38} /></div>
              ))}
              {run.hero.artifacts.map((a) => (
                <span key={a.code} title={a.text} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-300/15 text-lg ring-1 ring-amber-300/30">{a.emoji}</span>
              ))}
              <button onClick={() => setConfirmQuit(true)} className="ml-auto shrink-0 px-1 text-[10px] text-ink-mist-dim underline">Сдаться</button>
            </div>
            <button
              disabled={call.isPending || run.phase !== "map"}
              onClick={endDay}
              className={`mb-2 w-full rounded-2xl py-3 font-display text-base font-black active:scale-[0.98] disabled:opacity-40 ${
                run.hero.moves === 0 || lastDay ? "bg-gradient-to-r from-amber-400 to-orange-500 text-black shadow-[0_0_20px_rgba(251,191,36,0.45)]" : "bg-white/12 bg-white/10 text-ink-chalk"
              }`}
            >
              {lastDay ? "⚔️ Завершить день — финальная битва" : `🌙 Завершить день ${run.day}`}
            </button>
          </div>
        </>
      )}

      {/* Night falls on "end the day", the morning comes with the answer. */}
      <AnimatePresence>
        {night && (
          <motion.div key="night" className="pointer-events-none absolute inset-0 z-[35] flex items-center justify-center"
            style={{ background: "radial-gradient(ellipse at 50% 30%, rgba(30,41,90,0.75), rgba(5,7,20,0.92))" }}
            initial={{ opacity: 0 }} animate={{ opacity: 1 }}
            exit={{ opacity: 0, background: "radial-gradient(ellipse at 50% 90%, rgba(251,146,60,0.55), rgba(5,7,20,0))" }}
            transition={{ duration: 0.5 }}>
            <motion.span className="text-6xl" initial={{ y: 20, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: -30, opacity: 0 }}>🌙</motion.span>
          </motion.div>
        )}
      </AnimatePresence>
      {fly && <FlyReward key={fly.n} kind={fly.kind} to={(fly.kind === "gold" ? goldChip : manaChip).current?.getBoundingClientRect() ?? null} onDone={() => setFly(null)} />}

      {/* --- popups --- */}
      <AnimatePresence>
        {run.phase === "map" && tired && !notice && !market && (
          <Sheet key="tired" onClose={() => setTired(false)}>
            <div className="flex flex-col items-center text-center">
              <span className="text-5xl">👣</span>
              <p className="mt-1 font-display text-lg font-black text-ink-chalk">Шаги на сегодня закончились</p>
              <p className="text-xs text-ink-mist">
                {run.hero.goal ? "Завершить день? Завтра герой пойдёт дальше по своему пути" : "Завершить день? Утром у героя снова будут шаги"}
              </p>
            </div>
            <button disabled={call.isPending} onClick={endDay}
              className="mt-3 w-full rounded-2xl bg-gradient-to-r from-amber-400 to-orange-500 py-3 font-display text-base font-black text-black active:scale-95 disabled:opacity-40">
              {lastDay ? "⚔️ Завершить день — финальная битва" : `🌙 Завершить день ${run.day}`}
            </button>
            <button onClick={() => setTired(false)} className="mt-2 w-full rounded-2xl bg-white/10 py-2.5 text-sm font-semibold text-ink-chalk active:scale-95">
              Осмотреться
            </button>
          </Sheet>
        )}

        {run.phase === "map" && selected && (sel || selBot || selSteps !== null) && !notice && !market && !tired && (
          <Sheet key="info" onClose={() => setSelected(null)}>
            <div className="flex items-center gap-3">
              <div className="shrink-0">
                {selBot ? <ArtIcon size={64}><HeroArt faction={run.rival} rival /></ArtIcon> : sel ? <ObjectIcon run={run} o={sel} /> : <span className="flex h-16 w-16 items-center justify-center text-3xl">🚶</span>}
              </div>
              <div className="min-w-0 flex-1">
                <p className="font-display text-base font-black text-ink-chalk">
                  {selBot ? "Герой-соперник" : sel ? sel.label : "Сюда можно пройти"}
                  {sel?.taken_by && sel.kind !== "market" ? <span className="ml-1 text-xs font-semibold text-ink-mist">{sel.taken_by === "me" ? "· твоё" : "· у соперника"}</span> : null}
                </p>
                <p className="text-xs text-ink-mist">{selBot ? "Подойди — начнётся финальная битва" : sel ? sel.hint : "Пустая земля"}</p>
                {sel?.guards.length ? <p className="mt-1 text-[11px] leading-snug text-red-300">Охрана: {sel.guards.join(" · ")}</p> : null}
                {sel?.kind === "camp" && !sel.taken_by && sel.danger ? (
                  <p className={`mt-1 text-[11px] font-bold ${sel.danger === "easy" ? "text-emerald-300" : sel.danger === "even" ? "text-amber-300" : "text-red-300"}`}>
                    {sel.danger === "easy" ? "Слабее твоей армии" : sel.danger === "even" ? "Примерно равны по силе" : "Сильнее твоей армии"}
                  </p>
                ) : null}
              </div>
            </div>
            {!(sel?.taken_by && sel.kind !== "mine" && sel.kind !== "market") && !(sel?.kind === "castle" && sel.owner === "me") && (
              <button
                disabled={!(canGo || canGoPart || outOfSteps) || call.isPending}
                onClick={outOfSteps ? endDay : go}
                className={`mt-3 w-full rounded-2xl py-3 text-sm font-black text-black active:scale-95 disabled:opacity-40 ${outOfSteps ? "bg-gradient-to-r from-amber-400 to-orange-500" : "bg-amber-400"}`}
              >
                {canGo
                  ? `${sel?.kind === "camp" || selBot || sel?.kind === "castle" ? "⚔️ В бой" : "Идти"} · ${selSteps} шаг.`
                  : canGoPart ? `Идти · сегодня ${run.hero.moves} из ${selSteps} шаг.`
                    : outOfSteps ? `🌙 Завершить день · до цели ${selSteps} шаг.` : "Туда не пройти"}
              </button>
            )}
          </Sheet>
        )}

        {run.phase === "choice" && run.pending?.kind === "perk" && (
          <Sheet key="perk">
            <div className="flex flex-col items-center text-center">
              <motion.span className="text-5xl" animate={{ scale: [1, 1.2, 1], rotate: [0, -8, 8, 0] }} transition={{ duration: 0.8 }}>⭐</motion.span>
              <p className="font-display text-lg font-black text-ink-chalk">Герой вырос!</p>
              <p className="text-xs text-ink-mist">Выбери умение до конца похода</p>
            </div>
            <div className="mt-3 flex flex-col gap-2">
              {run.pending.options.map((o) => (
                <button key={o.code} disabled={call.isPending} onClick={() => act(() => magicChoose(id, v, o.code))}
                  className="flex items-center gap-3 rounded-2xl bg-gradient-to-r from-indigo-500/40 to-fuchsia-500/30 px-3 py-2.5 text-left ring-1 ring-white/15 active:scale-[0.98]">
                  <span className="text-3xl">{o.emoji}</span>
                  <span>
                    <span className="block font-display text-sm font-black text-ink-chalk">{o.title}</span>
                    <span className="block text-[11px] text-ink-mist">{o.text}</span>
                  </span>
                </button>
              ))}
            </div>
          </Sheet>
        )}

        {journal && (
          <Sheet key="journal" onClose={() => setJournal(false)}>
            <div className="max-h-[70vh] overflow-y-auto">
              <p className="font-display text-lg font-black text-ink-chalk">📜 Журнал похода</p>
              {run.bot_style && (
                <p className="mt-1 text-xs text-ink-mist">🚩 Соперник — <b className="text-red-300">{run.bot_style.label}</b>: {run.bot_style.text}</p>
              )}
              {run.event && <p className="mt-1 text-xs text-sky-200">{run.event.icon} Сегодня: {run.event.title} — {run.event.text}</p>}
              {(run.quests?.length ?? 0) > 0 && (
                <div className="mt-3">
                  <p className="text-[11px] font-bold uppercase tracking-wide text-ink-mist">Задания · награда 250 золота</p>
                  {run.quests!.map((q) => {
                    const goal = q.code === "strong" ? 1 : q.target;
                    return (
                      <div key={q.code} className="mt-1.5 flex items-center gap-2 rounded-xl bg-white/5 px-3 py-2">
                        <span className="text-lg">{q.done ? "✅" : q.failed ? "❌" : "🎯"}</span>
                        <span className={`flex-1 text-xs ${q.failed ? "text-ink-mist-dim line-through" : "text-ink-chalk"}`}>{q.text}</span>
                        <span className="font-mono text-[11px] text-amber-200">{Math.min(q.progress, goal)}/{goal}</span>
                      </div>
                    );
                  })}
                </div>
              )}
              {(run.perks?.length ?? 0) > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {run.perks!.map((p, i) => <span key={i} className="rounded-full bg-indigo-500/25 px-2 py-1 text-[11px] font-bold text-indigo-100">{p.emoji} {p.title}</span>)}
                </div>
              )}
              <p className="mt-3 text-[11px] font-bold uppercase tracking-wide text-ink-mist">События</p>
              <div className="mt-1 flex flex-col gap-1">
                {[...run.log].reverse().map((l, i) => (
                  <p key={i} className="text-xs text-ink-chalk"><span className="mr-1 font-mono text-[10px] text-ink-mist">д{l.day}</span>{l.text}</p>
                ))}
              </div>
            </div>
          </Sheet>
        )}

        {run.phase === "choice" && run.pending && run.pending.kind !== "perk" && (
          <Sheet key="choice">
            <div className="flex flex-col items-center text-center">
              <ArtIcon size={84} tight><MapObjectArt kind="chest" /></ArtIcon>
              <p className="font-display text-lg font-black text-ink-chalk">Сундук с сокровищем!</p>
              <p className="text-xs text-ink-mist">Что берёшь?</p>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {run.pending.options.map((o) => (
                <button key={o.code} disabled={call.isPending} onClick={() => act(() => magicChoose(id, v, o.code))}
                  className={`rounded-2xl px-2 py-3 font-black active:scale-95 ${o.code === "gold" ? "bg-gradient-to-b from-amber-300 to-amber-500 text-black" : "bg-gradient-to-b from-indigo-400 to-indigo-700 text-white"}`}>
                  <span className="block text-2xl">{o.code === "gold" ? "💰" : "⭐"}</span>
                  {o.code === "gold" ? `+${o.gold} золота` : `+${(o.xp ?? 0) + 10} опыта`}
                  <span className="block text-[10px] font-semibold opacity-80">{o.code === "gold" ? "на рынок и в монеты" : "герой растёт быстрее"}</span>
                </button>
              ))}
            </div>
          </Sheet>
        )}

        {market && run.phase === "map" && (
          <Sheet key="market" onClose={() => setMarketOpen(null)}>
            <div className="flex items-center gap-3">
              <ObjectIcon run={run} o={market} size={60} />
              <div>
                <p className="font-display text-base font-black text-ink-chalk">Трансферный рынок</p>
                <p className="text-xs text-ink-mist">У тебя 💰 {fmt(run.hero.gold)} золота</p>
              </div>
            </div>
            <div className="mt-3 flex flex-col gap-2">
              {market.offers.map((f, i) => (
                <div key={f.unit} className="flex items-center gap-3 rounded-2xl bg-white/5 p-2">
                  <StackToken unit={f.unit} tier={f.tier} count={f.count} size={46} dim={f.bought} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-bold text-ink-chalk">{f.unit_name}</p>
                    <p className="text-[11px] text-ink-mist">×{f.count} бойцов</p>
                  </div>
                  <button
                    disabled={f.bought || run.hero.gold < f.price || call.isPending || !isHere(market)}
                    onClick={() => act(() => magicBuy(id, v, market.id, i))}
                    className="rounded-xl bg-amber-400 px-3 py-2 text-xs font-black text-black active:scale-95 disabled:opacity-40"
                  >
                    {f.bought ? "Нанят" : `💰 ${fmt(f.price)}`}
                  </button>
                </div>
              ))}
            </div>
            <button onClick={() => setMarketOpen(null)} className="mt-3 w-full rounded-2xl bg-white/10 py-2.5 text-sm font-semibold text-ink-chalk active:scale-95">Уйти с рынка</button>
          </Sheet>
        )}

        {notice && !(inBattle && replaying) && (
          <motion.div key="notice" className="absolute inset-0 z-40 flex items-center justify-center bg-black/50 p-6"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setNotice(null)}>
            <motion.div initial={{ scale: 0.6, y: 20 }} animate={{ scale: 1, y: 0 }} transition={{ type: "spring", stiffness: 300, damping: 18 }}
              className="w-full max-w-xs rounded-3xl bg-gradient-to-b from-indigo-950 to-bg-surface p-5 text-center ring-1 ring-amber-300/40 shadow-2xl">
              <motion.div className="mx-auto flex justify-center" animate={{ rotate: [0, -6, 6, 0] }} transition={{ duration: 0.6 }}>
                {notice.unit ? <StackToken unit={notice.unit} tier={3} count={0} size={80} />
                  : notice.kind === "day" ? <span className="text-6xl">🌅</span>
                    : <ArtIcon size={90} tight><MapObjectArt kind={notice.kind === "hired" ? "market" : notice.kind} variant={notice.artifact} level={2} faction={run.faction} /></ArtIcon>}
              </motion.div>
              <p className="mt-1 font-display text-lg font-black text-ink-chalk">{NOTICE_ICON[notice.kind] ?? ""} {notice.title}</p>
              <p className={`mt-1 font-bold ${notice.gold ? "font-display text-2xl text-amber-300" : "text-sm text-ink-chalk"}`}>{notice.text}</p>
              {notice.lines?.length ? (
                <div className="mt-2 flex flex-col gap-0.5 rounded-xl bg-black/30 p-2 text-left">
                  {notice.lines.map((l, i) => <p key={i} className="text-[11px] text-ink-mist">• {l}</p>)}
                </div>
              ) : null}
              {notice.points ? <p className="mt-1 text-xs text-amber-200/80">+{notice.points} очков</p> : null}
              <button className="mt-3 w-full rounded-2xl bg-amber-400 py-2.5 text-sm font-black text-black active:scale-95">Отлично!</button>
            </motion.div>
          </motion.div>
        )}

        {run.phase === "battle_over" && run.battle && !replaying && !notice && (
          <Sheet key="won">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center">
              <p className="text-5xl">🏆</p>
              <p className="font-display text-xl font-black text-ink-chalk">Лагерь разбит!</p>
              <p className="text-xs text-ink-mist">Потери: {run.battle.losses} · боевой дух +{run.hero.morale}% урона</p>
              <button onClick={() => act(() => magicLeaveBattle(id, v))} className="mt-3 w-full rounded-2xl bg-amber-400 py-3 text-sm font-black text-black active:scale-95">
                Продолжить поход
              </button>
            </motion.div>
          </Sheet>
        )}

        {run.phase === "final_lost" && run.retry && !replaying && (
          <Sheet key="retry">
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="text-center">
              <p className="text-5xl">💔</p>
              <p className="font-display text-xl font-black text-ink-chalk">Финал проигран</p>
              <p className="text-xs text-ink-mist">
                {run.retry.available ? "Второй шанс: переиграй финал с той же армией и маной, что были перед битвой." : "Вторые шансы на сегодня закончились."}
              </p>
              {run.retry.available && (
                <div className="mt-3 flex flex-col gap-2">
                  {run.retry.credits > 0 && (
                    <button disabled={call.isPending} onClick={() => act(() => magicRetry(id, v, "credit"))} className="rounded-2xl bg-amber-400 py-3 text-sm font-black text-black active:scale-95">
                      🔁 Переиграть (оплачено)
                    </button>
                  )}
                  <div className="grid grid-cols-2 gap-2">
                    {run.retry.coins && (
                      <button disabled={call.isPending} onClick={() => act(() => magicRetry(id, v, "coins"))}
                        className="flex items-center justify-center gap-1 rounded-2xl bg-amber-400 py-3 text-sm font-black text-black active:scale-95 disabled:opacity-40">
                        🔁 {run.retry.coins} <IconCoin size={14} />
                      </button>
                    )}
                    {run.retry.stars && (
                      <button disabled={paying} onClick={payRetryStars}
                        className="rounded-2xl bg-gradient-to-r from-sky-400 to-indigo-500 py-3 text-sm font-black text-white active:scale-95 disabled:opacity-40">
                        🔁 {run.retry.stars} ⭐
                      </button>
                    )}
                  </div>
                </div>
              )}
              <button onClick={() => act(() => magicAccept(id, v))} className="mt-2 w-full rounded-2xl bg-white/10 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
                Принять поражение
              </button>
            </motion.div>
          </Sheet>
        )}
      </AnimatePresence>

      <Coach open={coach.open && !inBattle && run.status === "in_progress"} steps={MAP_COACH} onClose={coach.close} />
      {/* After the general hints: what this bigger mode does differently. */}
      {MODE_COACH[run.mode ?? ""] && (
        <ModeCoach mode={run.mode ?? ""} ready={!coach.open && !inBattle && run.status === "in_progress"} />
      )}

      <ConfirmDialog
        open={confirmQuit}
        title="Сдаться?"
        description={run.phase === "battle"
          ? "Поход засчитают поражением без награды и опыта. Сдача посреди боя: все отряды на поле считаются павшими и уйдут из коллекции (часть навсегда)."
          : "Поход засчитают поражением без награды и опыта. Уже павшие в походе существа уйдут из коллекции (часть навсегда)."}
        confirmLabel="Сдаться"
        danger
        onConfirm={() => { setConfirmQuit(false); act(() => magicForfeit(id)); }}
        onCancel={() => setConfirmQuit(false)}
      />

      <AnimatePresence>
        {showResult && !replaying && run.status === "finished" && (
          <motion.div className="absolute inset-0 z-50 flex items-end justify-center bg-black/70 p-4 backdrop-blur-sm"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
            <motion.section initial={{ y: 40, scale: 0.95 }} animate={{ y: 0, scale: 1 }}
              className="safe-bottom w-full max-w-sm rounded-3xl bg-bg-surface p-5 text-center ring-1 ring-white/10">
              <motion.p className="text-5xl" animate={{ rotate: [0, -8, 8, 0] }} transition={{ duration: 0.8 }}>
                {run.result === "win" ? "👑" : "💀"}
              </motion.p>
              <p className="mt-1 font-display text-2xl font-black text-ink-chalk">{run.result === "win" ? "Победа в походе!" : "Поход проигран"}</p>
              <p className="text-caption text-ink-mist">Очки: {run.score} · боёв выиграно: {run.battles_won}</p>
              <div className="mt-3 grid grid-cols-3 gap-1.5 text-sm font-bold">
                <span className="flex items-center justify-center gap-1 rounded-xl bg-white/5 py-2 text-ink-chalk">+{run.reward_coins} <IconCoin size={13} /></span>
                <span className={`rounded-xl bg-white/5 py-2 ${run.rating_delta >= 0 ? "text-accent-green" : "text-red-400"}`}>{run.rating_delta >= 0 ? "+" : ""}{run.rating_delta} 📈</span>
                <span className="rounded-xl bg-white/5 py-2 text-amber-200">+{run.xp_gained} опыта</span>
              </div>
              <CasualtiesBlock cas={run.casualties} />
              {run.gold_coins > 0 && <p className="mt-2 text-xs text-amber-200">💰 Золото похода → +{run.gold_coins} монет</p>}
              {run.level_up && <p className="mt-2 rounded-xl bg-fuchsia-500/15 px-3 py-2 text-xs font-bold text-fuchsia-200">⬆️ Новый уровень героя!</p>}
              {run.pack_name && (
                <div className="mt-2 rounded-xl bg-amber-400/10 px-3 py-2 text-xs text-amber-200">
                  🎁 Пак «{run.pack_name}»: {run.pack_cards.map((c) => c.name).join(", ")}
                </div>
              )}
              <div className="mt-4 grid grid-cols-2 gap-2">
                <button onClick={() => navigate("/play/magic")} className="rounded-xl bg-amber-400 py-2.5 text-sm font-bold text-black active:scale-95">Новый поход</button>
                <button onClick={() => setShowResult(false)} className="rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">Посмотреть бой</button>
              </div>
            </motion.section>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
