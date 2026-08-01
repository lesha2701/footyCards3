import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import CardPickerModal from "@/components/cards/CardPickerModal";
import EmptyState from "@/components/common/EmptyState";
import {
  IconBall,
  IconChevronLeft,
  IconChevronRight,
  IconChevronUp,
  IconCoin,
  IconPlus,
  IconShirt,
  type IconProps,
} from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchCollection } from "@/api/collection";
import { fetchActiveLineup, setActiveLineup, setLineupTactic } from "@/api/lineups";
import { fetchArenaStats, fetchMatchHistory, playMatch, shootMatch } from "@/api/matches";
import { CATEGORY_LABELS, CATEGORY_POSITIONS, TACTICS, type FormationSlot } from "@/lib/formation";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Match, MatchPendingShot, MatchResult, ShotDirection, ShotType, UserCard } from "@/types";

const EVENT_STEP_MS = 950;

const DIRECTIONS: { value: ShotDirection; label: string; Icon: (props: IconProps) => JSX.Element }[] = [
  { value: "left", label: "Лево", Icon: IconChevronLeft },
  { value: "center", label: "Центр", Icon: IconChevronUp },
  { value: "right", label: "Право", Icon: IconChevronRight },
];

const SHOT_PROMPTS: Record<ShotType, { user: string; opponent: string }> = {
  in_box: {
    user: "Удар из штрафной! Только вратарь может тебя остановить — выбери, куда пробить.",
    opponent: "Соперник бьёт из штрафной! Выбери, куда прыгнет твой вратарь.",
  },
  long_range: {
    user: "Дальний удар! Защитник соперника может заблокировать — выбери направление.",
    opponent: "Соперник бьёт издали! Твой защитник может помочь — выбери, куда прыгнет вратарь.",
  },
  empty_net: {
    user: "Пустые ворота! Не отправь мяч в трибуны.",
    opponent: "",
  },
};

