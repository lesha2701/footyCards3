import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { fetchManagerAnalytics, type ManagerPass } from "@/api/manager";
import analyticsArt from "@/assets/manager/analytics.webp";
import SectionTitle from "@/components/manager/SectionTitle";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { hapticNotify } from "@/lib/telegram";

const LINE_LABEL = { GK: "Вратарь", DEF: "Защита", MID: "Полузащита", FWD: "Атака" } as const;
const FORM_COLOR = { W: "bg-accent-lime text-bg-base", D: "bg-white/20 text-ink-chalk", L: "bg-red-400/80 text-bg-base" } as const;
const EDGE_TEXT = { win: "Твой стиль бьёт его — преимущество твоё", lose: "Его стиль бьёт твой — подумай о тактике", even: "Стили на равных" } as const;

function Form({ form }: { form: ("W" | "D" | "L")[] }) {
  if (form.length === 0) return <span className="text-micro text-ink-mist">ещё не играл</span>;
  return (
    <span className="flex gap-0.5">
      {form.map((r, i) => <span key={i} className={`flex h-4 w-4 items-center justify-center rounded text-[9px] font-black ${FORM_COLOR[r]}`}>{r === "W" ? "В" : r === "D" ? "Н" : "П"}</span>)}
    </span>
  );
}

/** «Аналитика Pro»: the next opponent line by line; a teaser without the pass. */
export default function AnalyticsPanel({ pass, onError }: { pass: ManagerPass | undefined; onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const { data } = useQuery({ queryKey: ["manager", "analytics"], queryFn: fetchManagerAnalytics, enabled: !!pass?.active, retry: false });
  if (!pass || (!pass.active && pass.stars <= 0)) return null;
  if (!pass.active) {
    const buy = async () => {
      setBusy(true);
      try {
        if ((await payMyPlayerWithStars({ purchase: "manager", code: "analytics" })) === "paid") {
          hapticNotify("success");
          await queryClient.invalidateQueries({ queryKey: ["manager"] });
        }
      } catch (err) {
        onError(err);
      } finally {
        setBusy(false);
      }
    };
    return (
      <section className="flex items-center gap-3 rounded-2xl bg-gradient-to-r from-sky-500/15 to-bg-surface p-3.5 ring-1 ring-sky-300/25" data-testid="analytics-teaser">
        <img src={analyticsArt} alt="" width={44} height={44} className="shrink-0 rounded-xl ring-1 ring-white/10" />
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-bold text-ink-chalk">Аналитика Pro</span>
          <span className="block text-micro text-ink-mist">Разбор соперника, алерты по акциям, спонсор и напоминания до окна</span>
        </span>
        <button disabled={busy} onClick={() => void buy()} className="shrink-0 rounded-xl bg-amber-400 px-3 py-2 text-xs font-bold text-bg-base">
          {pass.stars} ⭐
        </button>
      </section>
    );
  }
  const o = data?.opponent;
  if (!o) return null;
  return (
    <section className="flex flex-col gap-2.5 rounded-2xl bg-gradient-to-br from-sky-500/20 via-bg-surface to-bg-surface p-4 ring-1 ring-sky-300/30" data-testid="analytics">
      <div className="flex items-center justify-between gap-2">
        <h2 className="min-w-0"><SectionTitle art={analyticsArt}>Разбор: «{o.name}»</SectionTitle></h2>
        <span className="shrink-0 rounded-full bg-black/30 px-2 py-0.5 text-micro font-bold text-sky-200">{o.home ? "дома" : "в гостях"}</span>
      </div>
      <p className="-mt-1 text-xs text-ink-mist">{o.formation} · {EDGE_TEXT[o.edge]}</p>
      <div className="flex flex-col gap-1.5">
        {o.lines.map((l) => {
          const mine = l.mine ?? 0;
          const theirs = l.theirs ?? 0;
          const share = Math.max(10, Math.min(90, 50 + (mine - theirs) * 6));  // the gap, magnified
          return (
            <div key={l.line} className="flex items-center gap-2 text-xs">
              <span className={`w-7 text-right font-mono font-bold ${mine >= theirs ? "text-accent-lime" : "text-ink-mist"}`}>{l.mine ?? "—"}</span>
              <span className="relative h-2 flex-1 overflow-hidden rounded-full bg-red-400/40">
                <span className="absolute inset-y-0 left-0 rounded-full bg-accent-lime" style={{ width: `${share}%` }} />
              </span>
              <span className={`w-7 font-mono font-bold ${theirs > mine ? "text-red-300" : "text-ink-mist"}`}>{l.theirs ?? "—"}</span>
              <span className="w-20 text-micro text-ink-mist">{LINE_LABEL[l.line]}</span>
            </div>
          );
        })}
      </div>
      <div className="grid grid-cols-2 gap-2 text-micro text-ink-mist">
        <div className="flex flex-col gap-1 rounded-xl bg-black/20 p-2">
          <span>Ты: {o.my_record.gf}:{o.my_record.ga}</span>
          <Form form={o.my_record.form} />
        </div>
        <div className="flex flex-col gap-1 rounded-xl bg-black/20 p-2">
          <span>Соперник: {o.record.gf}:{o.record.ga}{o.injuries > 0 && ` · 🩹 ${o.injuries}`}</span>
          <Form form={o.record.form} />
        </div>
      </div>
    </section>
  );
}
