import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimPairsReward, flipPairsCard, startPairs } from "@/api/games";
import { IconCard, IconCoin, IconTrophy } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { RARITY_GRADIENTS, RARITY_GLOW } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { PairsCard, PairsClaimResult } from "@/types";

type Phase = "idle" | "playing" | "finished";

const MISMATCH_DELAY_MS = 900;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function PairsGamePage() {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [phase, setPhase] = useState<Phase>("idle");
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [boardSize, setBoardSize] = useState(25);
  const [totalPairs, setTotalPairs] = useState(12);
  const [visibleCards, setVisibleCards] = useState<Map<number, PairsCard>>(new Map());
  const [matchedPositions, setMatchedPositions] = useState<Set<number>>(new Set());
  const [wrongAttempts, setWrongAttempts] = useState(0);
  const [matchedPairs, setMatchedPairs] = useState(0);
  const [busy, setBusy] = useState(false);
  const [claimResult, setClaimResult] = useState<PairsClaimResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const claimMutation = useMutation({
    mutationFn: () => claimPairsReward(sessionId!),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      setClaimResult(data);
    },
  });

  const startMutation = useMutation({
    mutationFn: startPairs,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setBoardSize(data.board_size);
      setTotalPairs(data.total_pairs);
      setVisibleCards(new Map());
      setMatchedPositions(new Set());
      setWrongAttempts(0);
      setMatchedPairs(0);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("playing");
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать игру")),
  });

  const handleTileClick = async (position: number) => {
    if (busy || matchedPositions.has(position) || visibleCards.has(position)) return;
    setBusy(true);
    haptic("light");
    try {
      const result = await flipPairsCard(sessionId!, position);
      setWrongAttempts(result.wrong_attempts);
      setMatchedPairs(result.matched_pairs);
      setVisibleCards((prev) => {
        const next = new Map(prev);
        result.revealed.forEach((c) => next.set(c.position, c));
        return next;
      });

      if (result.matched === null) {
        setBusy(false);
        return;
      }

      if (result.matched) {
        haptic("medium");
        setMatchedPositions((prev) => {
          const next = new Set(prev);
          result.revealed.forEach((c) => next.add(c.position));
          return next;
        });
        if (result.status === "won") {
          hapticNotify("success");
          setPhase("finished");
          claimMutation.mutate();
        }
        setBusy(false);
        return;
      }

      haptic("heavy");
      const toHide = result.revealed.map((c) => c.position);
      await sleep(MISMATCH_DELAY_MS);
      setVisibleCards((prev) => {
        const next = new Map(prev);
        toHide.forEach((p) => next.delete(p));
        return next;
      });
      setBusy(false);
    } catch (err) {
      setBusy(false);
      setErrorMsg(formatGameError(err, "Не удалось перевернуть карточку"));
    }
  };

  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Найди пару</h1>
        <p className="text-sm text-ink-mist">
          Поле 5×5. Переворачивай по две карточки и ищи одинаковых футболистов. Среди карт спрятана одна особая —
          она приносит бонус монет, если её найти.
        </p>

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <button
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {startMutation.isPending ? "Загрузка..." : "Начать игру"}
        </button>
      </div>
    );
  }

  if (phase === "finished") {
    return (
      <div className="flex flex-col items-center gap-5 py-6 text-center">
        <IconTrophy size={40} className="text-accent-lime" />
        <p className="font-display text-2xl font-bold text-ink-chalk">Все пары найдены!</p>
        <p className="text-sm text-ink-mist">Ошибок: {wrongAttempts}</p>

        {claimMutation.isPending ? (
          <p className="text-sm text-ink-mist">Начисление...</p>
        ) : claimResult ? (
          claimResult.reward_coins > 0 ? (
            <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
              <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
                Ты получил +{claimResult.reward_coins}
                <IconCoin size={16} />
              </p>
            </div>
          ) : (
            <p className="text-sm text-ink-mist">Награды нет</p>
          )
        ) : claimMutation.isError ? (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(claimMutation.error, "Не удалось начислить награду")}
          </p>
        ) : null}

        <div className="flex gap-3">
          <button onClick={() => setPhase("idle")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Ещё раз
          </button>
          <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Назад
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between rounded-2xl bg-bg-surface px-4 py-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-wide text-ink-mist-dim">Пары</p>
          <p className="font-display text-lg font-bold text-ink-chalk">{matchedPairs}/{totalPairs}</p>
        </div>
        <div className="text-right">
          <p className="font-mono text-[10px] uppercase tracking-wide text-ink-mist-dim">Ошибки</p>
          <p className="font-display text-lg font-bold text-ink-chalk">{wrongAttempts}</p>
        </div>
      </div>

      <div className="grid grid-cols-5 gap-1.5">
        {Array.from({ length: boardSize }, (_, position) => (
          <Tile
            key={position}
            card={visibleCards.get(position) ?? null}
            isMatched={matchedPositions.has(position)}
            disabled={busy}
            onClick={() => handleTileClick(position)}
          />
        ))}
      </div>
    </div>
  );
}

function Tile({
  card,
  isMatched,
  disabled,
  onClick,
}: {
  card: PairsCard | null;
  isMatched: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  if (!card) {
    return (
      <button
        type="button"
        onClick={onClick}
        disabled={disabled}
        className="flex aspect-square items-center justify-center rounded-xl bg-bg-surface ring-1 ring-white/5 transition active:scale-90 disabled:active:scale-100"
      >
        <IconCard size={16} className="text-ink-mist-dim" />
      </button>
    );
  }

  if (card.is_bonus) {
    return (
      <div className="flex aspect-square items-center justify-center rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 text-lg shadow-glow-legendary">
        ⭐
      </div>
    );
  }

  const player = card.player!;
  return (
    <div
      className={`aspect-square overflow-hidden rounded-xl bg-gradient-to-b ${RARITY_GRADIENTS[player.rarity]} ${RARITY_GLOW[player.rarity]} p-[1.5px] transition-opacity ${
        isMatched ? "opacity-60" : ""
      }`}
    >
      <div className="flex h-full w-full flex-col overflow-hidden rounded-[10px] bg-bg-surface">
        <img
          src={staticUrl(player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
          alt={player.display_name}
          className="h-full w-full object-cover"
        />
      </div>
    </div>
  );
}
