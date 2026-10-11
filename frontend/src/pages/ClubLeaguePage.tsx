import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchClubLeague } from "@/api/clubs";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconClock, IconCoin, IconTrophy, IconUsers } from "@/components/icons";
import type { ClubLeagueRow } from "@/types";

function timeLeft(endsAt: string): string {
  const seconds = Math.max(0, (new Date(endsAt).getTime() - Date.now()) / 1000);
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) return `${days} д ${hours} ч`;
  if (hours > 0) return `${hours} ч ${minutes} мин`;
  return `${minutes} мин`;
}

function weekLabel(weekStart: string): string {
  const start = new Date(`${weekStart}T00:00:00`);
  const end = new Date(start);
  end.setDate(start.getDate() + 6);
  const fmt = (d: Date) => d.toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
  return `${fmt(start)}–${fmt(end)}`;
}

function Row({ row, mine }: { row: ClubLeagueRow; mine: boolean }) {
  return (
    <div
      className={`flex items-center gap-3 rounded-xl px-3 py-2 ${mine ? "bg-accent-lime/10 ring-1 ring-accent-lime/40" : "bg-bg-surface"}`}
    >
      <span className={`w-6 text-center font-mono text-sm font-bold ${row.rank <= 3 ? "text-accent-lime" : "text-ink-mist"}`}>
        {row.rank}
      </span>
      <ClubLogo shape={row.logo_shape} color={row.logo_color} size={28} />
      <span className="min-w-0 flex-1 truncate text-sm font-semibold text-ink-chalk">{row.name}</span>
      {row.reward > 0 && (
        <span className="flex items-center gap-0.5 font-mono text-[11px] text-ink-mist">
          +{row.reward}
          <IconCoin size={11} />
        </span>
      )}
      <span className="w-12 text-right font-mono text-sm font-bold text-ink-chalk">{row.points}</span>
    </div>
  );
}

/** «Лига клубов»: weekly table of clubs by members' activity; places pay
 * into the club budget. Everything (points, caps, rewards) comes from the
 * server — the page only renders it. */
