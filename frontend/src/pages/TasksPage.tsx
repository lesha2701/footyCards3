import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCurrentBingo } from "@/api/bingo";
import { claimTask, claimTaskChest, fetchTasks, rerollTask } from "@/api/tasks";
import EmptyState from "@/components/common/EmptyState";
import RewardModal, { RewardCoins } from "@/components/common/RewardModal";
import { UserBadge } from "@/components/common/UserBadge";
import WeeklyEventStrip from "@/components/home/WeeklyEventStrip";
import {
  IconChat, IconCheck, IconChevronRight, IconClock, IconCoin, IconFire, IconHelp, IconLock, IconPack,
  IconSwap, IconTarget, IconUsers, type IconProps,
} from "@/components/icons";
import { SkillTokenIcon } from "@/components/icons/skills";
import { GrantedRewardModal } from "@/components/rewards/RewardBundleView";
import { ApiRequestError } from "@/lib/api";
import { skillByCode, useSkillCatalog } from "@/lib/cardSkills";
import { chestArt, type ChestArtKind } from "@/lib/chestArt";
import { HalloweenDecor } from "@/components/halloween/HalloweenBanner";
import { useHalloween } from "@/lib/halloween";
import { artOf } from "@/lib/gameArt";
import { RARITY_LABELS, RARITY_TEXT } from "@/lib/rarity";
import { haptic, hapticNotify, openTelegramLink } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Badge, GrantedRewards, Task, TaskChest, TaskTrack } from "@/types";

type Tab = "daily" | "weekly" | "subs";
type Period = Exclude<Tab, "subs">;

