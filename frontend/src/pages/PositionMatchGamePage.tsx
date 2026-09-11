import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimPositionMatchReward, startPositionMatch, submitPositionMatchAttempt } from "@/api/games";
import { IconCoin, IconShirt, IconTrophy } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { POSITION_LABELS, RARITY_GRADIENTS, RARITY_GLOW } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { PositionMatchCard, PositionMatchClaimResult } from "@/types";

type Phase = "idle" | "playing" | "finished";

const WRONG_FLASH_MS = 700;

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export default function PositionMatchGamePage() {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [phase, setPhase] = useState<Phase>("idle");
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [cards, setCards] = useState<PositionMatchCard[]>([]);
  const [positions, setPositions] = useState<string[]>([]);
  const [maxMistakes, setMaxMistakes] = useState(3);
  const [matchedCardIds, setMatchedCardIds] = useState<Set<number>>(new Set());
  const [matchedPositions, setMatchedPositions] = useState<Set<string>>(new Set());
  const [mistakes, setMistakes] = useState(0);
  const [selectedCardId, setSelectedCardId] = useState<number | null>(null);
  const [wrongFlash, setWrongFlash] = useState<{ cardId: number; position: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [won, setWon] = useState(false);
  const [claimResult, setClaimResult] = useState<PositionMatchClaimResult | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const claimMutation = useMutation({
    mutationFn: () => claimPositionMatchReward(sessionId!),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      setClaimResult(data);
    },
  });

  const startMutation = useMutation({
    mutationFn: startPositionMatch,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setCards(data.cards);
      setPositions(data.positions);
      setMaxMistakes(data.max_mistakes);
      setMatchedCardIds(new Set());
      setMatchedPositions(new Set());
      setMistakes(0);
      setSelectedCardId(null);
      setWrongFlash(null);
      setWon(false);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("playing");
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать игру")),
  });

  const handleCardClick = (cardId: number) => {
    if (busy || matchedCardIds.has(cardId)) return;
    haptic("light");
    setSelectedCardId((prev) => (prev === cardId ? null : cardId));
  };

  const handlePositionClick = async (position: string) => {
    if (busy || matchedPositions.has(position) || selectedCardId === null) return;
    const cardId = selectedCardId;
    setBusy(true);
    haptic("light");
    try {
      const result = await submitPositionMatchAttempt(sessionId!, cardId, position);
      setMistakes(result.mistakes);
      setSelectedCardId(null);

      if (result.correct) {
        haptic("medium");
        setMatchedCardIds((prev) => new Set(prev).add(cardId));
        setMatchedPositions((prev) => new Set(prev).add(position));
        if (result.status === "won") {
          hapticNotify("success");
          setWon(true);
          setPhase("finished");
          claimMutation.mutate();
        }
        setBusy(false);
        return;
      }

      haptic("heavy");
      setWrongFlash({ cardId, position });
      await sleep(WRONG_FLASH_MS);
      setWrongFlash(null);
      if (result.status === "lost") {
        setWon(false);
        setPhase("finished");
        claimMutation.mutate();
      }
      setBusy(false);
    } catch (err) {
      setBusy(false);
      setErrorMsg(formatGameError(err, "Не удалось отправить ответ"));
    }
  };

  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Своя позиция</h1>
        <p className="text-sm text-ink-mist">
          5 случайных футболистов и их позиции — вперемешку. Сопоставь карточку слева с её позицией справа.
          За каждую ошибку награда уменьшается, а если ошибок будет слишком много — раунд проигран.
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
        <IconTrophy size={40} className={won ? "text-accent-lime" : "text-ink-mist-dim"} />
        <p className="font-display text-2xl font-bold text-ink-chalk">
          {won ? "Все позиции угаданы!" : "Слишком много ошибок"}
        </p>
        <p className="text-sm text-ink-mist">Ошибок: {mistakes}</p>

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
          <p className="font-mono text-[10px] uppercase tracking-wide text-ink-mist-dim">Угадано</p>
          <p className="font-display text-lg font-bold text-ink-chalk">{matchedCardIds.size}/{cards.length}</p>
        </div>
        <div className="text-right">
          <p className="font-mono text-[10px] uppercase tracking-wide text-ink-mist-dim">Ошибки</p>
          <p className="font-display text-lg font-bold text-ink-chalk">{mistakes}/{maxMistakes}</p>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-2">
          {cards.map((card) => (
            <CardButton
              key={card.id}
              card={card}
              isMatched={matchedCardIds.has(card.id)}
              isSelected={selectedCardId === card.id}
              isWrong={wrongFlash?.cardId === card.id}
              disabled={busy}
              onClick={() => handleCardClick(card.id)}
            />
          ))}
        </div>

        <div className="flex flex-col gap-2">
          {positions.map((position) => (
            <button
              key={position}
              type="button"
              onClick={() => handlePositionClick(position)}
              disabled={busy || matchedPositions.has(position)}
              className={`flex min-h-[52px] items-center justify-center rounded-xl px-2 text-center text-xs font-semibold transition active:scale-95 disabled:active:scale-100 ${
                matchedPositions.has(position)
                  ? "bg-accent-green/10 text-accent-green opacity-60"
                  : wrongFlash?.position === position
                    ? "bg-red-500/20 text-red-400"
                    : "bg-bg-surface text-ink-chalk"
              }`}
            >
              {POSITION_LABELS[position] ?? position}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function CardButton({
  card,
  isMatched,
  isSelected,
  isWrong,
  disabled,
  onClick,
}: {
  card: PositionMatchCard;
  isMatched: boolean;
  isSelected: boolean;
  isWrong: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || isMatched}
      className={`flex items-center gap-2 rounded-xl p-1.5 pr-2 text-left transition active:scale-95 disabled:active:scale-100 ${
        isMatched ? "opacity-50" : isSelected ? "bg-accent-lime/10 ring-2 ring-accent-lime" : isWrong ? "bg-red-500/10 ring-2 ring-red-500" : "bg-bg-surface"
      }`}
    >
      <div className={`h-10 w-10 shrink-0 overflow-hidden rounded-lg bg-gradient-to-b ${RARITY_GRADIENTS[card.rarity]} ${RARITY_GLOW[card.rarity]} p-[1.5px]`}>
        <div className="h-full w-full overflow-hidden rounded-[7px] bg-bg-surface">
          {card.image_path ? (
            <img src={staticUrl(card.image_path) ?? undefined} alt={card.display_name} className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <IconShirt size={16} className="text-ink-mist-dim" />
            </div>
          )}
        </div>
      </div>
      <span className="truncate text-xs font-semibold text-ink-chalk">{card.display_name}</span>
    </button>
  );
}
