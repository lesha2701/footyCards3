import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  feedDiamondCard,
  fetchDiamondMaterialCards,
  fetchDiamondUpgradeCap,
  fetchDiamondUpgradeTiers,
  fetchUpgradeableCards,
} from "@/api/collection";
import { IconChevronRight, IconStar, IconUpgrade } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { RARITY_LABELS } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import type { DiamondMaterialBandKind, FeedCardsResult, Rarity, UserCard } from "@/types";

const MATERIAL_RARITIES: Rarity[] = ["common", "rare", "epic", "legendary"];
const COST_FIELD: Record<Rarity, "common_cost" | "rare_cost" | "epic_cost" | "legendary_cost" | null> = {
  common: "common_cost",
  rare: "rare_cost",
  epic: "epic_cost",
  legendary: "legendary_cost",
  diamond: null,
};

// The two fixed extension bands (above the admin-configured cap) aren't
// rarity-driven — every material card is diamond, so the "choose a rarity"
// step is skipped entirely and this text explains what's needed instead.
const EXTENSION_BAND_LABELS: Record<Exclude<DiamondMaterialBandKind, "admin_tier">, string> = {
  any_diamond: "Любые другие диамантовые карты",
  same_player_diamond: "Только копии именно этой карты",
};

type Phase = "rarity" | "pick" | "confirm" | "result";