export default function ArenaPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const { data: lineup, isLoading: lineupLoading } = useQuery({ queryKey: ["lineup"], queryFn: fetchActiveLineup });
  const { data: collectionPage } = useQuery({
    queryKey: ["collection-for-lineup"],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc" }),
  });
  const { data: stats } = useQuery({ queryKey: ["arena-stats"], queryFn: fetchArenaStats });
  const { data: history } = useQuery({ queryKey: ["match-history"], queryFn: fetchMatchHistory });

  const [pickerSlot, setPickerSlot] = useState<FormationSlot | null>(null);
  const [match, setMatch] = useState<Match | null>(null);
  const [matchError, setMatchError] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);

  const setLineupMutation = useMutation({
    mutationFn: setActiveLineup,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["lineup"] }),
  });

  const setTacticMutation = useMutation({
    mutationFn: setLineupTactic,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["lineup"] }),
  });

  const playMutation = useMutation({
    mutationFn: () => playMatch("medium"),
    onSuccess: (data) => {
      setMatch(data);
      setMatchError(null);
      setSimulating(true);
      // Balance, stats and history only update once the simulation finishes
      // playing out (MatchSimulation's onFinished) so the result isn't spoiled.
    },
    onError: (err) => setMatchError(formatGameError(err, "Не удалось начать матч")),
  });

  const shootMutation = useMutation({
    mutationFn: (direction?: ShotDirection) => shootMatch(match!.id, direction),
    onSuccess: (data) => setMatch(data),
  });

  if (lineupLoading) return <ListSkeleton />;

  // A player already fielded in another slot is blocked even via a duplicate
  // card copy (same player, different card id) — one player can't start twice.
  const usedPlayerIds = (pickerSlot
    ? lineup?.slots.filter((s) => s.card && s.slot_code !== pickerSlot.code)
    : lineup?.slots.filter((s) => s.card)
  )?.map((s) => s.card!.player.id) ?? [];

  const cardsForSlot = (slot: FormationSlot): UserCard[] => {
    const positions = CATEGORY_POSITIONS[slot.category];
    return (collectionPage?.items ?? []).filter((c) => positions.includes(c.player.position));
  };

  const assignSlot = async (slot: FormationSlot, card: UserCard) => {
    const currentSlots = (lineup?.slots ?? [])
      .filter((s) => s.card && s.slot_code !== slot.code)
      .map((s) => ({ slot_code: s.slot_code, user_card_id: s.card!.id }));
    currentSlots.push({ slot_code: slot.code, user_card_id: card.id });
    await setLineupMutation.mutateAsync(currentSlots);
    setPickerSlot(null);
  };

  const lastFive = (history ?? []).slice(0, 5).reverse();

  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Card Arena</h1>

      {stats && (
        <div className="grid grid-cols-3 gap-2 text-center">
          <MiniStat label="Рейтинг" value={stats.arena_rating} />
          <MiniStat label="Место в рейтинге" value={stats.arena_rank != null ? `#${stats.arena_rank}` : "—"} />
          <div className="rounded-xl bg-bg-surface py-2">
            <div className="flex items-center justify-center gap-1">
              {lastFive.length ? (
                lastFive.map((m) => <FormBadge key={m.id} result={m.result} />)
              ) : (
                <span className="font-mono text-xs text-ink-mist-dim">—</span>
              )}
            </div>
            <p className="mt-1 text-[10px] text-ink-mist-dim">Форма</p>
          </div>
        </div>
      )}

      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-display text-base font-bold text-ink-chalk">Состав 4-3-3</p>
          {lineup?.is_complete && (
            <span className="font-mono text-sm font-bold text-accent-cyan">Сила: {lineup.team_strength}</span>
          )}
        </div>
        <div className="relative flex flex-col gap-3 overflow-hidden rounded-2xl bg-gradient-to-b from-emerald-950/60 to-emerald-900/30 p-3">
          <div className="pointer-events-none absolute inset-x-3 top-1/2 h-px -translate-y-1/2 bg-white/10" />
          <div className="pointer-events-none absolute left-1/2 top-1/2 h-16 w-16 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/10" />
          {(["FWD", "MID", "DEF", "GK"] as const).map((category) => (
            <div key={category} className="relative flex justify-evenly gap-2">
              {lineup?.slots
                .filter((slot) => slot.category === category)
                .map((slot) => {
                  const formationSlot = { code: slot.slot_code, category: slot.category as FormationSlot["category"], idealPosition: slot.ideal_position };
                  return (
                    <button
                      key={slot.slot_code}
                      onClick={() => setPickerSlot(formationSlot)}
                      className="flex min-w-0 max-w-[84px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95"
                    >
                      {slot.card ? (
                        <>
                          <IconShirt size={18} className="text-accent-cyan" />
                          <span className="max-w-full truncate text-[10px] font-semibold text-ink-chalk">{slot.card.player.display_name}</span>
                          <span className="font-mono text-[9px] text-accent-lime">{slot.card.player.rating}</span>
                        </>
                      ) : (
                        <>
                          <IconPlus size={18} className="text-ink-mist-dim" />
                          <span className="text-[9px] text-ink-mist-dim">{CATEGORY_LABELS[slot.category as FormationSlot["category"]]}</span>
                        </>
                      )}
                    </button>
                  );
                })}
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl bg-bg-surface p-4">
        <p className="mb-3 font-display text-sm font-bold text-ink-chalk">Тактическая схема</p>
        <div className="grid grid-cols-3 gap-2">
          {TACTICS.map((t) => (
            <button
              key={t.value}
              onClick={() => setTacticMutation.mutate(t.value)}
              disabled={setTacticMutation.isPending}
              className={`rounded-xl px-1 py-2 text-center disabled:opacity-60 ${
                lineup?.tactic === t.value ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
              }`}
            >
              <p className="whitespace-nowrap text-[9px] font-bold leading-tight">{t.label}</p>
              <p className={`mt-0.5 whitespace-nowrap text-[8px] leading-tight ${lineup?.tactic === t.value ? "text-bg-base/70" : "text-ink-mist-dim"}`}>
                {t.description}
              </p>
            </button>
          ))}
        </div>
      </section>

      {matchError && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{matchError}</p>}

      <section className="flex flex-col gap-3">
        <button
          onClick={() => playMutation.mutate()}
          disabled={!lineup?.is_complete || playMutation.isPending || simulating}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {playMutation.isPending || simulating ? "Идёт матч..." : "Играть матч"}
        </button>
      </section>

      {match && (
        <MatchSimulation
          key={match.id}
          match={match}
          shootPending={shootMutation.isPending}
          onShoot={(direction) => shootMutation.mutate(direction)}
          onFinished={() => {
            setSimulating(false);
            if (match.reward_coins > 0) {
              updateBalance((useAuthStore.getState().user?.balance ?? 0) + match.reward_coins);
            }
            queryClient.invalidateQueries({ queryKey: ["arena-stats"] });
            queryClient.invalidateQueries({ queryKey: ["match-history"] });
            hapticNotify(match.result === "win" ? "success" : match.result === "loss" ? "error" : "warning");
          }}
        />
      )}

      <section>
        <p className="mb-2 font-display text-base font-bold text-ink-chalk">История матчей</p>
        {!history?.length ? (
          <EmptyState icon={IconBall} title="Матчей ещё не было" />
        ) : (
          <div className="flex flex-col gap-2">
            {history.slice(0, 5).map((m) => (
              <div key={m.id} className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2 text-sm">
                <span className="text-ink-mist">vs {m.opponent_name}</span>
                <span className={`font-mono font-bold ${m.result === "win" ? "text-accent-green" : m.result === "loss" ? "text-red-400" : "text-ink-mist"}`}>
                  {m.user_score}:{m.opponent_score}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {pickerSlot && (
        <CardPickerModal
          open
          title={`Выбери на позицию ${CATEGORY_LABELS[pickerSlot.category]}`}
          cards={cardsForSlot(pickerSlot)}
          disabledCardIds={cardsForSlot(pickerSlot).filter((c) => usedPlayerIds.includes(c.player.id)).map((c) => c.id)}
          onSelect={(card) => assignSlot(pickerSlot, card)}
          onClose={() => setPickerSlot(null)}
        />
      )}
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-xl bg-bg-surface py-2">
      <p className="font-mono text-sm font-bold text-ink-chalk">{value}</p>
      <p className="text-[10px] text-ink-mist-dim">{label}</p>
    </div>
  );
}

function FormBadge({ result }: { result: MatchResult | null }) {
  const letter = result === "win" ? "W" : result === "loss" ? "L" : "D";
  const className =
    result === "win"
      ? "bg-accent-green/20 text-accent-green"
      : result === "loss"
        ? "bg-red-500/20 text-red-400"
        : "bg-white/10 text-ink-mist";
  return (
    <span className={`flex h-5 w-5 items-center justify-center rounded-full font-mono text-[10px] font-bold ${className}`}>
      {letter}
    </span>
  );
}

function MatchSimulation({
  match,
  shootPending,
  onShoot,
  onFinished,
}: {
  match: Match;
  shootPending: boolean;
  onShoot: (direction?: ShotDirection) => void;
  onFinished: () => void;
}) {
  const [revealedCount, setRevealedCount] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const finishedFiredRef = useRef(false);

  const total = match.events.length;
  const caughtUp = revealedCount >= total;
  const isFinished = match.status === "finished";

  useEffect(() => {
    if (caughtUp) {
      if (isFinished && !finishedFiredRef.current) {
        finishedFiredRef.current = true;
        onFinished();
      }
      return;
    }
    timerRef.current = setTimeout(() => {
      if (["goal", "save", "blocked"].includes(match.events[revealedCount]?.event_type)) haptic("medium");
      setRevealedCount((c) => c + 1);
    }, EVENT_STEP_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealedCount, caughtUp, isFinished]);

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: "smooth" });
  }, [revealedCount]);

  const skip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setRevealedCount(total);
  };

  const revealed = match.events.slice(0, revealedCount);
  const currentMinute = revealed.length ? revealed[revealed.length - 1].minute : 0;
  const pendingShot = caughtUp && !isFinished ? match.pending_shot : null;

  // The live score only counts goals among the *revealed* events, so it
  // climbs to the final score in step with the commentary instead of
  // spoiling the outcome the instant the match starts.
  const liveUserScore = revealed.filter((e) => e.event_type === "goal" && e.team === "user").length;
  const liveOpponentScore = revealed.filter((e) => e.event_type === "goal" && e.team === "opponent").length;

  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-ink-mist-dim">
          {caughtUp && isFinished ? "Матч завершён" : `${currentMinute}' · идёт матч...`}
        </span>
        {!caughtUp && (
          <button onClick={skip} className="rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold text-ink-chalk">
            Пропустить
          </button>
        )}
      </div>

      <p className="mt-1 text-center font-mono text-lg font-bold text-ink-chalk">
        {liveUserScore} : {liveOpponentScore}
      </p>
      <p className="text-center text-sm text-ink-mist">vs {match.opponent_name}</p>

      {/* The win/draw/loss verdict and reward stay hidden until the
          simulation actually finishes playing out, even though the live
          score above already tracks along with it. */}
      {caughtUp && isFinished && (
        <p
          className={`mt-1 flex items-center justify-center gap-1 text-center font-display text-sm font-bold ${
            match.result === "win" ? "text-accent-green" : match.result === "loss" ? "text-red-400" : "text-ink-mist"
          }`}
        >
          {match.result === "win" ? "Победа!" : match.result === "loss" ? "Поражение" : "Ничья"} · +{match.reward_coins}
          <IconCoin size={13} />
        </p>
      )}

      <div ref={logRef} className="mt-3 max-h-48 space-y-1 overflow-y-auto text-xs">
        {revealed.map((e, i) => (
          <p key={i} className={e.team === "user" ? "text-accent-green" : "text-ink-mist"}>
            <span className="font-mono text-ink-mist-dim">{e.minute}&apos;</span> {e.description}
          </p>
        ))}
      </div>

      {pendingShot && <ShotPrompt pending={pendingShot} disabled={shootPending} onShoot={onShoot} />}
    </section>
  );
}

function ShotPrompt({
  pending,
  disabled,
  onShoot,
}: {
  pending: MatchPendingShot;
  disabled: boolean;
  onShoot: (direction?: ShotDirection) => void;
}) {
  const prompt = SHOT_PROMPTS[pending.shot_type][pending.team === "user" ? "user" : "opponent"];

  return (
    <div className="mt-4 flex flex-col items-center gap-3 rounded-2xl bg-black/20 p-4 text-center">
      <p className="text-sm font-semibold text-ink-chalk">{prompt}</p>
      {pending.shot_type === "empty_net" ? (
        <button
          onClick={() => onShoot()}
          disabled={disabled}
          className="rounded-2xl bg-floodlight px-8 py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          Ударить!
        </button>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {DIRECTIONS.map((d) => (
            <button
              key={d.value}
              onClick={() => onShoot(d.value)}
              disabled={disabled}
              className="flex flex-col items-center gap-1.5 rounded-2xl bg-bg-surface px-4 py-3 text-sm font-semibold text-ink-chalk active:scale-90 disabled:opacity-40"
            >
              <d.Icon size={16} />
              {d.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
