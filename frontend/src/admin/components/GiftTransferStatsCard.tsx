import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchGiftTransferStats } from "@/admin/api";

/** «Передача подарков»: what passing gifts on for Stars brings. */
export default function GiftTransferStatsCard() {
  const [days, setDays] = useState(30);
  const { data } = useQuery({ queryKey: ["admin-gift-transfer-stats", days], queryFn: () => fetchGiftTransferStats(days) });
  return (
    <section className="rounded-2xl bg-bg-surface p-4" data-testid="admin-gift-transfer-stats">
      <div className="mb-3 flex items-center justify-between gap-2">
        <p className="font-semibold">⭐ Передача подарков</p>
        <div className="flex gap-1">
          {[7, 30, 90].map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`rounded-lg px-2 py-1 text-xs ${days === d ? "bg-floodlight text-bg-base" : "bg-white/5 text-slate-400"}`}
            >
              {d} дн.
            </button>
          ))}
        </div>
      </div>
      {!data ? (
        <p className="text-sm text-slate-400">Загрузка…</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {[
              ["Звёзд", data.stars],
              ["Оплат", data.invoices],
              ["Копий передано", data.copies],
              ["Отправителей", data.senders],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-black/20 p-3">
                <p className="font-mono text-xl font-bold">{Number(value).toLocaleString("ru-RU")}</p>
                <p className="text-xs text-slate-400">{label}</p>
              </div>
            ))}
          </div>
          {data.top_sets.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs text-slate-400">Чаще всего передают</p>
              {data.top_sets.map((s) => (
                <div key={s.name} className="flex justify-between border-b border-white/5 py-1 text-sm">
                  <span>{s.name}</span>
                  <span className="font-mono">{s.copies}</span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </section>
  );
}
