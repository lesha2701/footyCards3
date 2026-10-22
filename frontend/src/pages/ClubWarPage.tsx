import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchClubWar } from "@/api/clubFeatures";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconClock, IconCoin } from "@/components/icons";
import { formatCountdown } from "@/lib/format";
import type { ClubWar } from "@/types";

const RESULT_LABELS = { win: "Победа", loss: "Поражение", draw: "Ничья" } as const;
const RESULT_COLORS = { win: "text-accent-green", loss: "text-red-400", draw: "text-ink-mist" } as const;

const secondsUntil = (iso: string) => Math.max(0, Math.floor((new Date(iso).getTime() - Date.now()) / 1000));
const when = (iso: string) =>
  new Date(iso).toLocaleString("ru-RU", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });

function Side({ side, align }: { side: NonNullable<ClubWar["me"]>; align: "left" | "right" }) {
  return (
    <div className={`flex flex-1 flex-col items-center gap-1 ${align === "right" ? "text-right" : "text-left"}`}>
      <ClubLogo shape={side.logo_shape} color={side.logo_color} emblem={side.emblem} size={64} />
      <p className="line-clamp-1 text-center text-xs font-semibold text-ink-chalk">{side.name}</p>
      <p className="text-micro text-ink-mist-dim">рейтинг {side.war_rating}</p>
    </div>
  );
}

/** «Клубные войны»: неделя → 48 часов клуб против клуба; очки — игры, паки и задания участников. */
export default function ClubWarPage() {
  const navigate = useNavigate();
  const { data: war, isLoading } = useQuery({ queryKey: ["clubs", "war"], queryFn: fetchClubWar, refetchInterval: 30_000 });
  if (isLoading || !war) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Клубная война</h1>
        <span className="ml-auto text-caption text-ink-mist-dim">рейтинг {war.war_rating}</span>
      </div>

      {!war.enabled && <p className="rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">Клубные войны сейчас выключены.</p>}

      {war.me && war.opponent ? (
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-red-500/20 via-bg-surface to-accent-cyan/15 p-4">
          <div className="flex items-center justify-between text-caption text-ink-mist">
            {war.state === "active" ? (
              <span className="flex items-center gap-1.5 font-bold text-red-300">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-red-400" /> Идёт бой
              </span>
            ) : (
              <span className={`font-bold ${war.result ? RESULT_COLORS[war.result] : ""}`}>{war.result ? RESULT_LABELS[war.result] : "Итоги"}</span>
            )}
            {war.state === "active" && (
              <span className="flex items-center gap-1"><IconClock size={12} /> {formatCountdown(secondsUntil(war.ends_at))}</span>
            )}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Side side={war.me} align="left" />
            <div className="flex flex-col items-center">
              <span className="font-display text-4xl font-black text-ink-chalk">
                {war.me.score}<span className="mx-1 text-ink-mist-dim">:</span>{war.opponent.score}
              </span>
              <span className="text-micro uppercase tracking-wider text-ink-mist">очки</span>
            </div>
            <Side side={war.opponent} align="right" />
          </div>
        </section>
      ) : (
        <section className="flex flex-col items-center gap-2 rounded-3xl bg-bg-surface p-6 text-center">
          <span className="text-4xl">⚔️</span>
          {war.state === "upcoming" ? (
            <>
              <p className="font-display text-base font-bold text-ink-chalk">Следующая война — {when(war.starts_at)}</p>
              <p className="text-xs text-ink-mist">через {formatCountdown(secondsUntil(war.starts_at))} · длится {war.duration_hours} ч</p>
            </>
          ) : (
            <p className="text-sm text-ink-mist">На этой неделе клубу не нашлось соперника — ждём следующую.</p>
          )}
          {war.member_count < war.min_members && (
            <p className="text-xs text-amber-300">Для участия нужно от {war.min_members} участников (сейчас {war.member_count})</p>
          )}
        </section>
      )}

      <section className="rounded-2xl bg-bg-surface p-3 text-xs text-ink-mist">
        <p className="mb-1 font-display text-sm font-bold text-ink-chalk">Как это работает</p>
        Раз в неделю клуб получает соперника с похожим рейтингом. {war.duration_hours} часов каждая игра, паки и задания
        участников приносят очки. Победа: <b className="text-accent-lime">+{war.win_budget}</b> <IconCoin size={11} className="inline" /> в казну
        и по {war.win_member_coins} монет каждому, ничья: +{war.draw_budget}, поражение: +{war.loss_budget}.
      </section>

      {war.me && war.state === "active" && (
        <section className="flex flex-col gap-1.5">
          <p className="font-display text-sm font-bold text-ink-chalk">Вклад участников</p>
          {war.me.members.length === 0 && <p className="text-xs text-ink-mist-dim">Пока никто не набрал очков — сыграй первым!</p>}
          {war.me.members.map((m) => (
            <div key={m.user_id} className="flex items-center gap-2 rounded-lg bg-bg-surface px-3 py-2 text-xs">
              <span className="min-w-0 flex-1 truncate text-ink-chalk">{m.name}</span>
              <span className="text-ink-mist-dim">
                🎮 {m.games} · 📦 {m.packs} · ✅ {m.tasks}
                {m.ring_points ? ` · 🥊 ${m.ring_points}` : ""}
              </span>
              <span className="w-10 text-right font-mono font-bold text-accent-lime">{m.points}</span>
            </div>
          ))}
        </section>
      )}

      {war.history.length > 0 && (
        <section className="flex flex-col gap-1.5">
          <p className="font-display text-sm font-bold text-ink-chalk">Прошлые войны</p>
          {war.history.map((h) => (
            <div key={h.war_id} className="flex items-center gap-2 rounded-lg bg-bg-surface px-3 py-2 text-xs">
              <span className={`w-20 font-bold ${RESULT_COLORS[h.result]}`}>{RESULT_LABELS[h.result]}</span>
              <span className="min-w-0 flex-1 truncate text-ink-chalk">vs {h.opponent_name}</span>
              <span className="font-mono text-ink-mist">{h.my_score}:{h.opponent_score}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
