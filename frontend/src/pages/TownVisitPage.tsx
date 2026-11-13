import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { giftTown, likeTown, visitTown, type TownVisitView } from "@/api/town";
import { IconCoin } from "@/components/icons";
import TownScene from "@/components/town/TownScene";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import { DECOR_ZONES, MAP_ZONES, TOWN_MAP, badgeAnchor } from "@/lib/town";
import { useAuthStore } from "@/store/authStore";

const fmt = (n: number) => n.toLocaleString("ru-RU");
const moodEmoji = (mood: number) => (mood >= 80 ? "😄" : mood >= 60 ? "🙂" : mood >= 40 ? "😐" : "😟");

/** A guest in someone's town (/town/visit/:ownerId): his map, a like, a gift. */
export default function TownVisitPage() {
  const ownerId = Number(useParams().ownerId);
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const { data, error } = useQuery({ queryKey: ["town-visit", ownerId], queryFn: () => visitTown(ownerId), enabled: ownerId > 0 });
  const done = (text: string) => (res: TownVisitView) => {
    hapticNotify("success");
    if (res.new_balance != null) updateBalance(res.new_balance);
    queryClient.setQueryData(["town-visit", ownerId], res);
    void queryClient.invalidateQueries({ queryKey: ["town-quests"] });
    void queryClient.invalidateQueries({ queryKey: ["town-guests"] });
    setMessage({ ok: true, text });
  };
  const fail = (err: unknown) => { hapticNotify("error"); setMessage({ ok: false, text: formatGameError(err, "Не получилось") }); };
  const like = useMutation({ mutationFn: () => likeTown(ownerId), onSuccess: done("Лайк поставлен ❤️"), onError: fail });
  const gift = useMutation({
    mutationFn: () => giftTown(ownerId),
    onSuccess: (res) => done(`Подарок оставлен — хозяин получит +${fmt(res.gift_rent)} к ренте 🎁`)(res),
    onError: fail,
  });
  const district = (code: string) => data?.districts.find((d) => d.code === code);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 px-1">
        <span className="text-4xl" aria-hidden>🏘️</span>
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-display text-xl font-bold leading-tight text-ink-chalk">{data?.name ?? "В гостях"}</h1>
          <p className="truncate text-xs text-ink-mist">{data ? `Хозяин: ${data.owner} · ❤️ ${fmt(data.likes_total)}` : "Загрузка…"}</p>
        </div>
        <Link to="/town/guests" className="shrink-0 rounded-full bg-white/5 px-3 py-1.5 text-xs font-bold text-ink-mist">👋 Гости</Link>
      </div>
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{formatGameError(error, "Город не открылся")}</p>}
      {message && (
        <p className={`rounded-xl px-3 py-2 text-xs ${message.ok ? "bg-accent-lime/10 text-accent-lime" : "bg-red-500/10 text-red-400"}`}>{message.text}</p>
      )}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-2">
            <button
              type="button" disabled={data.liked || like.isPending} onClick={() => like.mutate()}
              className={`min-h-[48px] rounded-2xl text-sm font-bold ${data.liked ? "bg-white/5 text-ink-mist" : "bg-rose-500 text-white"}`}
            >
              {data.liked ? "❤️ Лайк есть" : "❤️ Лайк"}
            </button>
            <button
              type="button" disabled={!data.can_gift || gift.isPending} onClick={() => gift.mutate()}
              className={`flex min-h-[48px] flex-col items-center justify-center rounded-2xl text-sm font-bold ${data.can_gift ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
            >
              {data.gifted ? "🎁 Подарок оставлен" : (
                <>
                  <span>🎁 Подарок</span>
                  <span className="flex items-center gap-0.5 text-[10px] font-semibold"><IconCoin size={10} /> {fmt(data.gift_price)} · хозяину +{fmt(data.gift_rent)}</span>
                </>
              )}
            </button>
          </div>
          <section className="rounded-3xl border border-white/10 bg-bg-surface p-2">
            <TownScene
              art={TOWN_MAP}
              label={`Карта: ${data.name}`}
              decorations={data.season_items}
              onPick={() => undefined}
              zones={[...MAP_ZONES.filter((z) => z.code !== "base").map((z) => {
                const d = district(z.code);
                return {
                  code: z.code,
                  label: z.name,
                  zone: z.zone,
                  badge: (
                    <span className={`absolute top-1/2 flex -translate-y-1/2 flex-col items-center whitespace-nowrap rounded-xl bg-black/65 px-1.5 py-0.5 font-display text-[10px] font-bold leading-tight text-white shadow-lg ring-1 ring-white/25 ${badgeAnchor(z.zone)}`}>
                      <span><span aria-hidden>{z.emoji}</span> {z.name}</span>
                      {d && <span className="text-[9px] font-semibold text-white/70">🏠 {d.owned}/{d.total} · {moodEmoji(d.mood)} {d.mood}</span>}
                    </span>
                  ),
                };
              }), ...DECOR_ZONES.map((z) => ({
                code: `decor:${z.code}`,
                label: z.name,
                zone: z.zone,
                badge: (
                  <span className={`absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-full px-2 py-0.5 text-[10px] font-bold ${data.places.includes(z.code) ? "bg-black/60 text-white" : "bg-black/70 text-white/50"}`}>
                    {data.places.includes(z.code) ? z.emoji : "🔒"} {z.name}
                  </span>
                ),
              }))]}
            />
          </section>
          <p className="px-1 text-center text-xs text-ink-mist">
            {data.hotel ? "🏨 Есть отель · " : ""}🧑 Жителей {fmt(data.population)} · лайков сегодня {fmt(data.likes_today)}
          </p>
        </>
      )}
    </div>
  );
}
