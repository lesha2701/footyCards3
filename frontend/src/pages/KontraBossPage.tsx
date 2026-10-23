import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchKontraBoss, startKontraBoss } from "@/api/kontra";
import { IconChevronLeft, IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";

const fmt = (n: number) => n.toLocaleString("ru-RU");

/** Weekly boss: one huge boss for everyone; each attempt's damage goes to
 *  your and your club's weekly total, coins by the attempt's damage tier. */
export default function KontraBossPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const { data: boss } = useQuery({ queryKey: ["kontra-boss"], queryFn: fetchKontraBoss });
  const start = useMutation({
    mutationFn: (manual: boolean) => startKontraBoss(manual),
    onSuccess: (b) => {
      queryClient.invalidateQueries({ queryKey: ["kontra-boss"] });
      queryClient.invalidateQueries({ queryKey: ["kontra-hub"] });
      navigate(`/play/kontra/battles/${b.id}`);
    },
    onError: (err) => setError(formatGameError(err, "Не удалось начать бой")),
  });
  if (!boss) return null;
  const left = Math.max(0, boss.week_hp - boss.week_damage);
  const pct = boss.week_hp ? Math.max(0, Math.round((left * 100) / boss.week_hp)) : 0;

  return (
    <div className="flex flex-col gap-3">
      <button onClick={() => navigate("/play/kontra")} className="flex items-center gap-1 self-start text-xs text-ink-mist">
        <IconChevronLeft size={16} /> Контратака
      </button>
      <section className="rounded-3xl bg-red-950/50 p-4 ring-1 ring-red-500/40">
        <p className="font-mono text-micro uppercase tracking-wider text-red-300">Босс недели · фаза {boss.phase}</p>
        <h1 className="font-display text-2xl font-black text-ink-chalk">{boss.name}</h1>
        <p className="text-xs text-ink-mist">{boss.tagline}</p>
        <div className="mt-3 h-3 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full bg-red-500" style={{ width: `${pct}%` }} />
        </div>
        <p className="mt-1 flex justify-between font-mono text-micro text-ink-mist">
          <span>{fmt(left)} HP</span><span>урон всех за неделю {fmt(boss.week_damage)}</span>
        </p>
      </section>

      <div className="grid grid-cols-2 gap-2">
        <div className="rounded-2xl bg-bg-surface p-3">
          <p className="text-micro text-ink-mist">Твой урон за неделю</p>
          <p className="font-mono text-lg font-bold text-amber-300">{fmt(boss.my_damage)}</p>
          <p className="text-micro text-ink-mist-dim">лучшая попытка {fmt(boss.my_best)}</p>
        </div>
        <div className="rounded-2xl bg-bg-surface p-3">
          <p className="text-micro text-ink-mist">{boss.club_name ? `Клуб «${boss.club_name}»` : "Клуб"}</p>
          <p className="font-mono text-lg font-bold text-ink-chalk">{boss.club_name ? fmt(boss.club_damage) : "—"}</p>
          <p className="text-micro text-ink-mist-dim">{boss.club_name ? "урон за неделю" : "вступи в клуб"}</p>
        </div>
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      <div className="grid grid-cols-2 gap-2">
        <button onClick={() => start.mutate(false)} disabled={start.isPending || boss.attempts_left <= 0} className="rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-chalk active:scale-95 disabled:opacity-40">
          Автобой
        </button>
        <button onClick={() => start.mutate(true)} disabled={start.isPending || boss.attempts_left <= 0} className="rounded-2xl bg-red-600 py-3 text-sm font-bold text-white active:scale-95 disabled:opacity-40">
          Атака вручную
        </button>
      </div>
      <p className="text-center text-caption text-ink-mist-dim">Попыток сегодня: {boss.attempts_left} из {boss.attempts_per_day}</p>

      <section className="rounded-2xl bg-bg-surface p-3">
        <p className="mb-1.5 text-xs font-semibold text-ink-chalk">Награда за попытку</p>
        <div className="flex flex-wrap gap-1.5">
          {boss.reward_tiers.map(([dmg, coins]) => (
            <span key={dmg} className="rounded-full bg-white/5 px-2 py-1 font-mono text-micro text-ink-mist">
              {fmt(dmg)}+ → {coins} <IconCoin size={9} className="inline" />
            </span>
          ))}
        </div>
      </section>

      {boss.top.length > 0 && (
        <section className="rounded-2xl bg-bg-surface p-3">
          <p className="mb-1.5 text-xs font-semibold text-ink-chalk">Лучшие за неделю</p>
          {boss.top.map((t, i) => (
            <div key={t.user_id} className="flex justify-between py-0.5 text-xs">
              <span className="truncate text-ink-chalk">{i + 1}. {t.name}</span>
              <span className="font-mono text-ink-mist">{fmt(t.damage)}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
