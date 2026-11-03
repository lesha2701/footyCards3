import { useState } from "react";

import { freeStarsDelivery } from "@/api/adminStars";
import { useAdminPayStore } from "@/store/adminPayStore";

/** For an admin, every Stars purchase stops here first: pay with Stars as
 * usual, take it free, or gift it free to another player (id, Telegram id or
 * @username). Free grants go through the server's real delivery and never
 * count as Stars revenue. */
export default function AdminPaySheet() {
  const { token, close } = useAdminPayStore();
  const [recipient, setRecipient] = useState("");
  const [gift, setGift] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  if (!token) return null;

  const finish = (choice: Parameters<typeof close>[0]) => {
    setRecipient(""); setGift(false); setError(null); setDone(null);
    close(choice);
  };
  const free = async () => {
    if (gift && !recipient.trim()) {
      setError("Укажи игрока");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const out = await freeStarsDelivery(token, gift ? recipient.trim() : null);
      if (gift) setDone(`Подарено: ${out.recipient_name} (id ${out.recipient_id}), ${out.stars} ⭐`);
      else finish("paid");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не получилось");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[90] flex items-end justify-center bg-black/60 p-3" onClick={() => !busy && finish(done ? "gifted" : "cancelled")}>
      <div className="flex w-full max-w-md flex-col gap-2 rounded-3xl bg-bg-surface p-4" onClick={(e) => e.stopPropagation()} data-testid="admin-pay-sheet">
        <p className="font-display text-base font-bold text-ink-chalk">👑 Покупка за звёзды · админ</p>
        {done ? (
          <>
            <p className="rounded-xl bg-accent-green/15 px-3 py-2 text-sm text-accent-green">{done}</p>
            <button onClick={() => finish("gifted")} className="rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-chalk">Готово</button>
          </>
        ) : (
          <>
            <div className="grid grid-cols-2 gap-2">
              <button onClick={() => setGift(false)} className={`rounded-xl py-2 text-sm font-bold ${!gift ? "bg-accent-lime/20 text-accent-lime ring-1 ring-accent-lime" : "bg-bg-raised text-ink-mist"}`}>
                Себе
              </button>
              <button onClick={() => setGift(true)} className={`rounded-xl py-2 text-sm font-bold ${gift ? "bg-accent-lime/20 text-accent-lime ring-1 ring-accent-lime" : "bg-bg-raised text-ink-mist"}`}>
                🎁 Подарить
              </button>
            </div>
            {gift && (
              <input value={recipient} onChange={(e) => { setRecipient(e.target.value); setError(null); }} placeholder="id, Telegram id или @username"
                className="rounded-xl bg-bg-raised px-3 py-2.5 text-sm text-ink-chalk outline-none" />
            )}
            {error && <p className="text-caption text-red-400">{error}</p>}
            <button disabled={busy} onClick={() => void free()} className="rounded-2xl bg-floodlight py-3 font-display text-base font-bold text-bg-base disabled:opacity-50">
              {busy ? "Выдаю…" : gift ? "Подарить бесплатно" : "Получить бесплатно"}
            </button>
            {!gift && (
              <button disabled={busy} onClick={() => finish("pay")} className="rounded-2xl bg-amber-400/15 py-2.5 text-sm font-semibold text-amber-300">
                Оплатить звёздами как игрок
              </button>
            )}
            <button disabled={busy} onClick={() => finish("cancelled")} className="py-1 text-caption text-ink-mist">Отмена</button>
          </>
        )}
      </div>
    </div>
  );
}
