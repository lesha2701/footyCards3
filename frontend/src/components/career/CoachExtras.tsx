import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { fetchCareerLeaderboard, type CareerAchievements, type CareerLeaderboardRow } from "@/api/career";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconTrophy, IconUsers } from "@/components/icons";
import titleCupArt from "@/assets/coach/title_cup.webp";
import { careerArt } from "@/lib/careerArt";

const TROPHY_ICON: Record<string, string> = { title: "🏆", cup: "🏅", promotion: "⬆️" };

/** Trophy cabinet and the achievements grid (locked ones greyed out). */
export function AchievementsPanel({ data }: { data: CareerAchievements }) {
  return (
    <div className="flex flex-col gap-3">
      <div>
        <p className="mb-1.5 text-caption font-semibold text-ink-mist">Трофеи</p>
        {data.trophies.length === 0 ? (
          <EmptyState compact icon={IconTrophy} title="Трофеев пока нет" description="Титулы, кубки и повышения попадут сюда." />
        ) : (
          <div className="flex gap-2 overflow-x-auto pb-1" style={{ scrollbarWidth: "none" }}>
            {data.trophies.map((t, i) => (
              <div key={i} className="flex w-24 shrink-0 flex-col items-center gap-1 rounded-2xl bg-bg-base/50 p-2 text-center">
                {t.kind === "title" ? (
                  <img src={titleCupArt} alt="" decoding="async" className="h-10 w-10 rounded-lg object-cover" />
                ) : careerArt("achievements", t.kind) ? (
                  <img src={careerArt("achievements", t.kind)} alt="" decoding="async" className="h-10 w-10 object-contain" />
                ) : (
                  <span className="text-2xl" aria-hidden>{TROPHY_ICON[t.kind] ?? "🏆"}</span>
                )}
                <span className="text-micro leading-tight text-ink-chalk">{t.label}</span>
                <span className="text-micro text-ink-mist-dim">{new Date(t.at).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</span>
              </div>
            ))}
          </div>
        )}
      </div>
      <div>
        <p className="mb-1.5 text-caption font-semibold text-ink-mist">Достижения · {data.unlocked} из {data.total}</p>
        <div className="grid grid-cols-3 gap-1.5">
          {data.items.map((a) => {
            const art = careerArt("achievements", a.code);
            return (
              <div
                key={a.code}
                title={a.text}
                className={`flex flex-col items-center gap-1 rounded-2xl p-2 text-center ${a.unlocked_at ? "bg-accent-lime/10 ring-1 ring-accent-lime/30" : "bg-bg-base/40"}`}
              >
                {art
                  ? <img src={art} alt="" decoding="async" className={`h-14 w-14 object-contain ${a.unlocked_at ? "" : "opacity-35 grayscale"}`} />
                  : <span className={`text-2xl ${a.unlocked_at ? "" : "opacity-40 grayscale"}`} aria-hidden>{a.icon}</span>}
                <span className={`text-caption font-bold leading-tight ${a.unlocked_at ? "text-ink-chalk" : "text-ink-mist"}`}>{a.title}</span>
                <span className="text-micro leading-tight text-ink-mist-dim">{a.text}</span>
              </div>
            );
          })}
        </div>
        <p className="mt-1.5 text-micro text-ink-mist-dim">
          Серии: побед {data.run.wins} · без поражений {data.run.unbeaten} · сухих {data.run.clean}
        </p>
      </div>
    </div>
  );
}

function Row({ row }: { row: CareerLeaderboardRow }) {
  return (
    <div className={`flex items-center gap-2 rounded-xl px-2 py-1.5 text-xs ${row.is_me ? "bg-accent-lime/10 text-accent-lime" : "text-ink-chalk"}`}>
      <span className="w-6 text-right font-mono text-ink-mist">{row.rank}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-semibold">{row.name}</span>
        <span className="block truncate text-micro text-ink-mist">{row.division_name} · {row.level}</span>
      </span>
      <span className="text-micro text-ink-mist" title="Титулы / трофеи">🏆{row.titles} · 🎖{row.achievements}</span>
      <span className="w-10 text-right font-mono font-bold">{row.reputation}</span>
    </div>
  );
}

/** Coaches by reputation: overall or by division. */
export function CoachLeaderboard() {
  const [division, setDivision] = useState<number | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["career", "leaderboard", division],
    queryFn: () => fetchCareerLeaderboard(division),
    staleTime: 60_000,
  });
  return (
    <div className="flex flex-col gap-2">
      <div className="flex gap-1 overflow-x-auto" style={{ scrollbarWidth: "none" }}>
        {[{ division: null as number | null, name: "Все" }, ...(data?.divisions ?? []).map((d) => ({ division: d.division, name: d.name }))].map((d) => (
          <button
            key={d.division ?? "all"}
            onClick={() => setDivision(d.division)}
            className={`shrink-0 rounded-lg px-2.5 py-1 text-caption font-semibold ${division === d.division ? "bg-floodlight text-bg-base" : "bg-bg-base/50 text-ink-mist"}`}
          >
            {d.name}
          </button>
        ))}
      </div>
      {isLoading || !data ? (
        <ListSkeleton count={3} />
      ) : data.rows.length === 0 ? (
        <EmptyState compact icon={IconUsers} title="В этом дивизионе пока никого" description="Здесь появятся тренеры, которые играют в этом дивизионе." />
      ) : (
        <div className="flex flex-col gap-0.5">
          {data.rows.map((r) => <Row key={r.user_id} row={r} />)}
          {data.me && (
            <>
              <p className="text-center text-micro text-ink-mist-dim">…</p>
              <Row row={data.me} />
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** Under the coach card: achievements & trophies, and the leaderboard. */
export function CoachExtras({ achievements }: { achievements?: CareerAchievements }) {
  const [open, setOpen] = useState<"achievements" | "leaderboard" | null>(null);
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-3">
      <div className="grid grid-cols-2 gap-2">
        {([
          ["achievements", `🏅 Достижения${achievements ? ` ${achievements.unlocked}/${achievements.total}` : ""}`],
          ["leaderboard", "📈 Рейтинг тренеров"],
        ] as const).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setOpen(open === id ? null : id)}
            aria-expanded={open === id}
            className={`rounded-xl px-2 py-2 text-xs font-semibold ${open === id ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk"}`}
          >
            {label}
          </button>
        ))}
      </div>
      {open === "achievements" && achievements && <AchievementsPanel data={achievements} />}
      {open === "leaderboard" && <CoachLeaderboard />}
    </section>
  );
}