export default function TasksPage() {
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  // A claim's reward popup; a subscription opens as a golden chest, maybe with «Свой в клубе».
  const [claimed, setClaimed] = useState<{ coins: number; chest: boolean; badge: Badge | null } | null>(null);
  const [chestReward, setChestReward] = useState<{ rewards: GrantedRewards; kind: ChestKind } | null>(null);
  const [tab, setTab] = useState<Tab>("daily");
  const [claimingAll, setClaimingAll] = useState(false);

  const { data: taskList, isLoading } = useQuery({ queryKey: ["tasks"], queryFn: fetchTasks });
  const chestCount = (track: Period) =>
    (track === "weekly" ? taskList?.weekly_track : taskList?.daily_track)?.chests.length ?? 0;
  const { data: bingo } = useQuery({ queryKey: ["bingo-current"], queryFn: fetchCurrentBingo });
  const fail = (err: unknown, fallback: string) => setError(err instanceof ApiRequestError ? err.message : fallback);

  const claimMutation = useMutation({
    mutationFn: claimTask,
    onSuccess: (data, userTaskId) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      if (data.granted_badge) queryClient.invalidateQueries({ queryKey: ["profile", "me"] });
      if (data.granted_skill_tokens) queryClient.invalidateQueries({ queryKey: ["card-skills"] });
      if (data.granted_pack) {
        // Reuses the same full packshot + per-card reveal animation as a
        // real pack purchase, instead of a bespoke "reward received" popup.
        navigate(`/packs/${data.granted_pack.pack.id}/open`, { state: { result: data.granted_pack } });
      } else {
        const chest = (taskList?.premium ?? []).some((t) => t.user_task_id === userTaskId);
        setClaimed({ coins: data.reward_coins, chest, badge: data.granted_badge ?? null });
      }
    },
    onError: (err) => fail(err, "Не удалось забрать награду"),
  });

  const chestMutation = useMutation({
    mutationFn: ({ track, index }: { track: Period; index: number }) => claimTaskChest(track, index),
    onSuccess: (data, variables) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      setError(null);
      setChestReward({ rewards: data.rewards, kind: chestKind(variables.track, variables.index, chestCount(variables.track)) });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
    },
    onError: (err) => fail(err, "Сундук не открылся"),
  });

  const rerollMutation = useMutation({
    mutationFn: rerollTask,
    onSuccess: () => {
      hapticNotify("success");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
    onError: (err) => fail(err, "Не удалось заменить задание"),
  });

  if (isLoading) return null;

  const daily = taskList?.regular ?? [];
  const weekly = taskList?.weekly ?? [];
  const premium = taskList?.premium ?? [];
  const requiredLeft = premium.filter((t) => t.is_required && !t.is_claimed);
  const readyOf = (list: Task[]) => list.filter((t) => t.is_completed && !t.is_claimed);
  const chestsReady = (track?: TaskTrack | null) => (track?.chests ?? []).filter((c) => c.is_available).length;
  const bingoReady = !!bingo?.all_goals_completed && !bingo.has_claimed;

  const period: Period = tab === "weekly" ? "weekly" : "daily";
  const tasks = period === "daily" ? daily : weekly;
  const track = period === "daily" ? taskList?.daily_track : taskList?.weekly_track;
  const ready = readyOf(tasks);
  // Ready ones rise to the top, claimed ones sink to the bottom.
  const ordered = [...tasks].sort((a, b) => rank(a) - rank(b));

  async function claimAll() {
    // One claim at a time: each is its own locked transaction on the server.
    setClaimingAll(true);
    let coins = 0;
    let balance: number | null = null;
    try {
      for (const task of ready) {
        const res = await claimTask(task.user_task_id);
        coins += res.reward_coins;
        balance = res.new_balance;
      }
      hapticNotify("success");
      setError(null);
      setClaimed({ coins, chest: false, badge: null });
    } catch (err) {
      fail(err, "Не удалось забрать награду");
    } finally {
      if (balance !== null) updateBalance(balance);
      setClaimingAll(false);
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
    }
  }

  const openChest = (index: number) => {
    haptic("medium");
    chestMutation.mutate({ track: period, index });
  };

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconTarget size={20} className="text-accent-lime" />
        Задания
      </h1>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      {requiredLeft.length > 0 && tab !== "subs" && (
        <button
          onClick={() => setTab("subs")}
          className="flex items-center gap-3 rounded-2xl border border-amber-400/60 bg-amber-500/15 px-3 py-2.5 text-left active:scale-[0.98]"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-400/25 text-amber-300">
            <IconChat size={18} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-display text-sm font-bold text-ink-chalk">Обязательно: канал и чат игры</span>
            <span className="block text-caption font-semibold text-amber-300">
              +{requiredLeft.reduce((sum, t) => sum + t.reward_coins, 0).toLocaleString("ru-RU")} монет за подписку
            </span>
          </span>
          <IconChevronRight size={16} className="shrink-0 text-amber-300" />
        </button>
      )}

      <div className="grid grid-cols-3 gap-1.5">
        <TabPill active={tab === "daily"} label="День" count={readyOf(daily).length + chestsReady(taskList?.daily_track)} onClick={() => setTab("daily")} />
        <TabPill
          active={tab === "weekly"}
          label="Неделя"
          count={readyOf(weekly).length + chestsReady(taskList?.weekly_track) + (bingoReady ? 1 : 0)}
          onClick={() => setTab("weekly")}
        />
        <TabPill active={tab === "subs"} label="Подписки" count={readyOf(premium).length} gold onClick={() => setTab("subs")} />
      </div>

      {tab === "subs" ? (
        <SubscriptionsTab
          tasks={premium}
          badge={taskList?.required_badge ?? null}
          pendingId={claimMutation.isPending ? claimMutation.variables : undefined}
          onClaim={(id) => claimMutation.mutate(id)}
        />
      ) : (
        <>
          {track && track.chests.length > 0 && (
            <>
              <ChestHero track={track} period={period} pending={chestMutation.isPending} onOpen={openChest} />
              <ChestRoad track={track} period={period} pendingIndex={chestMutation.isPending ? chestMutation.variables?.index : undefined} onOpen={openChest} />
            </>
          )}

          <section className="flex flex-col gap-2">
            <div className="flex items-center justify-between px-1">
              <p className="font-display text-sm font-bold text-ink-chalk">
                {period === "daily" ? "Задания дня" : "Задания недели"}
              </p>
              {period === "daily" && (taskList?.rerolls_left ?? 0) > 0 && (
                <p className="flex items-center gap-1 text-caption text-ink-mist">
                  <IconSwap size={12} /> Замена: {taskList?.rerolls_left}
                </p>
              )}
            </div>

            {ready.length > 1 && (
              <button
                onClick={claimAll}
                disabled={claimingAll}
                className="w-full rounded-2xl bg-accent py-3 font-display text-sm font-bold text-bg-base shadow-glow active:scale-95 disabled:opacity-50"
              >
                {claimingAll ? "Начисление..." : `Забрать всё (${ready.length})`}
              </button>
            )}

            {!ordered.length ? (
              <EmptyState icon={IconTarget} title="Заданий пока нет" description="Загляните позже" />
            ) : (
              ordered.map((task) => (
                <TaskCard
                  key={task.user_task_id}
                  task={task}
                  isPending={(claimMutation.isPending && claimMutation.variables === task.user_task_id) || claimingAll}
                  canReroll={period === "daily" && (taskList?.rerolls_left ?? 0) > 0 && !task.is_completed}
                  isRerolling={rerollMutation.isPending && rerollMutation.variables === task.user_task_id}
                  onClaim={() => claimMutation.mutate(task.user_task_id)}
                  onGo={() => task.route && navigate(task.route)}
                  onReroll={() => rerollMutation.mutate(task.user_task_id)}
                />
              ))
            )}
          </section>

          {period === "weekly" && bingo?.is_enabled && (
            <section className="flex flex-col gap-2">
              <p className="px-1 font-display text-sm font-bold text-ink-chalk">Общие цели всех игроков</p>
              <WeeklyEventStrip bingo={bingo} />
            </section>
          )}
        </>
      )}

      {claimed && (
        <RewardModal
          title={claimed.chest ? "Сундук подписчика открыт!" : "Награда получена!"}
          subtitle={claimed.chest ? "Спасибо, что с нами! Монеты уже на балансе." : "Задание выполнено, монеты начислены на баланс."}
          hero={claimed.chest ? <img src={chestArt("gold", true)} alt="" className="h-32 w-32 object-contain" /> : undefined}
          items={[
            <RewardCoins key="coins" amount={claimed.coins} />,
            ...(claimed.badge
              ? [
                  <p key="badge" className="flex items-center gap-1.5 text-sm font-semibold text-fuchsia-200">
                    <UserBadge badge={claimed.badge} /> Значок «{claimed.badge.name}» — теперь он у твоего имени
                  </p>,
                ]
              : []),
          ]}
          onClose={() => setClaimed(null)}
        />
      )}
      {chestReward && (
        <GrantedRewardModal
          title="Сундук открыт!"
          granted={chestReward.rewards}
          hero={<img src={chestArt(chestReward.kind, true)} alt="" className="h-32 w-32 object-contain" />}
          onClose={() => setChestReward(null)}
        />
      )}
    </div>
  );
}

