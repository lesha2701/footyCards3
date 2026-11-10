import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { fetchTownResidents, sellTownResidentSpare, type TownResident, type TownResidentsAlbum } from "@/api/town";
import residentsArt from "@/assets/town/residents.webp";
import { IconCoin } from "@/components/icons";
import MuseArt from "@/components/muses/MuseArt";
import { formatGameError } from "@/lib/errors";
import { districtOf } from "@/lib/town";
import { RARITY_LABELS } from "@/lib/rarity";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Rarity } from "@/types";

const fmt = (n: number) => n.toLocaleString("ru-RU");
const coinsWord = (n: number) => {
  const d = n % 10, h = n % 100;
  if (d === 1 && h !== 11) return "монета";
  return d >= 2 && d <= 4 && (h < 12 || h > 14) ? "монеты" : "монет";
};

/** «Жители города» (/town/residents): the album of resident cards. Every copy
 * pays rent each day, a resident's bonus counts once; spare copies are sold
 * for coins (backend town_service — every number comes from there). */
export default function TownResidentsPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [picked, setPicked] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["town-residents"], queryFn: fetchTownResidents });
  const sell = useMutation({
    mutationFn: (id: number) => sellTownResidentSpare(id, 1),
    onSuccess: (res) => {
      hapticNotify("success");
      setError(null);
      setNotice(`Продано: +${fmt(res.sold_coins ?? 0)} монет`);
      if (res.new_balance != null) updateBalance(res.new_balance);
      queryClient.setQueryData(["town-residents"], res);
      queryClient.invalidateQueries({ queryKey: ["town"] });
    },
    onError: (err) => { hapticNotify("error"); setNotice(null); setError(formatGameError(err, "Не получилось")); },
  });
  const resident = data?.residents.find((r) => r.id === picked) ?? null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 px-1">
        <img src={residentsArt} alt="" className="h-12 w-12 shrink-0 object-contain" draggable={false} />
        <div className="min-w-0 flex-1">
          <h1 className="font-display text-xl font-bold leading-tight text-ink-chalk">Жители города</h1>
          <p className="truncate text-xs text-ink-mist">
            {data ? `Собрано ${data.owned_count} из ${data.total_count} · население ${fmt(data.population)}` : "Загрузка…"}
          </p>
        </div>
        <Link to="/town" className="shrink-0 rounded-full bg-white/5 px-3 py-1.5 text-xs font-bold text-ink-mist">🗺️ Город</Link>
      </div>

      {data && <Summary album={data} />}
      {data && <SetsPanel album={data} />}
      {data && !data.enabled && <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-xs text-legend">Жители временно недоступны.</p>}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {notice && <p className="rounded-xl bg-accent-lime/10 px-3 py-2 text-xs text-accent-lime">{notice}</p>}

      {resident && (
        <ResidentCard resident={resident} busy={sell.isPending} enabled={!!data?.enabled} settledOnly={!!data?.bonus_settled_only}
          onSell={() => sell.mutate(resident.id)} onClose={() => setPicked(null)} />
      )}

      {data && data.residents.length === 0 ? (
        <p className="rounded-2xl bg-bg-surface px-3 py-6 text-center text-sm text-ink-mist">Жители скоро приедут в город.</p>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {(data?.residents ?? []).map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => setPicked(r.id)}
              aria-label={r.owned ? `${r.name}, копий ${r.copies}` : `${r.name}, ещё нет`}
              className={`relative flex min-w-0 flex-col gap-1 rounded-2xl p-1 text-left ${picked === r.id ? "bg-cyan-400/15 ring-1 ring-cyan-300/60" : "bg-bg-surface"}`}
            >
              <MuseArt muse={r} locked={!r.owned} className="aspect-[3/4] w-full rounded-2xl" iconClass="text-4xl" />
              {r.owned && r.district && (
                <span className="absolute left-2 top-2 rounded-full bg-black/70 px-1 text-[11px] leading-5" aria-label="Поселён в район">
                  {districtOf(r.district)?.emoji ?? "🏠"}
                </span>
              )}
              {r.copies > 1 && (
                <span className="absolute right-2 top-2 rounded-full bg-black/70 px-1.5 text-[11px] font-bold leading-5 text-white">×{r.copies}</span>
              )}
              <span className={`truncate px-0.5 text-xs font-semibold ${r.owned ? "text-ink-chalk" : "text-ink-mist-dim"}`}>{r.name}</span>
              <span className={`truncate px-0.5 text-[10px] ${r.bonus !== "none" && r.owned && !r.bonus_active ? "text-ink-mist-dim line-through" : "text-cyan-300"}`}>
                {r.bonus_label || RARITY_LABELS[r.rarity as Rarity] || r.rarity}
              </span>
            </button>
          ))}
        </div>
      )}
      <p className="px-1 text-center text-xs text-ink-mist">
        Жители приходят из паков «Жители» и из магазина. Каждая копия платит ренту, бонус жителя считается один раз
        {data?.bonus_settled_only ? " и работает, только пока житель поселён в район (по 3 в районе)" : ""}.
      </p>
    </div>
  );
}

