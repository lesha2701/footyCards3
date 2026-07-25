import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { RevealStage, STAGES, STAGE_DURATION_MS } from "@/components/cards/CardRevealStage";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import { openPack } from "@/api/packs";
import { ApiRequestError, staticUrl } from "@/lib/api";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_LABELS } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { PackOpenResult } from "@/types";

export default function PackOpenPage() {
  const { packId } = useParams<{ packId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  // Present when arriving with an already-claimed result (e.g. the free pack) so we skip re-opening it.
  const prefetchedResult = (location.state as { result?: PackOpenResult } | null)?.result ?? null;

  const [phase, setPhase] = useState<"packshot" | "revealing" | "summary">("packshot");
  const [cardIndex, setCardIndex] = useState(0);
  const [stageIndex, setStageIndex] = useState(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hasStartedRef = useRef(false);
  // Lazily initialized once via the ref-during-render pattern, which (unlike
  // useMemo) is guaranteed stable across React 18 StrictMode's dev-only
  // double-render/double-effect replay — so a duplicate invocation reuses the
  // same idempotency key and the backend's dedup logic returns the original
  // result instead of charging the player twice.
  const idempotencyKeyRef = useRef<string | null>(null);
  if (idempotencyKeyRef.current === null) {
    idempotencyKeyRef.current = `pack-${packId}-${crypto.randomUUID()}`;
  }
  const idempotencyKey = idempotencyKeyRef.current;

  // A plain useState/useEffect (rather than TanStack Query's useMutation) for
  // this fire-once-on-mount request: useMutation's result is delivered via an
  // internal observer subscription that is itself wired up in a useEffect, and
  // that subscription can be torn down and rebuilt by React 18 StrictMode's
  // dev-only double-invoke of effects independently of the in-flight request —
  // so the resolved data can arrive after the *new* subscription replaces the
  // one the pending request's promise chain was going to notify, leaving the
  // UI stuck on the loading state even though the purchase completed. Local
  // state sidesteps that lifecycle entirely.
  const [requestState, setRequestState] = useState<
    { status: "pending" } | { status: "success"; data: PackOpenResult } | { status: "error"; message: string }
  >(prefetchedResult ? { status: "success", data: prefetchedResult } : { status: "pending" });

  useEffect(() => {
    if (prefetchedResult) return;
    // Guards against React 18 StrictMode's dev-only double-invoke of effects
    // (mount → cleanup → mount) firing this purchase twice; the ref persists
    // across that replay since it isn't reset by the cleanup function.
    if (hasStartedRef.current) return;
    hasStartedRef.current = true;

    openPack(Number(packId), idempotencyKey)
      .then((data) => {
        updateBalance(data.new_balance);
        setRequestState({ status: "success", data });
      })
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

    if (stageIndex < STAGES.length - 1) {
      setStageIndex((i) => i + 1);
    }
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
    if (timerRef.current) clearTimeout(timerRef.current);
    hapticNotify("success");
    setPhase("summary");
  };

  if (requestState.status === "pending") return <LoadingScreen />;
  if (requestState.status === "error") {
    return <ErrorScreen message={requestState.message} onRetry={() => navigate("/packs")} />;
  }
  if (!result) return null;

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg-base">
      {phase !== "summary" && (
        <button
          onClick={skipAll}
          className="safe-top absolute right-4 top-4 z-10 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold text-slate-200"
        >
          Пропустить всё
        </button>
      )}

      {phase === "packshot" && (
        <PackShot pack={result.pack} onOpen={() => { haptic("medium"); setPhase("revealing"); }} />
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
                className="w-full rounded-2xl bg-accent py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
              >
                {cardIndex < result.cards.length - 1 ? "Следующая карта" : "Готово"}
              </button>
            </div>
          )}
        </div>
      )}

      {phase === "summary" && <Summary result={result} onDone={() => navigate("/collection")} />}
    </div>
  );
}

function PackShot({ pack, onOpen }: { pack: PackOpenResult["pack"]; onOpen: () => void }) {
  return (
    <button onClick={onOpen} className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center">
      <motion.img
        src={staticUrl(pack.image_path ?? undefined)}
        alt={pack.name}
        className="w-52 drop-shadow-2xl"
        animate={{ scale: [1, 1.04, 1], rotate: [0, -1.5, 1.5, 0] }}
        transition={{ repeat: Infinity, duration: 1.6 }}
      />
      <p className="font-display text-xl font-bold text-slate-100">{pack.name}</p>
      <p className="animate-pulse text-sm text-accent">Нажми, чтобы открыть</p>
    </button>
  );
}

function Summary({ result, onDone }: { result: PackOpenResult; onDone: () => void }) {
  return (
    <div className="safe-bottom flex flex-1 flex-col gap-4 overflow-y-auto px-5 pb-6 pt-16">
      <h2 className="text-center font-display text-2xl font-bold text-slate-100">Пак открыт!</h2>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {result.cards.map((opened) => (
          <div
            key={opened.card.id}
            className={`relative overflow-hidden rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[opened.card.player.rarity]} p-[2px] ${RARITY_GLOW[opened.card.player.rarity]}`}
          >
            <div className="flex flex-col rounded-[14px] bg-bg-surface">
              <img
                src={staticUrl(opened.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                alt={opened.card.player.display_name}
                className="aspect-square w-full object-cover"
              />
              <div className="p-2 text-center">
                <p className="truncate text-xs font-bold text-slate-100">{opened.card.player.display_name}</p>
                <p className="text-[10px] text-slate-400">{RARITY_LABELS[opened.card.player.rarity]}</p>
                {opened.card.player.collection_name && (
                  <p className="truncate text-[9px] font-semibold text-amber-400">🏷️ {opened.card.player.collection_name}</p>
                )}
              </div>
            </div>
            {opened.is_new && (
              <span className="absolute left-1 top-1 rounded-full bg-emerald-500 px-1.5 py-0.5 text-[9px] font-bold text-white">NEW</span>
            )}
            {opened.duplicate_count > 1 && (
              <span className="absolute right-1 top-1 rounded-full bg-black/70 px-1.5 py-0.5 text-[9px] font-bold text-white">
                ×{opened.duplicate_count}
              </span>
            )}
          </div>
        ))}
      </div>
      <button onClick={onDone} className="mt-2 rounded-2xl bg-accent py-3.5 font-display text-base font-bold text-bg-base active:scale-95">
        Готово
      </button>
    </div>
  );
}
