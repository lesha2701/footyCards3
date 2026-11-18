import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { likeVilla, visitVilla } from "@/api/town";
import VillaPlot from "@/components/town/VillaPlot";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

const fmt = (n: number) => n.toLocaleString("ru-RU");

/** A guest at someone's «Моя вилла» (/town/visit/:ownerId/villa): look and like. */
export default function TownVillaVisitPage() {
  const ownerId = Number(useParams().ownerId);
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const { data, error } = useQuery({ queryKey: ["town-villa-visit", ownerId], queryFn: () => visitVilla(ownerId), enabled: ownerId > 0 });
  const like = useMutation({
    mutationFn: () => likeVilla(ownerId),
    onSuccess: (res) => {
      hapticNotify("success");
      queryClient.setQueryData(["town-villa-visit", ownerId], res);
      if (res.new_balance != null) updateBalance(res.new_balance);
      setMessage({ ok: true, text: res.party_paid ? `Лайк вилле ❤️ — и +${fmt(res.party_paid)} монет с вечеринки 🎉` : "Лайк вилле поставлен ❤️" });
    },
    onError: (err) => { hapticNotify("error"); setMessage({ ok: false, text: formatGameError(err, "Не получилось") }); },
  });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 px-1">
        <span className="text-4xl" aria-hidden>🏡</span>
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-display text-xl font-bold leading-tight text-ink-chalk">Вилла в гостях</h1>
          <p className="truncate text-xs text-ink-mist">
            {data ? `${"★".repeat(data.villa_level)} · престиж ${fmt(data.prestige)} · ❤️ ${fmt(data.likes_total)}` : "Загрузка…"}
          </p>
        </div>
        <Link to={`/town/visit/${ownerId}`} className="shrink-0 rounded-full bg-white/5 px-3 py-1.5 text-xs font-bold text-ink-mist">🏘️ Город</Link>
      </div>
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{formatGameError(error, "Вилла не открылась")}</p>}
      {message && (
        <p className={`rounded-xl px-3 py-2 text-xs ${message.ok ? "bg-accent-lime/10 text-accent-lime" : "bg-red-500/10 text-red-400"}`}>{message.text}</p>
      )}
      {data && (
        <>
          {data.party_until && (
            <p className="rounded-2xl border border-fuchsia-300/30 bg-fuchsia-500/10 px-3 py-2 text-center text-xs text-fuchsia-100">
              🎉 На вилле вечеринка!{data.party_guest_coins && !data.liked ? ` Лайкни виллу — получишь +${fmt(data.party_guest_coins)} монет.` : ""}
            </p>
          )}
          <button
            type="button" disabled={data.liked || like.isPending} onClick={() => like.mutate()}
            className={`min-h-[48px] rounded-2xl text-sm font-bold ${data.liked ? "bg-white/5 text-ink-mist" : "bg-rose-500 text-white"}`}
          >
            {data.liked ? `❤️ Лайк есть · за неделю ${fmt(data.likes_week)}` : "❤️ Лайк вилле"}
          </button>
          <div className="overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-b from-sky-400/25 to-sky-900/10">
            <VillaPlot
              open={data.cells_open} items={data.items.filter((i) => i.x != null)}
              comboIds={new Set((data.combos ?? []).flatMap((c) => c.ids))} label="Вилла хозяина"
            />
          </div>
          {(data.combos ?? []).length > 0 && (
            <div className="flex flex-wrap justify-center gap-1">
              {data.combos.map((c) => (
                <span key={`${c.a}:${c.b}`} className="rounded-full bg-accent-lime/15 px-2 py-0.5 text-[11px] font-semibold text-accent-lime">{c.emoji} {c.name}</span>
              ))}
            </div>
          )}
          {(data.perks ?? []).length > 0 && (
            <div className="flex flex-wrap justify-center gap-1">
              {data.perks.map((p) => (
                <span key={p.code} className="rounded-full bg-white/5 px-2 py-0.5 text-[11px] text-ink-mist">{p.emoji} {p.name}</span>
              ))}
            </div>
          )}
          {(data.trophies ?? []).length > 0 && (
            <section className="rounded-2xl border border-amber-300/25 bg-amber-400/5 p-3" aria-label="Витрина трофеев">
              <p className="mb-2 text-xs font-bold text-ink-chalk">🏆 Витрина трофеев хозяина</p>
              <div className="flex flex-wrap gap-2">
                {data.trophies.map((t) => (
                  <span key={t.id} className="flex items-center gap-1 rounded-full bg-white/5 py-1 pl-1 pr-2 text-[11px] text-ink-chalk">
                    <span className="grid h-6 w-6 place-items-center overflow-hidden rounded-full bg-white/10">
                      {t.image_path ? <img src={staticUrl(t.image_path)} alt="" className="h-full w-full object-contain" /> : (t.icon || "🏆")}
                    </span>
                    {t.name}
                  </span>
                ))}
              </div>
            </section>
          )}
          {data.car && <p className="px-1 text-center text-xs text-ink-mist">В городе ездит: {data.car.emoji} {data.car.name}</p>}
          {data.staff.length > 0 && (
            <div className="flex flex-wrap justify-center gap-2">
              {data.staff.map((s) => (
                <span key={s.post} className="flex items-center gap-1 rounded-full bg-white/5 py-1 pl-1 pr-2 text-[11px] text-ink-chalk">
                  <span className="grid h-6 w-6 place-items-center overflow-hidden rounded-full bg-white/10">
                    {s.resident.image_path ? <img src={staticUrl(s.resident.image_path)} alt="" className="h-full w-full object-cover" /> : s.resident.icon}
                  </span>
                  {s.emoji} {s.resident.name}
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