function Summary({ album }: { album: TownResidentsAlbum }) {
  const { bonuses } = album;
  const parts = [
    `+${fmt(album.population * album.rent_per_resident)} в день от жителей`,
    bonuses.rent_pct ? `+${bonuses.rent_pct}% к ренте домов` : "",
    bonuses.hotel_pct ? `+${bonuses.hotel_pct}% к отелю` : "",
    bonuses.daily_coins ? `+${fmt(bonuses.daily_coins)} монет в день` : "",
    bonuses.xp_pct ? `+${bonuses.xp_pct}% к опыту «Моего игрока»` : "",
    bonuses.game_attempts ? `+${bonuses.game_attempts} наградн. попытки в мини-играх` : "",
    bonuses.build_pct ? `−${bonuses.build_pct}% ко времени стройки базы` : "",
  ].filter(Boolean);
  return (
    <section className="rounded-2xl border border-cyan-300/25 bg-cyan-400/5 p-3 text-xs" aria-label="Что дают жители">
      <p className="font-semibold text-ink-chalk">
        Каждый житель — +{fmt(album.rent_per_resident)} {coinsWord(album.rent_per_resident)} в день
      </p>
      <p className="text-ink-mist">{parts.join(" · ")}</p>
    </section>
  );
}

function ResidentCard({ resident: r, busy, enabled, settledOnly, onSell, onClose }: {
  resident: TownResident; busy: boolean; enabled: boolean; settledOnly: boolean; onSell: () => void; onClose: () => void;
}) {
  const home = r.district ? districtOf(r.district) : undefined;
  return (
    <section className="flex gap-3 rounded-2xl border border-white/10 bg-bg-surface p-3" aria-label={r.name}>
      <MuseArt muse={r} locked={!r.owned} className="aspect-[3/4] w-20 shrink-0 rounded-xl" iconClass="text-3xl" />
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <p className="truncate font-display text-base font-bold text-ink-chalk">{r.name}</p>
            <p className="truncate text-[11px] text-ink-mist">{[r.title, RARITY_LABELS[r.rarity as Rarity] ?? r.rarity].filter(Boolean).join(" · ")}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Закрыть" className="text-sm text-ink-mist">✕</button>
        </div>
        <p className="text-xs font-semibold text-cyan-300">{r.effect_label}</p>
        {r.description && <p className="text-[11px] text-ink-mist">{r.description}</p>}
        <p className="text-[11px] text-ink-mist">{r.owned ? `Копий: ${r.copies}` : "Ещё не живёт в твоём городе"}</p>
        {r.owned && home && <p className="text-[11px] text-accent-lime">{home.emoji} Живёт: {home.name}{r.bonus !== "none" ? " — бонус работает" : ""}</p>}
        {r.owned && !home && settledOnly && r.bonus !== "none" && (
          <Link to="/town" className="text-[11px] font-semibold text-legend underline">
            💤 Бонус спит — посели жителя в район (район → «+»)
          </Link>
        )}
        {r.copies > 1 && r.spare_coins > 0 && (
          <button type="button" disabled={busy || !enabled} onClick={onSell}
            className="mt-1 min-h-[40px] self-start rounded-xl bg-floodlight px-3 text-xs font-bold text-bg-base disabled:opacity-40">
            <span className="flex items-center gap-1">Продать лишнюю за <IconCoin size={12} /> {fmt(r.spare_coins)}</span>
          </button>
        )}
      </div>
    </section>
  );
}

/** «Наборы жителей»: progress of each set, a badge for a whole one. */
function SetsPanel({ album }: { album: TownResidentsAlbum }) {
  const sets = album.sets ?? [];
  if (sets.length === 0) return null;
  const names = new Map(album.residents.map((r) => [r.id, r]));
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-amber-300/25 bg-amber-400/5 p-3" aria-label="Наборы жителей" data-testid="town-sets">
      <div className="flex items-center justify-between">
        <p className="text-sm font-bold text-ink-chalk">🧩 Наборы жителей</p>
        {!!album.sets_pct && <span className="text-xs font-bold text-amber-200">+{album.sets_pct}% к ренте домов</span>}
      </div>
      {sets.map((s) => (
        <div key={s.name} className="flex flex-col gap-1">
          <div className="flex items-center justify-between gap-2">
            <p className={`truncate text-xs font-semibold ${s.complete ? "text-amber-200" : "text-ink-chalk"}`}>
              {s.complete ? "🏅 " : ""}{s.name}
            </p>
            <span className="shrink-0 text-[11px] text-ink-mist">
              {s.complete ? `собран · +${s.rent_pct}%` : `${s.owned}/${s.total} · соберёшь — +${s.rent_pct}%`}
            </span>
          </div>
          <div className="flex flex-wrap gap-1">
            {s.resident_ids.map((id) => {
              const r = names.get(id);
              if (!r) return null;
              return (
                <span key={id} className={`rounded-full px-2 py-0.5 text-[10px] ${r.owned ? "bg-amber-400/15 text-amber-100" : "bg-white/5 text-ink-mist-dim"}`}>
                  {r.owned ? r.icon : "❔"} {r.name}
                </span>
              );
            })}
          </div>
        </div>
      ))}
      {!!album.sets_max_pct && <p className="text-[10px] text-ink-mist">Все наборы вместе — не больше +{album.sets_max_pct}%.</p>}
    </section>
  );
}
