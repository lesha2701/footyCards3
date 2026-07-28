import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchUpgradeRules, upgradeCard } from "@/api/collection";
import { IconBomb, IconChevronRight, IconCoin, IconTrophy, IconUpgrade } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_LABELS } from "@/lib/rarity";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { CardUpgradeResult, Rarity, UserCard } from "@/types";

type Phase = "pick" | "confirm" | "result";

export default function CardUpgradeModal({ card, onClose }: { card: UserCard; onClose: () => void }) {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [phase, setPhase] = useState<Phase>("pick");
  const [target, setTarget] = useState<Rarity | null>(null);
  const [result, setResult] = useState<CardUpgradeResult | null>(null);

  const { data: rules } = useQuery({ queryKey: ["upgrade-rules"], queryFn: fetchUpgradeRules });
  const options = rules?.filter((r) => r.from_rarity === card.player.rarity && r.is_active) ?? [];
  const selectedRule = options.find((r) => r.to_rarity === target);

  const upgradeMutation = useMutation({
    mutationFn: () => upgradeCard(card.id, target!),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify(data.success ? "success" : "error");
      setResult(data);
      setPhase("result");
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      queryClient.invalidateQueries({ queryKey: ["collection-stats"] });
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm" onClick={onClose}>
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
                {options.map((rule) => (
                  <button
                    key={rule.id}
                    onClick={() => { setTarget(rule.to_rarity); setPhase("confirm"); }}
                    className="flex items-center justify-between rounded-2xl bg-bg-raised px-4 py-3 text-left active:scale-[0.98]"
                  >
                    <div>
                      <p className="font-display text-sm font-bold text-ink-chalk">{RARITY_LABELS[rule.to_rarity]}</p>
                      <p className="mt-0.5 font-mono text-[11px] text-ink-mist">
                        Шанс {Math.round(rule.success_chance * 100)}%
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="flex items-center gap-1 font-mono text-xs text-accent-lime">
                        <IconCoin size={12} />
                        {rule.coin_cost}
                      </span>
                      <IconChevronRight size={16} className="text-ink-mist-dim" />
                    </div>
                  </button>
                ))}
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

            <div className="mt-4 flex gap-2">
              <button
                onClick={() => setPhase("pick")}
                className="flex-1 rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95"
              >
                Назад
              </button>
              <button
                onClick={() => upgradeMutation.mutate()}
                disabled={upgradeMutation.isPending}
                className="flex-1 rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50"
              >
                {upgradeMutation.isPending ? "..." : "Рискнуть"}
              </button>
            </div>
          </>
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