function rank(task: Task): number {
  if (task.is_claimed) return 2;
  return task.is_completed ? 0 : 1;
}

function TabPill({
  active, label, count, gold = false, onClick,
}: {
  active: boolean;
  label: string;
  count: number;
  gold?: boolean;
  onClick: () => void;
}) {
  const on = gold ? "bg-amber-400 text-bg-base" : "bg-accent text-bg-base";
  const off = gold ? "bg-amber-500/10 text-amber-300" : "bg-white/5 text-ink-mist";
  return (
    <button onClick={onClick} className={`relative rounded-2xl py-2.5 font-display text-sm font-bold transition active:scale-95 ${active ? on : off}`}>
      {label}
      {count > 0 && (
        <span className="absolute -right-1 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500 px-1 text-micro font-bold text-white ring-2 ring-bg-base">
          {count}
        </span>
      )}
    </button>
  );
}

function useCountdown(iso: string): string {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(id);
  }, []);
  const minutes = Math.max(0, Math.round((new Date(iso).getTime() - now) / 60_000));
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  return days > 0 ? `${days} д ${hours} ч` : `${hours} ч ${minutes % 60} мин`;
}

function chestRewardText(chest: TaskChest): string {
  const coins = `${chest.coins.toLocaleString("ru-RU")} монет`;
  return chest.card_rarity ? `${coins} + ${RARITY_LABELS[chest.card_rarity].toLowerCase()} карта` : coins;
}

type ChestKind = ChestArtKind;

/** Ordinary chests are emerald; the day's last one gold, the week's last one legendary. */
function chestKind(period: Period, index: number, total: number): ChestKind {
  if (index < total - 1) return "emerald";
  return period === "weekly" ? "legend" : "gold";
}

