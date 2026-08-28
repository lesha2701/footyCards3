import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { RevealStage, STAGES, STAGE_DURATION_MS } from "@/components/cards/CardRevealStage";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import { IconCoin } from "@/components/icons";
import { openClubPack } from "@/api/clubPacks";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { haptic, hapticNotify } from "@/lib/telegram";
import type { ClubPackOpenResult } from "@/types";

export default function ClubPackOpenPage() {
  const { packId } = useParams<{ packId: string }>();
  const navigate = useNavigate();

  const [phase, setPhase] = useState<"packshot" | "revealing" | "summary">("packshot");
  const [cardIndex, setCardIndex] = useState(0);
  const [stageIndex, setStageIndex] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasStartedRef = useRef(false);
  const idempotencyKeyRef = useRef<string | null>(null);
  if (idempotencyKeyRef.current === null) {
    idempotencyKeyRef.current = `club-pack-${packId}-${crypto.randomUUID()}`;
  }

  const [requestState, setRequestState] = useState<
    { status: "pending" } | { status: "success"; data: ClubPackOpenResult } | { status: "error"; message: string }
  >({ status: "pending" });

  useEffect(() => {
    // Guards against React 18 StrictMode's dev-only double-invoke of effects, same reasoning
    // as PackOpenPage.tsx's identical guard.
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;

    openClubPack(Number(packId), idempotencyKeyRef.current!)
      .then((data) => setRequestState({ status: "success", data }))
      .catch((err: unknown) => {
        setRequestState({
          status: "error",
          message: err instanceof ApiRequestError ? err.message : "Не удалось открыть пак",
        });
      });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const result = requestState.status === "success" ? requestState.data : null;

  const advance = () => {
    if (!result) return;
    haptic("light");
    if (timerRef.current) clearTimeout(timerRef.current);
    if (stageIndex < STAGES.length - 1) setStageIndex((i) => i + 1);
  };

  const nextCard = () => {
    if (!result) return;
    haptic("light");
    if (timerRef.current) clearTimeout(timerRef.current);
    if (cardIndex < result.cards.length - 1) {
      setCardIndex((i) => i + 1);
      setStageIndex(0);
      return;
    }
    hapticNotify("success");
    setPhase("summary");
  };

  useEffect(() => {
    if (phase !== "revealing" || stageIndex >= STAGES.length - 1) return;
    timerRef.current = setTimeout(advance, STAGE_DURATION_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [phase, cardIndex, stageIndex, result]);

  const skipAll = () => {
    if (!result) return;
    if (timerRef.current) clearTimeout(timerRef.current);
    haptic("light");
    setPhase("revealing");
    setCardIndex(result.cards.length - 1);
    setStageIndex(STAGES.length - 1);
  };

  if (requestState.status === "pending") return <LoadingScreen />;
  if (requestState.status === "error") {
    return <ErrorScreen message={requestState.message} onRetry={() => navigate("/clubs/packs")} />;
  }
  if (!result) return null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg-base">
      {phase !== "summary" && (
        <button
          onClick={skipAll}
          className="safe-top absolute right-4 top-4 z-10 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold text-ink-chalk"
        >
          Пропустить всё
        </button>
      )}

      {phase === "packshot" && (
        <button
          onClick={() => { haptic("medium"); setPhase("revealing"); }}
          className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center"
        >
          <motion.img
            src={staticUrl(result.pack.image_path ?? undefined)}
            alt={result.pack.name}
            className="w-52 drop-shadow-2xl"
            animate={{ scale: [1, 1.04, 1], rotate: [0, -1.5, 1.5, 0] }}
            transition={{ repeat: Infinity, duration: 1.6 }}
          />
          <p className="font-display text-xl font-bold text-ink-chalk">{result.pack.name}</p>
          <p className="animate-pulse text-sm text-accent-lime">Нажми, чтобы открыть</p>
        </button>
      )}

      {phase === "revealing" && (
        <div className="flex flex-1 flex-col">
          <RevealStage
            key={`${cardIndex}-${stageIndex}`}
            opened={result.cards[cardIndex]}
            stage={STAGES[stageIndex]}
            index={cardIndex}
            total={result.cards.length}
            onTap={advance}
          />
          {stageIndex === STAGES.length - 1 && (
            <div className="safe-bottom px-6 pb-6 pt-2">
              <button
                onClick={nextCard}
                className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
              >
                {cardIndex < result.cards.length - 1 ? "Следующая карта" : "Готово"}
              </button>
            </div>
          )}
        </div>
      )}

      {phase === "summary" && (
        <div className="safe-bottom flex flex-1 flex-col gap-4 overflow-y-auto px-5 pb-6 pt-16">
          <h2 className="text-center font-display text-2xl font-bold text-ink-chalk">Пак открыт!</h2>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {result.cards.map((oc) => (
              <div key={oc.card.id} className="flex flex-col items-center gap-1 rounded-xl bg-bg-surface p-2">
                <img
                  src={staticUrl(oc.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                  alt={oc.card.player.display_name}
                  className="aspect-square w-full rounded-lg object-cover"
                />
                <span className="truncate text-[10px] font-semibold text-ink-chalk">{oc.card.player.display_name}</span>
                {oc.is_new && <span className="text-[9px] font-bold text-accent-green">Новая!</span>}
              </div>
            ))}
          </div>
          <p className="flex items-center justify-center gap-1 text-sm text-ink-mist-dim">
            Новый бюджет клуба:
            <IconCoin size={14} className="text-accent-lime" />
            <span className="font-mono font-bold text-accent-lime">{result.new_budget}</span>
          </p>
          <button
            onClick={() => navigate("/clubs/packs")}
            className="mt-2 w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
          >
            Готово
          </button>
        </div>
      )}
    </div>
  );
}