export default function DiamondFeedModal({ card, onClose }: { card: UserCard; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<Phase>("rarity");
  const [rarity, setRarity] = useState<Rarity | null>(null);
  const [selected, setSelected] = useState<UserCard[]>([]);
  const [feedError, setFeedError] = useState<string | null>(null);
  const [result, setResult] = useState<FeedCardsResult | null>(null);

  const { data: tiers } = useQuery({ queryKey: ["diamond-upgrade-tiers"], queryFn: fetchDiamondUpgradeTiers });
  const { data: ratingCap } = useQuery({ queryKey: ["diamond-upgrade-cap"], queryFn: fetchDiamondUpgradeCap });
  const { data: band, isLoading: bandLoading } = useQuery({
    queryKey: ["diamond-material-cards", card.id],
    queryFn: () => fetchDiamondMaterialCards(card.id),
  });
  const currentRating = card.player.rating;
  const tier = tiers?.find((t) => t.is_active && t.min_rating <= currentRating && currentRating < t.max_rating);
  const atCap = ratingCap !== undefined && currentRating >= ratingCap;
  const isExtensionBand = !!band && band.kind !== "admin_tier";

  // Extension bands have no rarity to choose (every material card is
  // diamond) — jump straight to picking cards as soon as we know the band.
  useEffect(() => {
    if (isExtensionBand && phase === "rarity") {
      setRarity("diamond");
      setPhase("pick");
    }
  }, [isExtensionBand, phase]);

  const { data: adminTierCards, isLoading: adminTierLoading } = useQuery({
    queryKey: ["upgrade-cards", rarity],
    queryFn: () => fetchUpgradeableCards(rarity!),
    enabled: !!rarity && phase === "pick" && !isExtensionBand,
  });

  const materialCards = isExtensionBand ? band?.cards : adminTierCards;
  const materialLoading = isExtensionBand ? bandLoading : adminTierLoading;

  const cost = isExtensionBand ? band?.cost ?? null : rarity && tier ? tier[COST_FIELD[rarity]!] : null;
  const effectiveCeiling =
    ratingCap !== undefined ? Math.min(ratingCap, isExtensionBand ? band!.ceiling : ratingCap) : undefined;
  const maxGain = effectiveCeiling !== undefined ? Math.max(0, effectiveCeiling - currentRating) : Infinity;
  const gain = cost ? Math.min(Math.floor(selected.length / cost), maxGain) : 0;
  const leftover = cost ? selected.length - gain * cost : 0;

  const toggleCard = (c: UserCard) => {
    setSelected((prev) => (prev.some((s) => s.id === c.id) ? prev.filter((s) => s.id !== c.id) : [...prev, c]));
  };

  const feedMutation = useMutation({
    mutationFn: () => feedDiamondCard(card.id, selected.map((c) => c.id)),
    onSuccess: (data) => {
      hapticNotify("success");
      setResult(data);
      setPhase("result");
      queryClient.invalidateQueries({ queryKey: ["upgrade-cards"] });
      queryClient.invalidateQueries({ queryKey: ["diamond-material-cards"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      queryClient.invalidateQueries({ queryKey: ["collection-stats"] });
    },
    onError: (err) => {
      hapticNotify("error");
      setFeedError(formatGameError(err, "Не удалось скормить карты"));
    },
  });

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm"
      onClick={() => onClose()}
    >
      <div className="w-full max-w-xs rounded-3xl bg-bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center gap-2">
          <IconStar size={18} className="text-rarity-diamond" />
          <p className="font-display text-base font-bold text-ink-chalk">{card.player.display_name}</p>
        </div>
        <p className="mt-1 text-xs text-ink-mist">
          Текущий рейтинг: <b className="text-rarity-diamond">{currentRating}</b>
        </p>

        {atCap && (
          <p className="mt-4 rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">Эта карта уже достигла максимального рейтинга ({ratingCap}).</p>
        )}

        {!atCap && bandLoading && <p className="mt-4 text-xs text-ink-mist">Загрузка...</p>}

        {!atCap && !bandLoading && !isExtensionBand && phase === "rarity" && (
          <>
            <p className="mt-4 text-xs text-ink-mist">Выбери редкость карт, которые скормишь этой карточке:</p>
            <div className="mt-3 flex flex-col gap-2">
              {MATERIAL_RARITIES.map((r) => {
                const rCost = tier ? tier[COST_FIELD[r]!] : null;
                return (
                  <button
                    key={r}
                    disabled={!tier || rCost == null}
                    onClick={() => { setRarity(r); setSelected([]); setPhase("pick"); }}
                    className="flex items-center justify-between rounded-2xl bg-bg-raised px-4 py-3 text-left active:scale-[0.98] disabled:opacity-40"
                  >
                    <p className="font-display text-sm font-bold text-ink-chalk">{RARITY_LABELS[r]}</p>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-ink-mist">{rCost ? `${rCost} шт. → +1` : "недоступно"}</span>
                      <IconChevronRight size={16} className="text-ink-mist-dim" />
                    </div>
                  </button>
                );
              })}
            </div>
            {!tier && (
              <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">
                Апгрейд для текущего рейтинга ({currentRating}) ещё не настроен админом.
              </p>
            )}
            <button onClick={onClose} className="mt-4 w-full rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist">
              Закрыть
            </button>
          </>
        )}

        {!atCap && phase === "pick" && rarity && (
          <>
            <p className="mt-4 text-xs text-ink-mist">
              {isExtensionBand ? EXTENSION_BAND_LABELS[band!.kind as Exclude<DiamondMaterialBandKind, "admin_tier">] : RARITY_LABELS[rarity]}
              {" "}· нужно <b className="text-ink-chalk">{cost}</b> шт. за +1 рейтинг
            </p>
            {materialLoading && <p className="mt-3 text-xs text-ink-mist">Загрузка...</p>}
            {!materialLoading && !materialCards?.length && (
              <p className="mt-3 text-xs text-ink-mist">Нет доступных карт этой редкости.</p>
            )}
            <div className="mt-3 grid max-h-64 grid-cols-4 gap-1.5 overflow-y-auto pr-1">
              {materialCards?.map((c) => {
                const isSelected = selected.some((s) => s.id === c.id);
                return (
                  <button
                    key={c.id}
                    onClick={() => toggleCard(c)}
                    className={`relative rounded-lg ${isSelected ? "ring-2 ring-accent-lime" : ""}`}
                  >
                    <img
                      src={staticUrl(c.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                      alt={c.player.display_name}
                      className="h-14 w-full rounded-lg object-cover"
                    />
                  </button>
                );
              })}
            </div>
            <div className="mt-3 rounded-xl bg-black/20 px-3 py-2 text-xs text-ink-mist">
              Выбрано: <b className="text-ink-chalk">{selected.length}</b> · прирост:{" "}
              <b className="text-rarity-diamond">+{gain}</b>
              {leftover > 0 && <span className="text-ink-mist-dim"> (останется {leftover} без изменений)</span>}
            </div>
            <div className="mt-4 flex gap-2">
              {!isExtensionBand && (
                <button
                  onClick={() => setPhase("rarity")}
                  className="flex-1 rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95"
                >
                  Назад
                </button>
              )}
              {isExtensionBand && (
                <button onClick={onClose} className="flex-1 rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
                  Закрыть
                </button>
              )}
              <button
                onClick={() => { setFeedError(null); setPhase("confirm"); }}
                disabled={gain <= 0}
                className="flex-1 rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
              >
                Далее
              </button>
            </div>
          </>
        )}

        {phase === "confirm" && rarity && (
          <>
            <p className="mt-4 text-sm text-ink-mist">
              Ты скормишь <b className="text-ink-chalk">{gain * (cost ?? 0)}</b> карт (
              {isExtensionBand ? EXTENSION_BAND_LABELS[band!.kind as Exclude<DiamondMaterialBandKind, "admin_tier">] : RARITY_LABELS[rarity]}) и
              получишь <b className="text-rarity-diamond">+{gain}</b> к рейтингу ({currentRating} → {currentRating + gain}). Карты
              будут безвозвратно потрачены.
            </p>
            {feedError && <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{feedError}</p>}
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => setPhase("pick")}
                className="flex-1 rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95"
              >
                Назад
              </button>
              <button
                onClick={() => { haptic("medium"); feedMutation.mutate(); }}
                disabled={feedMutation.isPending}
                className="flex-1 rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
              >
                {feedMutation.isPending ? "..." : "Скормить"}
              </button>
            </div>
          </>
        )}

        {phase === "result" && result && (
          <div className="mt-4 flex flex-col items-center gap-3 text-center">
            <IconUpgrade size={28} className="text-rarity-diamond" />
            <p className="font-display text-lg font-bold text-ink-chalk">
              Рейтинг вырос до {result.diamond_card.player.rating}!
            </p>
            <p className="text-xs text-ink-mist">
              Потрачено карт: {result.cards_consumed}
              {result.cards_returned > 0 && ` · осталось невостребованных: ${result.cards_returned}`}
            </p>
            <button onClick={onClose} className="mt-2 w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95">
              Готово
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