const CHEST_LOOK: Record<ChestKind, { frame: string; text: string; bar: string; glow: string }> = {
  emerald: {
    frame: "border-emerald-400/60 bg-gradient-to-br from-emerald-500/25 via-emerald-900/20 to-bg-surface",
    text: "text-emerald-200", bar: "from-emerald-500 to-emerald-300", glow: "drop-shadow-[0_0_14px_rgba(52,211,153,0.55)]",
  },
  gold: {
    frame: "border-amber-400/70 bg-gradient-to-br from-amber-500/30 via-amber-900/20 to-bg-surface",
    text: "text-amber-200", bar: "from-amber-500 to-amber-300", glow: "drop-shadow-[0_0_16px_rgba(251,191,36,0.6)]",
  },
  legend: {
    frame: "border-fuchsia-400/70 bg-gradient-to-br from-fuchsia-600/30 via-purple-900/30 to-bg-surface",
    text: "text-fuchsia-200", bar: "from-fuchsia-500 to-fuchsia-300", glow: "drop-shadow-[0_0_18px_rgba(217,70,239,0.65)]",
  },
};

const SPOOKY_CHEST_TITLES: Record<ChestKind, string> = {
  emerald: "Склеп с сокровищем",
  gold: "Проклятый сундук",
  legend: "Гроб Легенды",
};

/** The big banner: the next chest the player is heading for. */
function ChestHero({
  track, period, pending, onOpen,
}: {
  track: TaskTrack;
  period: Period;
  pending: boolean;
  onOpen: (index: number) => void;
}) {
  const countdown = useCountdown(track.resets_at);
  const total = track.chests.length;
  // The day heads for its next chest; the week shows its big final one as
  // the goal, unless a smaller one is already ready to open.
  const next =
    track.chests.find((c) => c.is_available) ??
    (period === "weekly" ? [...track.chests].reverse().find((c) => !c.is_claimed) : track.chests.find((c) => !c.is_claimed));
  const kind = chestKind(period, next?.index ?? total - 1, total);
  const look = CHEST_LOOK[kind];
  const max = Math.max(1, track.max_points);
  const { live: spooky, data: hw } = useHalloween();
  const plainTitle = kind === "legend" ? "Легендарный сундук" : kind === "gold" ? "Золотой сундук" : period === "daily" ? "Сундук дня" : "Сундук недели";
  // «🎃 Ночь тыкв»: the chests turn creepy while the event runs.
  const title = spooky ? SPOOKY_CHEST_TITLES[kind] : plainTitle;
  const chestPumpkins = spooky ? (period === "weekly" ? hw?.pumpkins_per_weekly_chest : hw?.pumpkins_per_daily_chest) ?? 0 : 0;

  return (
    <section className={`relative overflow-hidden rounded-3xl border-2 p-4 ${look.frame}${spooky ? " hw-sky" : ""}`}>
      {spooky && <HalloweenDecor dense />}
      <div className="relative flex items-center gap-3">
        <motion.img
          src={chestArt(kind, !next)}
          alt=""
          animate={next?.is_available ? { y: [0, -6, 0], rotate: [0, -5, 5, 0] } : { y: [0, -3, 0] }}
          transition={{ duration: next?.is_available ? 0.9 : 2.6, repeat: Infinity, ease: "easeInOut" }}
          className={`h-28 w-28 shrink-0 object-contain ${look.glow}`}
        />
        <div className="min-w-0 flex-1">
          <p className="font-display text-lg font-bold leading-tight text-ink-chalk">
            {next ? title : spooky ? "Все склепы вскрыты" : "Все сундуки открыты"}
          </p>
          <p className={`text-xs font-semibold ${spooky ? "text-orange-300" : look.text}`}>
            {next ? chestRewardText(next) : spooky ? "Духи вернутся с новыми заданиями" : "Возвращайся за новыми заданиями"}
            {next && chestPumpkins > 0 && ` + ${chestPumpkins} 🎃`}
          </p>
          <div className="mt-2 h-3 overflow-hidden rounded-full border border-white/10 bg-black/40">
            <div
              className={`h-full rounded-full bg-gradient-to-r ${look.bar}`}
              style={{ width: `${Math.min(100, (track.points / max) * 100)}%` }}
            />
          </div>
          <p className="mt-1 flex items-center justify-between font-mono text-micro text-ink-mist">
            <span className="flex items-center gap-1"><IconFire size={11} className="text-amber-400" />{track.points} / {track.max_points}</span>
            <span className="flex items-center gap-1"><IconClock size={11} />{countdown}</span>
          </p>
        </div>
      </div>
      {next?.is_available && (
        <button
          onClick={() => onOpen(next.index)}
          disabled={pending}
          className="mt-3 w-full rounded-2xl bg-amber-400 py-3 font-display text-base font-bold text-bg-base shadow-glow-legendary active:scale-95 disabled:opacity-60"
        >
          {pending ? (spooky ? "Скрипит крышка..." : "Открываем...") : spooky ? "Вскрыть, если не страшно" : "Открыть сундук"}
        </button>
      )}
      {next && !next.is_available && (
        <p className="relative mt-2 pr-8 text-caption text-ink-mist">
          Ещё <b className="text-ink-chalk">{next.points - track.points}</b> очков —{" "}
          {spooky ? "успей до рассвета" : "выполняй задания ниже"}
        </p>
      )}
    </section>
  );
}