export default function ClubLeaguePage() {
  const navigate = useNavigate();
  const { data: league, isLoading } = useQuery({ queryKey: ["clubs", "league"], queryFn: fetchClubLeague });

  const header = (
    <div className="flex items-center gap-2">
      <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
        <IconChevronLeft size={18} className="text-ink-chalk" />
      </button>
      <h1 className="font-display text-xl font-bold text-ink-chalk">Лига клубов</h1>
    </div>
  );

  if (isLoading || !league) {
    return (
      <div className="flex flex-col gap-4">
        {header}
        <ListSkeleton />
      </div>
    );
  }
  if (!league.enabled) {
    return (
      <div className="flex flex-col gap-4">
        {header}
        <EmptyState icon={IconTrophy} title="Лига на паузе" description="Лига клубов сейчас выключена. Загляни позже!" />
      </div>
    );
  }

  const mine = league.my_row;
  const myId = mine?.club_id ?? null;
  const inClub = league.members.length > 0;
  const lastMine = league.last_week?.my_row;

  return (
    <div className="flex flex-col gap-4">
      {header}

      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-accent-lime/20 via-bg-surface to-bg-surface p-4 ring-1 ring-accent-lime/20">
        <div className="flex items-center justify-between gap-2 whitespace-nowrap text-[11px] text-ink-mist">
          <span className="font-mono uppercase tracking-wider">Неделя {weekLabel(league.week_start)}</span>
          <span className="flex items-center gap-1 font-mono">
            <IconClock size={12} />
            итоги через {timeLeft(league.ends_at)}
          </span>
        </div>
        {inClub ? (
          mine ? (
            <div className="mt-3 flex items-end justify-between">
              <div>
                <p className="text-xs text-ink-mist">Твой клуб</p>
                <p className="font-display text-3xl font-bold text-ink-chalk">
                  {mine.rank}
                  <span className="text-base text-ink-mist"> место из {league.clubs_count}</span>
                </p>
              </div>
              <div className="text-right">
                <p className="font-mono text-xl font-bold text-accent-lime">{mine.points}</p>
                <p className="text-[11px] text-ink-mist">очков</p>
              </div>
            </div>
          ) : (
            <p className="mt-3 text-sm text-ink-mist">
              У клуба пока нет очков на этой неделе — сыграй матч, открой пак или выполни задание.
            </p>
          )
        ) : (
          <div className="mt-3 flex flex-col gap-2">
            <p className="text-sm text-ink-mist">Вступи в клуб, чтобы твоя активность приносила ему очки и монеты в бюджет.</p>
            <button
              onClick={() => navigate("/clubs")}
              className="self-start rounded-full bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95"
            >
              Найти клуб
            </button>
          </div>
        )}
        {mine && mine.reward > 0 && (
          <p className="mt-2 flex items-center gap-1 text-xs text-ink-mist">
            Если неделя закончится так — клуб получит
            <span className="flex items-center gap-0.5 font-mono font-bold text-accent-lime">
              {mine.reward}
              <IconCoin size={11} />
            </span>
          </p>
        )}
      </section>

      <section className="rounded-2xl bg-bg-surface p-3">
        <p className="mb-2 font-mono text-[11px] uppercase tracking-wider text-ink-mist">Как набрать очки</p>
        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-xl bg-black/20 py-2">
            <p className="font-mono text-base font-bold text-accent-lime">+{league.points_game}</p>
            <p className="text-[10px] text-ink-mist">игра или матч</p>
          </div>
          <div className="rounded-xl bg-black/20 py-2">
            <p className="font-mono text-base font-bold text-accent-lime">+{league.points_pack}</p>
            <p className="text-[10px] text-ink-mist">покупка пака</p>
          </div>
          <div className="rounded-xl bg-black/20 py-2">
            <p className="font-mono text-base font-bold text-accent-lime">+{league.points_task}</p>
            <p className="text-[10px] text-ink-mist">задание</p>
          </div>
        </div>
        <p className="mt-2 text-[11px] text-ink-mist-dim">
          Каждый участник приносит клубу до {league.member_weekly_cap} очков за неделю. Призовые места:{" "}
          {league.rewards.length} — монеты идут в бюджет клуба.
        </p>
      </section>

      <section className="flex flex-col gap-1.5">
        <p className="font-mono text-[11px] uppercase tracking-wider text-ink-mist">Таблица недели</p>
        {league.table.length === 0 && (
          <p className="rounded-xl bg-bg-surface px-3 py-4 text-center text-sm text-ink-mist">
            Пока ни у одного клуба нет очков — стань первым!
          </p>
        )}
        {league.table.map((row, i) => (
          <div key={row.club_id}>
            {i > 0 && row.rank > league.table[i - 1].rank + 1 && <p className="py-1 text-center text-ink-mist-dim">···</p>}
            <Row row={row} mine={row.club_id === myId} />
          </div>
        ))}
      </section>

      {inClub && (
        <section className="rounded-2xl bg-bg-surface p-3">
          <p className="mb-2 flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-wider text-ink-mist">
            <IconUsers size={12} />
            Вклад участников
          </p>
          <div className="flex flex-col divide-y divide-white/5">
            {league.members.map((m) => (
              <div key={m.user_id} className="flex items-center gap-2 py-1.5 text-xs">
                <span className="min-w-0 flex-1 truncate text-ink-chalk">{m.name}</span>
                <span className="text-ink-mist-dim">
                  {m.games} игр · {m.packs} пак. · {m.tasks} зад.
                </span>
                <span
                  className={`w-10 text-right font-mono font-bold ${m.points >= league.member_weekly_cap ? "text-accent-lime" : "text-ink-chalk"}`}
                >
                  {m.points}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {league.last_week && (
        <section className="rounded-2xl bg-bg-surface p-3">
          <p className="mb-2 font-mono text-[11px] uppercase tracking-wider text-ink-mist">
            Прошлая неделя · {weekLabel(league.last_week.week_start)}
          </p>
          <div className="flex flex-col gap-1.5">
            {league.last_week.podium.map((row) => (
              <Row key={row.club_id} row={row} mine={row.club_id === lastMine?.club_id} />
            ))}
            {lastMine && lastMine.rank > 3 && <Row row={lastMine} mine />}
          </div>
          {lastMine && lastMine.reward > 0 && (
            <p className="mt-2 text-xs text-ink-mist">
              Твой клуб получил {lastMine.reward} монет в бюджет за {lastMine.rank} место.
            </p>
          )}
        </section>
      )}
    </div>
  );
}
