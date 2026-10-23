import { useQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";

import { fetchClubTrophies } from "@/api/clubFeatures";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconFlagCheckered, IconStar, IconTarget, IconTrophy } from "@/components/icons";
import { DIVISION_STYLES } from "@/lib/clubDivisions";

const date = (iso: string) => new Date(iso).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit", year: "2-digit" });

function Stat({ value, label, className = "text-ink-chalk" }: { value: number | string; label: string; className?: string }) {
  return (
    <div className="flex flex-col items-center rounded-xl bg-black/20 py-2">
      <span className={`font-mono text-lg font-bold ${className}`}>{value}</span>
      <span className="text-micro text-ink-mist">{label}</span>
    </div>
  );
}

/** «Трофейная комната» клуба — сезоны лиги, подиумы недель, турниры, задания, войны. */
export default function ClubTrophiesPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const { data: t, isLoading } = useQuery({ queryKey: ["clubs", "trophies", id], queryFn: () => fetchClubTrophies(Number(id)) });
  if (isLoading || !t) return <ListSkeleton />;
  const division = DIVISION_STYLES[t.division] ?? DIVISION_STYLES[0];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate(-1)} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Трофейная комната</h1>
      </div>

      <div className="relative flex flex-col items-center gap-2 overflow-hidden rounded-3xl bg-gradient-to-b from-amber-300/15 via-bg-surface to-bg-surface p-5 text-center">
        <ClubLogo shape={t.logo_shape} color={t.logo_color} emblem={t.emblem} size={96} />
        <p className="font-display text-lg font-bold text-ink-chalk">{t.name}</p>
        <span className={`rounded-full px-3 py-1 text-caption font-bold ${division.badge}`}>{t.division_name}</span>
        <p className="text-micro text-ink-mist-dim">Основан {date(t.founded_at)}</p>
      </div>

      <div className="grid grid-cols-4 gap-2">
        <Stat value={t.cups_count} label="кубки" className="text-amber-300" />
        <Stat value={t.stars_count} label="звёзды" className="text-accent-cyan" />
        <Stat value={t.quests_completed} label="заданий" className="text-accent-lime" />
        <Stat value={`${t.wars_won}/${t.wars_played}`} label="войны" />
      </div>

      <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3">
        <p className="flex items-center gap-1.5 font-display text-sm font-bold text-ink-chalk">
          <IconTrophy size={15} className="text-amber-300" /> Лига клубов: подиумы недель
        </p>
        <div className="grid grid-cols-3 gap-2">
          <Stat value={t.league_gold} label="🥇 1 место" className="text-amber-300" />
          <Stat value={t.league_silver} label="🥈 2 место" className="text-slate-200" />
          <Stat value={t.league_bronze} label="🥉 3 место" className="text-orange-300" />
        </div>
        {t.recent_podiums.map((p) => (
          <div key={p.week_start} className="flex items-center justify-between text-xs text-ink-mist">
            <span>Неделя {date(p.week_start)} · {p.division_name}</span>
            <span className="font-bold text-ink-chalk">{p.rank} место · {p.points} очк.</span>
          </div>
        ))}
      </section>

      <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3">
        <p className="flex items-center gap-1.5 font-display text-sm font-bold text-ink-chalk">
          <IconStar size={15} className="text-accent-cyan" /> Сезоны
        </p>
        {t.seasons.length === 0 && <p className="text-xs text-ink-mist-dim">Первый сезон ещё идёт</p>}
        {t.seasons.map((s) => (
          <div key={s.season_end_week} className="flex items-center gap-2 text-xs">
            <span className="text-ink-mist">до {date(s.season_end_week)}</span>
            <span className={`rounded-full px-2 py-0.5 text-micro font-bold ${(DIVISION_STYLES[s.division] ?? DIVISION_STYLES[0]).badge}`}>
              {s.division_name}
            </span>
            <span className="ml-auto font-bold text-ink-chalk">{s.rank} место</span>
            {s.moved > 0 && <span className="text-accent-green">▲ повышение</span>}
            {s.moved < 0 && <span className="text-red-400">▼ вылет</span>}
          </div>
        ))}
      </section>

      <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3">
        <p className="flex items-center gap-1.5 font-display text-sm font-bold text-ink-chalk">
          <IconFlagCheckered size={15} className="text-accent-lime" /> Турниры
        </p>
        <div className="grid grid-cols-3 gap-2">
          <Stat value={t.tournaments_played} label="сыграно" />
          <Stat value={t.tournaments_won} label="победы" className="text-amber-300" />
          <Stat value={t.best_tournament_rank ?? "—"} label="лучшее место" />
        </div>
        {t.recent_tournaments.map((r) => (
          <button
            key={r.tournament_id}
            onClick={() => navigate(`/clubs/tournament/${r.tournament_id}`)}
            className="flex items-center justify-between text-left text-xs text-ink-mist"
          >
            <span>{date(r.played_at)}</span>
            <span className="font-bold text-ink-chalk">{r.cup ? "🏆 " : ""}{r.final_rank} место</span>
          </button>
        ))}
      </section>

      <p className="flex items-center justify-center gap-1 text-micro text-ink-mist-dim">
        <IconTarget size={11} /> Трофеи копятся сами — играйте, выигрывайте недели и сезоны
      </p>
    </div>
  );
}
