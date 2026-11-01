import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchManagerRating, type ManagerRatingTable } from "@/api/manager";
import { ListSkeleton } from "@/components/common/Skeleton";
import Emblem from "@/components/manager/Emblem";
import { eur } from "@/lib/managerMoney";

type Board = "profit" | "capital";
const MEDAL = ["🥇", "🥈", "🥉"];

/** «🏆 Лучший президент»: clubs by the season's profit and by the capital. */
export default function PresidentRating() {
  const { data } = useQuery({ queryKey: ["manager", "rating"], queryFn: fetchManagerRating });
  const [board, setBoard] = useState<Board>("profit");
  if (!data) return <ListSkeleton />;
  const table: ManagerRatingTable = data[board];
  const week = Number(data.season_key.split("-W")[1] ?? 0);
  return (
    <div className="flex flex-col gap-3" data-testid="president-rating">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-amber-500/30 via-[#2a1a05] to-[#0b1220] p-4 ring-1 ring-amber-300/40">
        <span className="pointer-events-none absolute -right-2 -top-3 text-[88px] leading-none opacity-80">🏆</span>
        <p className="relative text-micro font-bold uppercase tracking-[0.2em] text-amber-200">Лучший президент</p>
        <p className="relative mt-1 max-w-[65%] text-caption text-ink-mist">
          {board === "profit" ? `Прибыль сезона недели ${week}: доходы минус расходы, без кредитов и вложений.`
            : "Капитал: бюджет + депозиты и венчур + акции по цене биржи + облигации − долги."}
        </p>
        <div className="relative mt-3 flex items-end gap-2">
          <b className="font-display text-3xl font-black text-ink-chalk">{table.my_place ? `#${table.my_place}` : "—"}</b>
          <span className="pb-1 text-micro text-ink-mist">из {table.total} · {eur(table.my_score)}</span>
        </div>
      </section>
      <div className="grid grid-cols-2 gap-1 rounded-2xl bg-bg-surface p-1">
        {([["profit", "💹 Прибыль сезона"], ["capital", "💰 Капитал"]] as const).map(([id, label]) => (
          <button key={id} onClick={() => setBoard(id)}
            className={`rounded-xl py-2 text-xs font-bold ${board === id ? "bg-gradient-to-r from-amber-300 to-yellow-300 text-bg-base" : "text-ink-mist"}`}>
            {label}
          </button>
        ))}
      </div>
      {table.rows.length === 0 ? (
        <p className="rounded-2xl bg-bg-surface p-4 text-caption text-ink-mist">Пока пусто — рейтинг появится после первого сезона.</p>
      ) : (
        <ol className="flex flex-col gap-1.5">
          {table.rows.map((r) => (
            <li key={r.club_id}
              className={`flex items-center gap-2 rounded-2xl p-2.5 ${r.mine ? "bg-amber-300/15 ring-1 ring-amber-300/50" : "bg-bg-surface"}`}>
              <span className="w-7 text-center font-display text-sm font-black text-ink-chalk">{MEDAL[r.place - 1] ?? r.place}</span>
              <Emblem look={r.look} size={30} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-ink-chalk">{r.name}</span>
                <span className="text-micro text-ink-mist">Дивизион {r.division}</span>
              </span>
              <b className={`shrink-0 font-display text-sm ${r.score >= 0 ? "text-accent-lime" : "text-red-300"}`}>{eur(r.score)}</b>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
