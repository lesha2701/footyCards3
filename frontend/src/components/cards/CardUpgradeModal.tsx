import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useEffect, useState } from "react";

import { fetchUpgradeRules, upgradeCard } from "@/api/collection";
import { IconBomb, IconChevronRight, IconCoin, IconTrophy, IconUpgrade } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_LABELS } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { CardUpgradeResult, Rarity, UserCard } from "@/types";

type Phase = "pick" | "confirm" | "rolling" | "result";

// Kept in sync with the CSS transition durations below so the reveal always
// lands on a full pulse cycle instead of cutting the animation off mid-beat.
const ROLL_DURATION_MS = 2200;

export default function CardUpgradeModal({ card, onClose }: { card: UserCard; onClose: () => void }) {
  const queryClient = useQueryClient();
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [phase, setPhase] = useState<Phase>("pick");
  const [target, setTarget] = useState<Rarity | null>(null);
  const [result, setResult] = useState<CardUpgradeResult | null>(null);
  const [craftError, setCraftError] = useState<string | null>(null);

  const { data: rules } = useQuery({ queryKey: ["upgrade-rules"], queryFn: fetchUpgradeRules });
  const options = rules?.filter((r) => r.from_rarity === card.player.rarity && r.is_active) ?? [];
  const selectedRule = options.find((r) => r.to_rarity === target);
  const canAfford = !selectedRule || balance >= selectedRule.coin_cost;

  const upgradeMutation = useMutation({
    mutationFn: () => upgradeCard(card.id, target!),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      setResult(data);
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      queryClient.invalidateQueries({ queryKey: ["collection-stats"] });
    },
    onError: (err) => {
      // Without this, a rejected request (e.g. insufficient balance) left
      // `result` unset forever, and the "rolling" animation — which only
      // advances once `result` arrives — would just spin indefinitely.
      hapticNotify("error");
      setCraftError(formatGameError(err, "Не удалось выполнить апгрейд"));
      setPhase("confirm");
    },
  });

  const startUpgrade = () => {
    if (!canAfford) return;
    haptic("medium");
    setCraftError(null);
    setPhase("rolling");
    upgradeMutation.mutate();
  };

  // The mutation can resolve well before the suspense animation has played
  // out, especially on a fast connection — waiting for this timer (instead of
  // switching to "result" as soon as `result` arrives) keeps the intended
  // build-up instead of an instant, anticlimactic flash.
  useEffect(() => {
    if (phase !== "rolling" || !result) return;
    const timer = setTimeout(() => {
      hapticNotify(result.success ? "success" : "error");
      setPhase("result");
    }, ROLL_DURATION_MS);
    return () => clearTimeout(timer);
  }, [phase, result]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
      onClick={() => phase !== "rolling" && onClose()}
    >
      <div
        className="w-full max-w-xs rounded-3xl bg-bg-surface p-5"
        onClick={(e) => e.stopPropagation()}
      >
        {phase === "pick" && (
          <>
            <div className="flex items-center gap-2">
              <IconUpgrade size={18} className="text-accent-lime" />
              <p className="font-display text-base font-bold text-ink-chalk">Апгрейд карточки</p>
            </div>
            <p className="mt-1 text-xs text-ink-mist">
              {card.player.display_name} · {RARITY_LABELS[card.player.rarity]}
            </p>

            {options.length === 0 ? (
              <p className="mt-4 text-sm text-ink-mist">Для этой редкости апгрейд недоступен.</p>
            ) : (
              <div className="mt-4 flex flex-col gap-2">
                {options.map((rule) => {
                  const affordable = balance >= rule.coin_cost;
                  return (
                    <button
                      key={rule.id}
                      onClick={() => { setTarget(rule.to_rarity); setCraftError(null); setPhase("confirm"); }}
                      className="flex items-center justify-between rounded-2xl bg-bg-raised px-4 py-3 text-left active:scale-[0.98]"
                    >
                      <div>
                        <p className="font-display text-sm font-bold text-ink-chalk">{RARITY_LABELS[rule.to_rarity]}</p>
                        <p className="mt-0.5 font-mono text-[11px] text-ink-mist">
                          Шанс {Math.round(rule.success_chance * 100)}%
                        </p>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`flex items-center gap-1 font-mono text-xs ${affordable ? "text-accent-lime" : "text-red-400"}`}>
                          <IconCoin size={12} />
                          {rule.coin_cost}
                        </span>
                        <IconChevronRight size={16} className="text-ink-mist-dim" />
                      </div>
                    </button>
                  );
                })}
              </div>
            )}

            <button onClick={onClose} className="mt-4 w-full rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist">
              Закрыть
            </button>
          </>
        )}

        {phase === "confirm" && selectedRule && (
          <>
            <p className="font-display text-base font-bold text-ink-chalk">Точно рискнуть?</p>
            <p className="mt-2 text-sm text-ink-mist">
              Ты ставишь <b className="text-ink-chalk">{card.player.display_name}</b> ({RARITY_LABELS[card.player.rarity]}) и{" "}
              <span className="inline-flex items-center gap-0.5 font-mono text-accent-lime">
                {selectedRule.coin_cost}<IconCoin size={11} />
              </span>
              . При неудаче (шанс {Math.round((1 - selectedRule.success_chance) * 100)}%) карта и монеты сгорают безвозвратно.
            </p>
            <p className="mt-2 font-mono text-xs text-ink-mist">
              Шанс успеха: <span className="text-accent-cyan">{Math.round(selectedRule.success_chance * 100)}%</span> → {RARITY_LABELS[selectedRule.to_rarity]}
            </p>

            {!canAfford && (
              <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">
                Не хватает монет: нужно {selectedRule.coin_cost}, на балансе {balance}.
              </p>
            )}
            {craftError && (
              <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{craftError}</p>
            )}

            <div className="mt-4 flex gap-2">
              <button
                onClick={() => setPhase("pick")}
                className="flex-1 rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95"
              >
                Назад
              </button>
              <button
                onClick={startUpgrade}
                disabled={!canAfford}
                className="flex-1 rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
              >
                {canAfford ? "Рискнуть" : "Не хватает монет"}
              </button>
            </div>
          </>
        )}

        {phase === "rolling" && selectedRule && (
          <div className="flex flex-col items-center gap-4 py-4 text-center">
            <div className="relative">
              <motion.div
                animate={{ opacity: [0.35, 0.6, 0.35], scale: [1, 1.3, 1] }}
                transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
                className="pointer-events-none absolute inset-0 -z-10 rounded-full bg-floodlight blur-2xl"
              />
              <motion.div
                className={`flex h-32 w-24 items-center justify-center rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[selectedRule.to_rarity]} p-[3px] ${RARITY_GLOW[selectedRule.to_rarity]}`}
                animate={{ rotateY: [0, 180, 360], scale: [1, 1.06, 1] }}
                transition={{ duration: 1.1, repeat: Infinity, ease: "easeInOut" }}
              >
                <div className="flex h-full w-full items-center justify-center rounded-[14px] bg-bg-surface">
                  <motion.div
                    animate={{ rotate: 360 }}
                    transition={{ duration: 1.4, repeat: Infinity, ease: "linear" }}
                  >
                    <IconUpgrade size={30} className="text-accent-lime" />
                  </motion.div>
                </div>
              </motion.div>
            </div>
            <p className="font-display text-base font-bold text-ink-chalk">Куём судьбу...</p>
            <p className="font-mono text-xs text-ink-mist">
              Шанс успеха: <span className="text-accent-cyan">{Math.round(selectedRule.success_chance * 100)}%</span>
            </p>
          </div>
        )}

        {phase === "result" && result && (
          <div className="flex flex-col items-center gap-3 text-center">
            {result.success && result.new_card ? (
              <>
                <div
                  className={`relative flex h-40 w-32 flex-col items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[result.new_card.player.rarity]} p-[3px] ${RARITY_GLOW[result.new_card.player.rarity]}`}
                >
                  <div className="flex h-full w-full flex-col items-center justify-center rounded-[14px] bg-bg-surface">
                    <img
                      src={staticUrl(result.new_card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                      alt={result.new_card.player.display_name}
                      className="h-full w-full object-cover"
                    />
                  </div>
                </div>
                <IconTrophy size={22} className="text-accent-lime" />
                <p className="font-display text-lg font-bold text-ink-chalk">Успех!</p>
                <p className="text-sm text-ink-mist">
                  {result.new_card.player.display_name} · {RARITY_LABELS[result.new_card.player.rarity]}
                </p>
              </>
            ) : (
              <>
                <IconBomb size={36} className="text-red-500" />
                <p className="font-display text-lg font-bold text-ink-chalk">Не повезло</p>
                <p className="text-sm text-ink-mist">Карта и монеты потеряны.</p>
              </>
            )}
            <button onClick={onClose} className="mt-2 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95">
              Готово
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
