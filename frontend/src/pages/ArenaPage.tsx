import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import CardPickerModal from "@/components/cards/CardPickerModal";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchCollection } from "@/api/collection";
import { fetchActiveLineup, setActiveLineup } from "@/api/lineups";
import { fetchArenaLeaderboard, fetchArenaStats, fetchMatchHistory, playMatch } from "@/api/matches";
import { CATEGORY_LABELS, CATEGORY_POSITIONS, type FormationSlot } from "@/lib/formation";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Match, MatchDifficulty, UserCard } from "@/types";

const DIFFICULTIES: { value: MatchDifficulty; label: string }[] = [
  { value: "easy", label: "Лёгкий" },
  { value: "medium", label: "Средний" },
  { value: "hard", label: "Сложный" },
];

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
  const { data: leaderboard } = useQuery({ queryKey: ["arena-leaderboard"], queryFn: fetchArenaLeaderboard });

  const [pickerSlot, setPickerSlot] = useState<FormationSlot | null>(null);
  const [difficulty, setDifficulty] = useState<MatchDifficulty>("medium");
  const [lastMatch, setLastMatch] = useState<Match | null>(null);
  const [matchError, setMatchError] = useState<string | null>(null);

  const setLineupMutation = useMutation({
    mutationFn: setActiveLineup,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["lineup"] }),
  });

  const playMutation = useMutation({
    mutationFn: () => playMatch(difficulty),
    onSuccess: (match) => {
      setLastMatch(match);
      setMatchError(null);
      if (match.reward_coins > 0) {
        updateBalance((useAuthStore.getState().user?.balance ?? 0) + match.reward_coins);
      }
      hapticNotify(match.result === "win" ? "success" : match.result === "loss" ? "error" : "warning");
      queryClient.invalidateQueries({ queryKey: ["arena-stats"] });
      queryClient.invalidateQueries({ queryKey: ["match-history"] });
      queryClient.invalidateQueries({ queryKey: ["arena-leaderboard"] });
    },
    onError: (err) => setMatchError(formatGameError(err, "Не удалось начать матч")),
  });

  if (lineupLoading) return <ListSkeleton />;

  const usedCardIds = lineup?.slots.filter((s) => s.card).map((s) => s.card!.id) ?? [];

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

  return (
    <div className="flex flex-col gap-5">
      <h1 className="font-display text-2xl font-bold text-slate-100">⚽ Card Arena</h1>

      {stats && (
        <div className="grid grid-cols-4 gap-2 text-center">
          <MiniStat label="П" value={stats.matches_won} />
          <MiniStat label="Н" value={stats.matches_drawn} />
          <MiniStat label="Пор" value={stats.matches_lost} />
          <MiniStat label="Энергия" value={`${stats.match_energy}/${stats.max_energy}`} />
        </div>
      )}

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-display text-base font-bold text-slate-100">Состав 4-3-3</p>
          {lineup?.is_complete && <span className="text-sm font-bold text-amber-300">Сила: {lineup.team_strength}</span>}
        </div>
        <div className="grid grid-cols-3 gap-2">
          {lineup?.slots.map((slot) => {
            const formationSlot = { code: slot.slot_code, category: slot.category as FormationSlot["category"], idealPosition: slot.ideal_position };
            return (
              <button
                key={slot.slot_code}
                onClick={() => setPickerSlot(formationSlot)}
                className="flex flex-col items-center gap-1 rounded-xl bg-black/20 p-2 active:scale-95"
              >
                {slot.card ? (
                  <>
                    <span className="text-lg">👕</span>
                    <span className="truncate text-[10px] font-semibold text-slate-200">{slot.card.player.display_name}</span>
                    <span className="text-[9px] text-amber-300">{slot.card.player.rating}</span>
                  </>
                ) : (
                  <>
                    <span className="text-lg text-slate-600">➕</span>
                    <span className="text-[9px] text-slate-500">{CATEGORY_LABELS[slot.category as FormationSlot["category"]]}</span>
                  </>
                )}
              </button>
            );
          })}
        </div>
      </section>

      {matchError && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{matchError}</p>}

      <section className="flex flex-col gap-3">
        <div className="flex gap-2">
          {DIFFICULTIES.map((d) => (
            <button
              key={d.value}
              onClick={() => setDifficulty(d.value)}
              className={`flex-1 rounded-xl py-2 text-xs font-semibold ${difficulty === d.value ? "bg-accent text-bg-base" : "bg-white/5 text-slate-300"}`}
            >
              {d.label}
            </button>
          ))}
        </div>
        <button
          onClick={() => playMutation.mutate()}
          disabled={!lineup?.is_complete || playMutation.isPending || (stats?.match_energy ?? 1) < 1}
          className="rounded-2xl bg-emerald-500 py-3.5 font-display text-base font-bold text-white active:scale-95 disabled:opacity-40"
        >
          {playMutation.isPending ? "Идёт матч..." : "Играть матч"}
        </button>
      </section>

      {lastMatch && <MatchResultCard match={lastMatch} />}

      <section>
        <p className="mb-2 font-display text-base font-bold text-slate-100">История матчей</p>
        {!history?.length ? (
          <EmptyState icon="⚽" title="Матчей ещё не было" />
        ) : (
          <div className="flex flex-col gap-2">
            {history.slice(0, 5).map((m) => (
              <div key={m.id} className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2 text-sm">
                <span className="text-slate-300">vs {m.opponent_name}</span>
                <span className={`font-bold ${m.result === "win" ? "text-emerald-400" : m.result === "loss" ? "text-red-400" : "text-slate-400"}`}>
                  {m.user_score}:{m.opponent_score}
                </span>
              </div>
            ))}
          </div>
        )}
      </section>

      {!!leaderboard?.length && (
        <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
          <p className="mb-2 font-display text-sm font-bold text-slate-200">🏆 Рейтинг Arena</p>
          <div className="flex flex-col gap-2">
            {leaderboard.slice(0, 5).map((entry, i) => (
              <div key={entry.user_id} className="flex items-center justify-between text-sm">
                <span className="text-slate-300">{i + 1}. {entry.display_name}</span>
                <span className="font-bold text-cyan-300">{entry.arena_rating}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {pickerSlot && (
        <CardPickerModal
          open
          title={`Выбери на позицию ${CATEGORY_LABELS[pickerSlot.category]}`}
          cards={cardsForSlot(pickerSlot)}
          disabledCardIds={usedCardIds}
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
      <p className="font-display text-sm font-bold text-slate-100">{value}</p>
      <p className="text-[10px] text-slate-500">{label}</p>
    </div>
  );
}

function MatchResultCard({ match }: { match: Match }) {
  return (
    <section className="rounded-2xl border border-white/10 bg-bg-surface p-4">
      <p className="text-center font-display text-lg font-bold text-slate-100">
        {match.user_score} : {match.opponent_score}
      </p>
      <p className="text-center text-sm text-slate-400">vs {match.opponent_name}</p>
      <p
        className={`mt-1 text-center font-display text-sm font-bold ${
          match.result === "win" ? "text-emerald-400" : match.result === "loss" ? "text-red-400" : "text-slate-400"
        }`}
      >
        {match.result === "win" ? "Победа!" : match.result === "loss" ? "Поражение" : "Ничья"} · +{match.reward_coins} 🪙
      </p>
      <div className="mt-3 max-h-40 space-y-1 overflow-y-auto text-xs">
        {match.events.map((e, i) => (
          <p key={i} className="text-slate-400">
            <span className="text-slate-500">{e.minute}&apos;</span> {e.description}
          </p>
        ))}
      </div>
    </section>
  );
}
