import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState } from "react";

import type { SellDuplicatesResult } from "@/api/collection";
import { IconCoin } from "@/components/icons";
import { RARITY_LABELS, RARITY_ORDER, RARITY_TEXT } from "@/lib/rarity";
import type { Rarity } from "@/types";

/** «Продать дубликаты»: the spares grouped by rarity (common first) with
 * what each group pays; only the ticked rarities are sold. Diamond spares
 * start unticked (they are diamond-upgrade material). */
export default function DuplicateSaleSheet({
  preview, busy, onSell, onClose,
}: {
  preview: SellDuplicatesResult | null;
  busy: boolean;
  onSell: (rarities: Rarity[]) => void;
  onClose: () => void;
}) {
  const rows = Object.entries(preview?.available_by_rarity ?? {})
    .map(([rarity, count]) => ({ rarity: rarity as Rarity, count, coins: preview?.available_coins_by_rarity?.[rarity] ?? 0 }))
    .filter((r) => r.count > 0)
    .sort((a, b) => RARITY_ORDER[a.rarity] - RARITY_ORDER[b.rarity]);
  const [picked, setPicked] = useState<Rarity[]>([]);
  useEffect(() => {
    setPicked(rows.filter((r) => r.rarity !== "diamond").map((r) => r.rarity));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [preview]);

  const chosen = rows.filter((r) => picked.includes(r.rarity));
  const count = chosen.reduce((s, r) => s + r.count, 0);
  const coins = chosen.reduce((s, r) => s + r.coins, 0);
  const toggle = (rarity: Rarity) =>
    setPicked((p) => (p.includes(rarity) ? p.filter((r) => r !== rarity) : [...p, rarity]));

  return (
    <AnimatePresence>
      {preview && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
        >
          <motion.div
            initial={{ y: 40 }}
            animate={{ y: 0 }}
            exit={{ y: 40 }}
            onClick={(e) => e.stopPropagation()}
            className="w-full max-w-md rounded-t-3xl bg-bg-surface p-5 pb-[calc(1.5rem+env(safe-area-inset-bottom,0px))] sm:rounded-3xl"
          >
            <p className="font-display text-lg font-bold text-ink-chalk">Продать дубликаты</p>
            <p className="mb-3 mt-0.5 text-caption text-ink-mist">
              Отметь, какие редкости продать. По одной карточке каждого игрока остаётся; с навыком, в составах, в обменах
              и под замком не продаются.
            </p>
            <div className="flex flex-col gap-1.5">
              {rows.map((r) => {
                const on = picked.includes(r.rarity);
                return (
                  <button
                    key={r.rarity}
                    onClick={() => toggle(r.rarity)}
                    aria-pressed={on}
                    className={`flex items-center gap-3 rounded-2xl px-3 py-2.5 text-left active:scale-[0.98] ${
                      on ? "bg-accent-lime/10 ring-1 ring-accent-lime/40" : "bg-white/5"
                    }`}
                  >
                    <span
                      className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-micro font-bold ${
                        on ? "bg-accent-lime text-bg-base" : "bg-white/10 text-transparent"
                      }`}
                    >
                      ✓
                    </span>
                    <span className={`flex-1 text-sm font-bold ${RARITY_TEXT[r.rarity]}`}>{RARITY_LABELS[r.rarity]}</span>
                    <span className="text-xs text-ink-mist">{r.count} шт.</span>
                    <span className="flex w-20 items-center justify-end gap-1 font-mono text-xs font-bold text-accent-lime">
                      +{r.coins.toLocaleString("ru-RU")} <IconCoin size={11} />
                    </span>
                  </button>
                );
              })}
            </div>
            {picked.includes("diamond") && (
              <p className="mt-2 text-caption text-amber-300">Диамантовые дубликаты — материал для прокачки диамантов.</p>
            )}
            <button
              onClick={() => onSell(picked)}
              disabled={busy || count === 0}
              className="mt-4 w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
            >
              {busy ? "Продаём..." : count ? `Продать ${count} шт. за ${coins.toLocaleString("ru-RU")} монет` : "Выбери редкость"}
            </button>
            <button onClick={onClose} className="mt-2 w-full py-1.5 text-xs text-ink-mist">
              Отмена
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
