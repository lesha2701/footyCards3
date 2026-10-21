import { useState } from "react";

import { IconCoin } from "@/components/icons";

/** «Сколько паков открыть?»: presets plus any number up to `maxQuantity`,
 * the total for that many and whether the balance covers it. Shared by the
 * shop (coins) and club packs (club budget). Prices are informative — the
 * server charges. */
export default function QuantitySheet({
  name,
  unitPrice,
  total = (q) => unitPrice * q,
  balance,
  maxQuantity,
  presets = [10],
  initialQuantity = 1,
  balanceLabel = "монет",
  note,
  onClose,
  onConfirm,
}: {
  name: string;
  unitPrice: number;
  /** Total for q copies (a bulk discount may make it less than unitPrice × q). */
  total?: (quantity: number) => number;
  balance: number;
  maxQuantity: number;
  presets?: number[];
  initialQuantity?: number;
  /** «монет» or «в бюджете клуба» — what runs short. */
  balanceLabel?: string;
  note?: string;
  onClose: () => void;
  onConfirm: (quantity: number) => void;
}) {
  const [quantityText, setQuantityText] = useState(String(Math.min(initialQuantity, Math.max(1, maxQuantity))));
  const parsed = Math.floor(Number(quantityText));
  const quantity = Number.isFinite(parsed) ? Math.min(Math.max(parsed, 1), maxQuantity) : 0;
  const sum = quantity >= 1 ? total(quantity) : 0;
  const canAfford = balance >= sum;
  const valid = quantity >= 1 && maxQuantity >= 1 && canAfford;
  const options = [1, ...presets.filter((p) => p > 1)];

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60" onClick={onClose}>
      <div role="dialog" aria-label="Сколько открыть" className="safe-bottom w-full max-w-md rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <p className="mb-1 font-display text-base font-bold text-ink-chalk">Сколько открыть?</p>
        <p className="mb-3 flex items-center gap-1 text-xs text-ink-mist">
          «{name}» — <IconCoin size={11} /> {unitPrice.toLocaleString("ru-RU")} за пак
        </p>

        <div className="mb-3 flex gap-2">
          {options.map((preset) => {
            const value = Math.min(preset, maxQuantity);
            return (
              <button
                key={preset}
                onClick={() => setQuantityText(String(value))}
                disabled={maxQuantity < 1 || (preset > maxQuantity && preset !== options[0])}
                className={`flex-1 rounded-xl py-2 text-sm font-semibold active:scale-95 disabled:opacity-30 ${
                  quantity === preset ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"
                }`}
              >
                ×{preset}
              </button>
            );
          })}
        </div>

        <div className="mb-2 flex items-center gap-2">
          <button
            onClick={() => setQuantityText(String(Math.max(1, quantity - 1)))}
            aria-label="Меньше"
            className="h-11 w-11 shrink-0 rounded-xl bg-bg-surface text-lg font-bold text-ink-chalk active:scale-95"
          >
            −
          </button>
          <input
            type="number"
            min={1}
            max={maxQuantity}
            inputMode="numeric"
            aria-label="Количество паков"
            value={quantityText}
            onChange={(e) => setQuantityText(e.target.value)}
            className="h-11 min-w-0 flex-1 rounded-xl bg-bg-surface px-4 text-center font-mono text-base font-bold text-ink-chalk outline-none"
          />
          <button
            onClick={() => setQuantityText(String(Math.min(maxQuantity, quantity + 1)))}
            aria-label="Больше"
            className="h-11 w-11 shrink-0 rounded-xl bg-bg-surface text-lg font-bold text-ink-chalk active:scale-95"
          >
            +
          </button>
        </div>
        <p className="mb-2 text-center text-caption text-ink-mist-dim">
          {note ?? `До ${maxQuantity} за раз`}
        </p>

        <div className="mb-3 flex items-center justify-center gap-1.5 font-mono text-sm font-semibold text-accent-lime">
          <IconCoin size={14} />
          {sum.toLocaleString("ru-RU")}
          {sum < unitPrice * quantity && <s className="text-ink-mist-dim">{(unitPrice * quantity).toLocaleString("ru-RU")}</s>}
          {!canAfford && quantity >= 1 && <span className="font-sans text-red-400">— не хватает {balanceLabel}</span>}
        </div>

        <button
          onClick={() => onConfirm(quantity)}
          disabled={!valid}
          className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40 disabled:grayscale"
        >
          {quantity > 1 ? `Открыть ${quantity}` : "Открыть"}
        </button>
      </div>
    </div>
  );
}