/** Every chest of the period as a road: opened, ready (bouncing), locked (dimmed). */
function ChestRoad({
  track, period, pendingIndex, onOpen,
}: {
  track: TaskTrack;
  period: Period;
  pendingIndex?: number;
  onOpen: (index: number) => void;
}) {
  const total = track.chests.length;
  return (
    <div className="relative flex items-start justify-between px-1">
      <div className="absolute left-8 right-8 top-7 h-1 rounded-full bg-white/10" />
      {track.chests.map((chest) => {
        const kind = chestKind(period, chest.index, total);
        const locked = !chest.is_claimed && !chest.is_available;
        return (
          <button
            key={chest.index}
            onClick={() => chest.is_available && onOpen(chest.index)}
            disabled={!chest.is_available || pendingIndex === chest.index}
            aria-label={`Сундук за ${chest.points} очков`}
            className="relative z-10 flex w-16 flex-col items-center"
          >
            <motion.span
              animate={chest.is_available ? { y: [0, -6, 0], scale: [1, 1.06, 1] } : undefined}
              transition={{ duration: 0.8, repeat: Infinity }}
              className="relative"
            >
              <img
                src={chestArt(kind, chest.is_claimed)}
                alt=""
                className={`h-14 w-14 object-contain ${
                  locked ? "opacity-45 grayscale-[60%]" : chest.is_claimed ? "opacity-60" : CHEST_LOOK[kind].glow
                }`}
              />
              {(locked || chest.is_claimed) && (
                <span
                  className={`absolute -bottom-0.5 -right-0.5 flex h-5 w-5 items-center justify-center rounded-full ring-2 ring-bg-base ${
                    chest.is_claimed ? "bg-emerald-500 text-bg-base" : "bg-bg-raised text-ink-mist"
                  }`}
                >
                  {chest.is_claimed ? <IconCheck size={12} /> : <IconLock size={11} />}
                </span>
              )}
            </motion.span>
            <span className={`font-mono text-micro font-bold ${chest.is_available ? "text-amber-300" : "text-ink-mist"}`}>{chest.points}</span>
            {chest.card_rarity && !chest.is_claimed && (
              <span className={`-mt-0.5 text-micro font-semibold ${RARITY_TEXT[chest.card_rarity]}`}>+карта</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Each game keeps its own colour, so the list reads at a glance. */
const ROUTE_TINTS: { prefix: string; card: string; chip: string; bar: string; Icon: (p: IconProps) => JSX.Element }[] = [
  { prefix: "/play/arena", card: "bg-emerald-500/10", chip: "bg-emerald-500/20 text-emerald-200", bar: "bg-emerald-400", Icon: IconTarget },
  { prefix: "/play/memory", card: "bg-sky-500/10", chip: "bg-sky-500/20 text-sky-200", bar: "bg-sky-400", Icon: IconTarget },
  { prefix: "/play/saboteur", card: "bg-rose-500/10", chip: "bg-rose-500/20 text-rose-200", bar: "bg-rose-400", Icon: IconTarget },
  { prefix: "/play/penalty", card: "bg-orange-500/10", chip: "bg-orange-500/20 text-orange-200", bar: "bg-orange-400", Icon: IconTarget },
  { prefix: "/packs", card: "bg-fuchsia-500/10", chip: "bg-fuchsia-500/20 text-fuchsia-200", bar: "bg-fuchsia-400", Icon: IconPack },
  { prefix: "/trades", card: "bg-cyan-500/10", chip: "bg-cyan-500/20 text-cyan-200", bar: "bg-cyan-400", Icon: IconSwap },
  { prefix: "/friends", card: "bg-violet-500/10", chip: "bg-violet-500/20 text-violet-200", bar: "bg-violet-400", Icon: IconUsers },
];
const DEFAULT_TINT = { card: "bg-white/5", chip: "bg-white/10 text-ink-chalk", bar: "bg-accent", Icon: IconTarget };

function tintOf(route: string | null | undefined) {
  return ROUTE_TINTS.find((t) => route?.startsWith(t.prefix)) ?? DEFAULT_TINT;
}

/** The go-button's verb follows where it leads — packs aren't "played". */
function actionLabel(route: string): string {
  if (route.startsWith("/packs")) return "Открыть";
  if (route.startsWith("/trades")) return "Обменять";
  if (route.startsWith("/friends")) return "Пригласить";
  return "Играть";
}

function TaskCard({
  task, isPending, canReroll, isRerolling, onClaim, onGo, onReroll,
}: {
  task: Task;
  isPending: boolean;
  canReroll: boolean;
  isRerolling: boolean;
  onClaim: () => void;
  onGo: () => void;
  onReroll: () => void;
}) {
  const ready = task.is_completed && !task.is_claimed;
  const tint = tintOf(task.route);
  const route = task.route ?? "";
  const art = route.startsWith("/play/") ? artOf(route.slice(6).split("/")[0]) : undefined;
  const progress = Math.min(task.progress, task.target_value);

  return (
    <div
      className={`flex items-center gap-3 rounded-2xl p-2.5 ${
        ready ? "bg-emerald-500/15 shadow-glow ring-2 ring-accent" : tint.card
      } ${task.is_claimed ? "opacity-50" : ""}`}
    >
      {art ? (
        <img src={art} alt="" className="h-14 w-14 shrink-0 rounded-2xl object-cover" />
      ) : (
        <span className={`flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl ${tint.chip}`}>
          <tint.Icon size={26} />
        </span>
      )}

      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 font-display text-sm font-bold leading-tight text-ink-chalk">{task.name}</p>
        {ready ? (
          <p className="mt-0.5 text-caption font-semibold text-emerald-300">Выполнено!</p>
        ) : (
          <>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-black/40">
              <div className={`h-full rounded-full ${tint.bar}`} style={{ width: `${(progress / Math.max(1, task.target_value)) * 100}%` }} />
            </div>
            <p className="mt-1 flex items-center gap-2 text-micro text-ink-mist">
              <span className="font-mono">{progress}/{task.target_value}</span>
              {!!task.points && <span className="flex items-center gap-0.5 font-semibold text-amber-400"><IconFire size={10} />+{task.points}</span>}
              {task.reward_skill_code && !!task.reward_skill_tokens && <TaskSkillReward code={task.reward_skill_code} quantity={task.reward_skill_tokens} />}
            </p>
          </>
        )}
      </div>

      <div className="flex shrink-0 flex-col items-end gap-1">
        {task.is_claimed ? (
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-300">
            <IconCheck size={20} />
          </span>
        ) : ready ? (
          <button
            onClick={onClaim}
            disabled={isPending}
            className="flex items-center gap-1 rounded-xl bg-accent px-3 py-2.5 font-display text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50"
          >
            {isPending ? "..." : task.reward_pack_name ? <><IconPack size={14} />Пак</> : <><IconCoin size={14} />{task.reward_coins}</>}
          </button>
        ) : (
          <>
            <span className="flex items-center gap-0.5 font-mono text-micro font-bold text-amber-300">
              {task.reward_pack_name ? <IconPack size={11} /> : <IconCoin size={11} />}
              {task.reward_pack_name ? "пак" : task.reward_coins}
            </span>
            {task.route && (
              <button onClick={onGo} className={`rounded-xl px-3 py-2 text-xs font-bold active:scale-95 ${tint.chip}`}>
                {actionLabel(task.route)}
              </button>
            )}
          </>
        )}
        {canReroll && (
          <button
            onClick={onReroll}
            disabled={isRerolling}
            aria-label="Заменить задание"
            className="flex items-center gap-0.5 text-micro text-ink-mist active:scale-95 disabled:opacity-50"
          >
            <IconSwap size={11} /> {isRerolling ? "..." : "заменить"}
          </button>
        )}
      </div>
    </div>
  );
}

function SubscriptionsTab({
  tasks, badge, pendingId, onClaim,
}: {
  tasks: Task[];
  badge: Badge | null;
  pendingId?: number;
  onClaim: (id: number) => void;
}) {
  const required = tasks.filter((t) => t.is_required);
  const others = tasks.filter((t) => !t.is_required).sort((a, b) => Number(a.is_claimed) - Number(b.is_claimed));
  const done = required.filter((t) => t.is_claimed).length;
  const allDone = required.length > 0 && done === required.length;
  const [visited, markVisited] = useVisited();

  return (
    <div className="flex flex-col gap-4">
      {required.length > 0 && (
        <section className="relative overflow-hidden rounded-3xl border-2 border-fuchsia-400/70 bg-gradient-to-br from-fuchsia-600/30 via-purple-900/30 to-bg-surface p-4">
          <div className="absolute right-3 top-3"><UnsubscribeInfo /></div>
          <div className="flex items-center gap-3">
            <motion.img
              src={chestArt("legend", allDone)}
              alt=""
              animate={allDone ? undefined : { y: [0, -4, 0], rotate: [0, -3, 3, 0] }}
              transition={{ duration: 2.2, repeat: Infinity, ease: "easeInOut" }}
              className="h-28 w-28 shrink-0 object-contain drop-shadow-[0_0_18px_rgba(217,70,239,0.65)]"
            />
            <div className="min-w-0 flex-1 pr-6">
              <p className="flex items-center gap-1.5 font-display text-lg font-bold leading-tight text-ink-chalk">
                {badge?.image_path && <UserBadge badge={badge} className="!h-7 !w-7" />}
                {badge?.name ?? "Свой в клубе"}
              </p>
              <p className="text-xs font-semibold text-fuchsia-200">
                {required.map((t) => t.reward_coins.toLocaleString("ru-RU")).join(" + ")} монет за подписки
                {badge ? " и значок у имени" : ""}
              </p>
              <div className="mt-2 flex gap-1">
                {required.map((t) => (
                  <span key={t.user_task_id} className={`h-2.5 flex-1 rounded-full ${t.is_claimed ? "bg-fuchsia-300" : "bg-black/40"}`} />
                ))}
              </div>
              <p className="mt-1 flex items-center gap-1 text-micro text-ink-mist">
                {allDone ? (
                  <>Ты свой! {badge && <UserBadge badge={badge} />}</>
                ) : (
                  <>Подписки: {done} из {required.length} — подпишись на канал и чат игры</>
                )}
              </p>
            </div>
          </div>
          <div className="mt-3 flex flex-col gap-2">
            {required.map((task) => (
              <SubscriptionRow
                key={task.user_task_id}
                task={task}
                visited={visited.has(task.user_task_id)}
                isPending={pendingId === task.user_task_id}
                onVisit={() => markVisited(task.user_task_id)}
                onClaim={() => onClaim(task.user_task_id)}
              />
            ))}
          </div>
        </section>
      )}

      {others.length > 0 && (
        <section className="flex flex-col gap-2">
          <div className="flex items-center justify-between px-1">
            <p className="font-display text-sm font-bold text-ink-chalk">Сундуки подписчика</p>
            {required.length === 0 && <UnsubscribeInfo />}
          </div>
          {others.map((task) => (
            <SubscriptionChest
              key={task.user_task_id}
              task={task}
              visited={visited.has(task.user_task_id)}
              isPending={pendingId === task.user_task_id}
              onVisit={() => markVisited(task.user_task_id)}
              onClaim={() => onClaim(task.user_task_id)}
            />
          ))}
        </section>
      )}
    </div>
  );
}

/** Subscriptions the player already opened in Telegram (this device): their
 * button turns into «Открыть сундук». Remembered per viewer only. */
function useVisited(): [Set<number>, (id: number) => void] {
  const KEY = "tasks.subs.visited";
  const [visited, setVisited] = useState<Set<number>>(() => {
    try {
      return new Set(JSON.parse(localStorage.getItem(KEY) ?? "[]") as number[]);
    } catch {
      return new Set();
    }
  });
  const mark = (id: number) =>
    setVisited((prev) => {
      const next = new Set(prev).add(id);
      try {
        localStorage.setItem(KEY, JSON.stringify([...next]));
      } catch {
        // storage unavailable: the button still works for this visit
      }
      return next;
    });
  return [visited, mark];
}

function channelUrl(task: Task): string | null {
  if (task.invite_link) return task.invite_link;
  return task.channel_username ? `https://t.me/${task.channel_username.replace("@", "")}` : null;
}

/** «Подписаться» first; once the channel was opened it becomes «Открыть сундук» (the claim re-checks membership). */
function SubscribeButton({
  task, visited, isPending, onVisit, onClaim, className,
}: {
  task: Task;
  visited: boolean;
  isPending: boolean;
  onVisit: () => void;
  onClaim: () => void;
  className: string;
}) {
  const url = channelUrl(task);
  if (url && !visited) {
    return (
      <button onClick={() => { haptic("light"); openTelegramLink(url); onVisit(); }} className={`${className} border-2 border-amber-300 bg-amber-400/10 text-amber-200`}>
        Подписаться
      </button>
    );
  }
  return (
    <button onClick={onClaim} disabled={isPending} className={`${className} bg-amber-400 text-bg-base shadow-glow-legendary disabled:opacity-50`}>
      {isPending ? "Проверяем..." : "Открыть сундук"}
    </button>
  );
}

function SubscriptionRow({
  task, visited, isPending, onVisit, onClaim,
}: {
  task: Task;
  visited: boolean;
  isPending: boolean;
  onVisit: () => void;
  onClaim: () => void;
}) {
  return (
    <div className="flex items-center gap-3 rounded-2xl bg-black/30 p-2.5">
      <span className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl ${task.is_claimed ? "bg-emerald-500/20 text-emerald-300" : "bg-fuchsia-400/20 text-fuchsia-200"}`}>
        {task.is_claimed ? <IconCheck size={20} /> : <IconChat size={20} />}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-display text-sm font-bold text-ink-chalk">{task.name}</p>
        <p className="flex items-center gap-0.5 text-caption font-bold text-amber-300">
          <IconCoin size={12} />+{task.reward_coins.toLocaleString("ru-RU")}
        </p>
      </div>
      {task.is_claimed ? (
        <span className="text-caption font-bold text-emerald-400">Получено</span>
      ) : (
        <SubscribeButton
          task={task} visited={visited} isPending={isPending} onVisit={onVisit} onClaim={onClaim}
          className="shrink-0 rounded-xl px-3 py-2 text-xs font-bold active:scale-95"
        />
      )}
    </div>
  );
}

/** An ordinary rewarded subscription, shown as a golden chest. */
function SubscriptionChest({
  task, visited, isPending, onVisit, onClaim,
}: {
  task: Task;
  visited: boolean;
  isPending: boolean;
  onVisit: () => void;
  onClaim: () => void;
}) {
  return (
    <div
      className={`flex items-center gap-3 rounded-3xl border p-3 ${
        task.is_claimed ? "border-white/5 bg-bg-surface opacity-60" : "border-amber-400/50 bg-gradient-to-r from-amber-500/20 via-amber-900/10 to-bg-surface"
      }`}
    >
      <motion.img
        src={chestArt("gold", task.is_claimed)}
        alt=""
        animate={task.is_claimed ? undefined : { y: [0, -3, 0] }}
        transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
        className="h-20 w-20 shrink-0 object-contain drop-shadow-[0_0_14px_rgba(251,191,36,0.5)]"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-display text-sm font-bold text-ink-chalk">{task.name}</p>
        <p className="flex items-center gap-1 font-display text-xl font-bold text-amber-300">
          <IconCoin size={18} />+{task.reward_coins.toLocaleString("ru-RU")}
        </p>
        {task.is_claimed ? (
          <p className="flex items-center gap-1 text-caption font-bold text-emerald-400"><IconCheck size={13} /> Сундук открыт</p>
        ) : (
          <SubscribeButton
            task={task} visited={visited} isPending={isPending} onVisit={onVisit} onClaim={onClaim}
            className="mt-1.5 w-full rounded-xl py-2 text-xs font-bold active:scale-95"
          />
        )}
      </div>
    </div>
  );
}

function UnsubscribeInfo() {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Как работают подписки"
        className="flex h-7 w-7 items-center justify-center rounded-full bg-white/10 text-ink-mist"
      >
        <IconHelp size={14} />
      </button>
      {open && (
        <p className="absolute right-0 top-8 z-10 w-64 rounded-xl border border-white/10 bg-bg-base p-3 text-caption text-ink-mist shadow-xl">
          Если после получения награды отписаться — награда спишется с баланса. Подпишись снова, и задание опять
          станет активным: награду можно будет забрать ещё раз.
        </p>
      )}
    </div>
  );
}

function TaskSkillReward({ code, quantity }: { code: string; quantity: number }) {
  const { data: catalog } = useSkillCatalog();
  const skill = skillByCode(catalog?.skills, code);
  return (
    <span className="text-accent-lime">
      <SkillTokenIcon code={code} size={11} className="inline-block align-[-2px]" aria-hidden /> {skill?.name ?? code} ×{quantity}
    </span>
  );
}
