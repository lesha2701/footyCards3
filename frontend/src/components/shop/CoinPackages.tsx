import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { createCoinInvoice, fetchCoinInvoiceStatus, fetchCoinPackages } from "@/api/wallet";
import { IconCoin } from "@/components/icons";
import { ApiRequestError } from "@/lib/api";
import { hapticNotify, openTelegramInvoice } from "@/lib/telegram";
import type { CoinPackage } from "@/types";

/** Coin packages for Telegram Stars: invoice → payment sheet → poll until
 * the bot has relayed the payment and the coins are credited. Shared by the
 * shop's "Монеты" tab and the profile's quick-buy modal. */
export function CoinPackagesPanel({
  onPurchased,
  onDone,
}: {
  onPurchased: (newBalance: number) => void;
  onDone?: () => void;
}) {
  const { data: packages, isLoading } = useQuery({ queryKey: ["coin-packages"], queryFn: fetchCoinPackages });
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<{ coins: number; stars: number } | null>(null);

  const handleBuy = async (pkg: CoinPackage) => {
    setError(null);
    setBusyId(pkg.id);
    try {
      const invoice = await createCoinInvoice(pkg.id);
      const paymentStatus = await openTelegramInvoice(invoice.invoice_link);
      if (paymentStatus === "cancelled") {
        setBusyId(null);
        return;
      }
      if (paymentStatus === "failed") {
        setError("Платёж не прошёл");
        setBusyId(null);
        return;
      }

      for (let attempt = 0; attempt < 20; attempt++) {
        const status = await fetchCoinInvoiceStatus(invoice.payload_token);
        if (status.status === "completed" && status.coin_result) {
          hapticNotify("success");
          onPurchased(status.coin_result.new_balance);
          setSuccess({ coins: status.coin_result.coins_credited, stars: pkg.stars_price });
          setBusyId(null);
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      throw new Error("Монеты ещё не начислены — проверь баланс через минуту");
    } catch (err) {
      setError(err instanceof ApiRequestError ? err.message : err instanceof Error ? err.message : "Не удалось купить монеты");
      setBusyId(null);
    }
  };

  if (success) {
    return (
      <div className="flex flex-col gap-3">
        <div className="rounded-2xl bg-accent-green/10 px-4 py-4 text-center">
          <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
            +{success.coins} <IconCoin size={16} />
          </p>
          <p className="mt-1 text-xs text-ink-mist">За {success.stars} ⭐</p>
        </div>
        <button
          onClick={() => (onDone ? onDone() : setSuccess(null))}
          className="w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base active:scale-95"
        >
          Отлично!
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {isLoading && <p className="text-xs text-ink-mist">Загрузка...</p>}
      {!isLoading && !packages?.length && <p className="text-xs text-ink-mist">Пакетов монет пока нет</p>}
      {(packages ?? []).map((pkg) => (
        <button
          key={pkg.id}
          onClick={() => handleBuy(pkg)}
          disabled={busyId !== null}
          className="flex items-center justify-between rounded-2xl bg-black/20 px-4 py-3 text-left disabled:opacity-40"
        >
          <span className="font-mono text-sm font-semibold text-ink-chalk">{pkg.stars_price} ⭐</span>
          <span className="flex items-center gap-1 font-mono text-sm font-bold text-accent-lime">
            {busyId === pkg.id ? "..." : `+${pkg.coins_amount}`}
            <IconCoin size={13} />
          </span>
        </button>
      ))}
    </div>
  );
}

export function BuyCoinsModal({ onClose, onPurchased }: { onClose: () => void; onPurchased: (newBalance: number) => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6" onClick={onClose}>
      <div className="w-full max-w-sm rounded-2xl bg-bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <p className="mb-4 font-display text-base font-bold text-ink-chalk">Купить монеты за ⭐</p>
        <CoinPackagesPanel onPurchased={onPurchased} onDone={onClose} />
        <button onClick={onClose} className="mt-4 w-full rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
          Отмена
        </button>
      </div>
    </div>
  );
}
