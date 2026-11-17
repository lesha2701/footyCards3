import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { likeVilla, visitVilla } from "@/api/town";
import VillaPlot from "@/components/town/VillaPlot";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";

const fmt = (n: number) => n.toLocaleString("ru-RU");

/** A guest at someone's «Моя вилла» (/town/visit/:ownerId/villa): look and like. */
export default function TownVillaVisitPage() {
  const ownerId = Number(useParams().ownerId);
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const { data, error } = useQuery({ queryKey: ["town-villa-visit", ownerId], queryFn: () => visitVilla(ownerId), enabled: ownerId > 0 });
  const like = useMutation({
    mutationFn: () => likeVilla(ownerId),
    onSuccess: (res) => {
      hapticNotify("success");
      queryClient.setQueryData(["town-villa-visit", ownerId], res);
      setMessage({ ok: true, text: "Лайк вилле поставлен ❤️" });
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
          <button
            type="button" disabled={data.liked || like.isPending} onClick={() => like.mutate()}
            className={`min-h-[48px] rounded-2xl text-sm font-bold ${data.liked ? "bg-white/5 text-ink-mist" : "bg-rose-500 text-white"}`}
          >
            {data.liked ? `❤️ Лайк есть · за неделю ${fmt(data.likes_week)}` : "❤️ Лайк вилле"}
          </button>
          <div className="overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-b from-sky-400/25 to-sky-900/10">
            <VillaPlot
              grid={data.grid} gridMax={data.grid_max ?? data.grid} items={data.items.filter((i) => i.x != null)}
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
