import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import { claimFreeKickReward, kickFreeKick, startFreeKick } from "@/api/games";
import CardPickerModal from "@/components/cards/CardPickerModal";
import { IconCheck, IconClose, IconCoin, IconFlagCheckered, IconTarget, type IconProps } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { FreeKickNextKick } from "@/types";

type Phase = "pick_card" | "playing" | "finished";

const TIER: Record<string, { label: string; Icon: (props: IconProps) => JSX.Element; className: string }> = {
  perfect: { label: "Идеально!", Icon: IconTarget, className: "text-accent-lime" },
  good: { label: "Хорошо", Icon: IconCheck, className: "text-accent-cyan" },
  ok: { label: "Норм", Icon: IconCheck, className: "text-ink-mist" },
  miss: { label: "Мимо", Icon: IconClose, className: "text-ink-mist" },
};

export default function FreeKickGamePage() {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("pick_card");
  const [kick, setKick] = useState<FreeKickNextKick | null>(null);
  const [position, setPosition] = useState(50);
  const [lastResult, setLastResult] = useState<{ tier: string; coins: number } | null>(null);
  const [totalCoins, setTotalCoins] = useState(0);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const localStartRef = useRef(0);
  const rafRef = useRef<number | null>(null);

  const { data: collection } = useQuery({
    queryKey: ["collection", "free-kick"],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc" }),
  });

  const startMutation = useMutation({
    mutationFn: startFreeKick,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setKick(data.kick);
      setTotalCoins(0);
      setLastResult(null);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("playing");
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать игру")),
  });

  const kickMutation = useMutation({
    mutationFn: (elapsedMs: number) => kickFreeKick(sessionId!, elapsedMs),
    onSuccess: (result) => {
      haptic(result.tier === "miss" ? "light" : "medium");
      setLastResult({ tier: result.tier, coins: result.coins_this_kick });
      setTotalCoins(result.total_coins);
      if (result.is_finished) {
        hapticNotify("success");
        setPhase("finished");
      } else {
        setKick(result.next_kick);
      }
    },
  });

  const claimMutation = useMutation({
    mutationFn: () => claimFreeKickReward(sessionId!),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      setClaimResult(data);
    },
  });

  useEffect(() => {
    if (!kick || phase !== "playing") return;
    localStartRef.current = performance.now();

    const tick = () => {
      const elapsed = performance.now() - localStartRef.current;
      setPosition(50 + 50 * Math.sin((2 * Math.PI * elapsed) / kick.period_ms));
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [kick, phase]);

  const takeShot = () => {
    if (!kick || kickMutation.isPending) return;
    const elapsedMs = Math.round(performance.now() - localStartRef.current);
    kickMutation.mutate(elapsedMs);
  };

  if (phase === "pick_card") {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Штрафной удар</h1>
        <p className="text-sm text-ink-mist">
          Останови шкалу в нужный момент. Чем выше рейтинг выбранного игрока, тем шире зона точного удара.
        </p>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <CardPickerModal
          open
          title="Выбери игрока"
          cards={collection?.items ?? []}
          onSelect={(card) => startMutation.mutate(card.id)}
          onClose={() => navigate("/play")}
        />
      </div>
    );
  }

  if (phase === "finished") {
    return (
      <div className="flex flex-col items-center gap-5 py-10 text-center">
        <IconFlagCheckered size={40} className="text-ink-mist" />
        <p className="font-display text-2xl font-bold text-ink-chalk">Серия завершена</p>
        <p className="text-sm text-ink-mist">
          Итог: <span className="inline-flex items-center gap-1 font-mono font-bold text-accent-lime">{totalCoins}<IconCoin size={14} /></span>
        </p>

        {!claimResult ? (
          <button
            onClick={() => claimMutation.mutate()}
            disabled={claimMutation.isPending || totalCoins === 0}
            className="rounded-2xl bg-floodlight px-6 py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
          >
            {claimMutation.isPending ? "Начисление..." : totalCoins > 0 ? "Забрать награду" : "Нечего забирать"}
          </button>
        ) : (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              +{claimResult.reward_coins}
              <IconCoin size={16} />
            </p>
          </div>
        )}

        <div className="flex gap-3">
          <button onClick={() => setPhase("pick_card")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Ещё раз
          </button>
          <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Назад
          </button>
        </div>
      </div>
    );
  }

  const halfWidth = kick?.half_width ?? 8;

  return (
    <div className="flex flex-col items-center gap-6 py-6">
      <p className="text-sm text-ink-mist">
        Удар {(kick?.kick_index ?? 0) + 1} / 3 · Всего: <span className="inline-flex items-center gap-1 font-mono font-bold text-accent-lime">{totalCoins}<IconCoin size={13} /></span>
      </p>

      <div className="relative h-6 w-full max-w-xs rounded-full bg-white/5">
        <div
          className="absolute top-0 h-full rounded-full bg-accent-green/25"
          style={{ left: `${50 - halfWidth}%`, width: `${halfWidth * 2}%` }}
        />
        <div
          className="absolute top-0 h-full w-1.5 rounded-full bg-floodlight"
          style={{ left: `calc(${position}% - 3px)` }}
        />
      </div>

      <AnimatePresence mode="wait">
        {lastResult && (
          <motion.div
            key={lastResult.tier + totalCoins}
            initial={{ scale: 0.85, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ opacity: 0 }}
            className="flex flex-col items-center gap-1.5 rounded-2xl bg-bg-surface px-6 py-3 text-center"
          >
            {(() => {
              const tier = TIER[lastResult.tier];
              const TierIcon = tier.Icon;
              return (
                <>
                  <TierIcon size={22} className={tier.className} />
                  <p className="font-display text-lg font-bold text-ink-chalk">{tier.label}</p>
                </>
              );
            })()}
            {lastResult.coins > 0 && (
              <p className="flex items-center gap-1 font-mono text-sm text-accent-lime">
                +{lastResult.coins}
                <IconCoin size={12} />
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <button
        onClick={takeShot}
        disabled={kickMutation.isPending}
        className="rounded-2xl bg-floodlight px-8 py-4 font-display text-lg font-bold text-bg-base active:scale-90 disabled:opacity-40"
      >
        Ударить
      </button>
    </div>
  );
}
