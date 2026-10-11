import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  fetchPlayerCareer,
  leavePlayerCareerSeason,
  signPlayerCareerContract,
  startPlayerCareerSeason,
  type PlayerCareerClub,
  type PlayerCareerSeason,
  type PlayerCareerView,
} from "@/api/playerCareer";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconLock, IconProfile, IconTrophy } from "@/components/icons";
import PlayerAvatar from "@/components/myPlayer/PlayerAvatar";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";

function formatWhen(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  const today = new Date();
  const tomorrow = new Date(today.getTime() + 86_400_000);
  const time = d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === today.toDateString()) return `сегодня в ${time}`;
  if (d.toDateString() === tomorrow.toDateString()) return `завтра в ${time}`;
  return `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })} в ${time}`;
}

/** «Карьера игрока»: «Мой игрок» signs for a club built from real cards and
 * plays week-long league seasons (2 rounds a day) — goals, assists, match
 * ratings, reputation, trophies and offers from bigger clubs. */
export default function PlayerCareerPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["player-career"], queryFn: fetchPlayerCareer, refetchInterval: 60_000 });
  const [picking, setPicking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onView = (view: PlayerCareerView) => {
    queryClient.setQueryData(["player-career"], view);
    setError(null);
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));
  const sign = useMutation({
    mutationFn: signPlayerCareerContract,
    onSuccess: (v) => { hapticNotify("success"); onView(v); setPicking(false); },
    onError,
  });
  const start = useMutation({ mutationFn: startPlayerCareerSeason, onSuccess: (v) => { hapticNotify("success"); onView(v); }, onError });

  if (isLoading || !data) return <ListSkeleton />;
  if (!data.enabled) return <EmptyState icon={IconTrophy} title="«Карьера игрока» скоро вернётся" />;
  if (!data.has_player) {
    return (
      <EmptyState
        icon={IconProfile}
        title="Сначала создай своего игрока"
        description="В «Карьере игрока» твой футболист подписывает контракт с клубом и играет за него сезоны."
        action={<button onClick={() => navigate("/my-player")} className="rounded-xl bg-floodlight px-4 py-2 text-sm font-bold text-bg-base">Создать игрока</button>}
      />
    );
  }

  const season = data.season;
  const active = season?.status === "active";

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Карьера игрока</h1>

      <section className="flex items-center gap-3 rounded-2xl bg-bg-surface p-4">
        {data.player && (
          <span className="h-16 w-16 shrink-0 overflow-hidden rounded-xl">
            <PlayerAvatar appearance={data.player.appearance} accessory={data.player.accessory} backdrop={data.player.background} number={data.player.number} className="h-full w-full" />
          </span>
        )}
        <span className="min-w-0 flex-1">
          <span className="block truncate font-display text-base font-bold text-ink-chalk">
            {data.player?.name} · {data.rating}
          </span>
          <span className="block text-xs text-ink-mist">
            {data.club ? `Клуб: ${data.club.name} (${data.club.rating})` : "Без клуба"} · репутация {data.reputation}
          </span>
          {data.career && data.career.seasons > 0 && (
            <span className="block text-[11px] text-ink-mist-dim">
              Сезонов {data.career.seasons} · матчей {data.career.matches} · голов {data.career.goals} · передач {data.career.assists}
              {data.career.titles > 0 && ` · титулов ${data.career.titles}`}
            </span>
          )}
        </span>
      </section>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      {(!data.club || picking) && data.can_change_club ? (
        <ClubPicker
          view={data}
          busy={sign.isPending}
          onPick={(club) => sign.mutate(club.key)}
          onCancel={data.club ? () => setPicking(false) : undefined}
        />
      ) : (
        <>
          {season && <SeasonBlock season={season} view={data} onView={onView} onError={onError} />}
          {!active && data.club && (
            <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
              <p className="text-sm text-ink-mist">
                Сезон: 8 клубов твоего уровня, 14 туров по два в день. За результат +{data.rewards?.win}/{data.rewards?.draw} монет,
                за гол +{data.rewards?.goal}, за матч +{data.rewards?.xp} опыта, в конце — награда за место и трофеи.
              </p>
              <button
                disabled={start.isPending}
                onClick={() => start.mutate()}
                className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base disabled:opacity-40 active:scale-[0.99]"
              >
                {season ? "Новый сезон" : "Начать сезон"} за «{data.club.name}»
              </button>
              <button onClick={() => setPicking(true)} className="rounded-2xl bg-bg-raised py-2.5 text-sm font-semibold text-ink-chalk">
                Сменить клуб
              </button>
            </section>
          )}
        </>
      )}
    </div>
  );
}

function ClubPicker({
  view, busy, onPick, onCancel,
}: { view: PlayerCareerView; busy: boolean; onPick: (c: PlayerCareerClub) => void; onCancel?: () => void }) {
  const open = view.clubs.filter((c) => !c.locked_reason);
  const locked = view.clubs.filter((c) => c.locked_reason);
  return (
    <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">Выбери клуб</h2>
        {onCancel && <button onClick={onCancel} className="text-xs text-ink-mist">Отмена</button>}
      </div>
      <p className="text-[11px] text-ink-mist">
        Клубы собраны из карточек игры: состав — лучшие карточки клуба, рейтинг — средний по основе. Чем выше твой рейтинг и
        репутация, тем сильнее клуб, за который можно играть.
      </p>
      {[...open, ...locked].map((club) => (
        <button
          key={club.key}
          disabled={!!club.locked_reason || busy || club.key === view.club?.key}
          onClick={() => onPick(club)}
          className={`flex items-center gap-3 rounded-xl p-3 text-left disabled:cursor-default ${
            club.key === view.club?.key ? "bg-accent-lime/15 ring-2 ring-accent-lime" : "bg-bg-raised"
          } ${club.locked_reason ? "opacity-60" : ""}`}
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-bg-surface font-display text-sm font-black text-ink-chalk">
            {club.rating}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-ink-chalk">{club.name}</span>
            <span className="block truncate text-[11px] text-ink-mist">
              {club.is_demo ? "Клуб лиги" : `${club.real_cards} карточек · ${club.stars.join(", ")}`}
            </span>
          </span>
          {club.locked_reason ? (
            <span className="flex shrink-0 items-center gap-1 text-[10px] text-ink-mist"><IconLock size={12} /> {club.locked_reason}</span>
          ) : club.key === view.club?.key ? (
            <span className="text-xs font-bold text-accent-lime">твой</span>
          ) : (
            <span className="rounded-lg bg-floodlight px-2.5 py-1 text-xs font-bold text-bg-base">Подписать</span>
          )}
        </button>
      ))}
    </section>
  );
}

type Tab = "overview" | "table" | "calendar" | "scorers";

function SeasonBlock({
  season, view, onView, onError,
}: { season: PlayerCareerSeason; view: PlayerCareerView; onView: (v: PlayerCareerView) => void; onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");
  const [confirmLeave, setConfirmLeave] = useState(false);
  const leave = useMutation({ mutationFn: leavePlayerCareerSeason, onSuccess: onView, onError });
  const sign = useMutation({
    mutationFn: signPlayerCareerContract,
    onSuccess: (v) => { hapticNotify("success"); onView(v); void queryClient.invalidateQueries({ queryKey: ["my-player"] }); },
    onError,
  });
  const active = season.status === "active";
  const teams = season.teams;
  const last = [...season.rounds].reverse().find((r) => r.me);

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">
          {active ? `Сезон · тур ${season.rounds_played + 1} из ${season.total_rounds}` : `Сезон завершён · ${season.final_place} место`}
        </h2>
        <span className="text-xs text-ink-mist">+{season.coins_earned} монет</span>
      </div>

      <div className="grid grid-cols-4 gap-1 rounded-xl bg-bg-raised p-1">
        {([["overview", "Обзор"], ["table", "Таблица"], ["calendar", "Матчи"], ["scorers", "Бомбардиры"]] as [Tab, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`rounded-lg py-1.5 text-[11px] font-semibold ${tab === id ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <div className="flex flex-col gap-3">
          <div className="grid grid-cols-4 gap-2 text-center">
            {[["Матчи", season.stats.matches], ["Голы", season.stats.goals], ["Пасы", season.stats.assists], ["Оценка", season.stats.avg_rating ?? "—"]].map(([label, value]) => (
              <div key={label} className="rounded-xl bg-bg-raised py-2">
                <p className="font-display text-lg font-black text-ink-chalk">{value}</p>
                <p className="text-[10px] text-ink-mist">{label}</p>
              </div>
            ))}
          </div>
          {active && season.next_round_at && (
            <p className="text-sm text-ink-mist">Следующий тур: <b className="text-ink-chalk">{formatWhen(season.next_round_at)}</b></p>
          )}
          {last?.me && (
            <p className="rounded-xl bg-bg-raised px-3 py-2 text-sm text-ink-chalk">
              Последний матч: {last.me.own}:{last.me.opp} с «{last.me.opponent}»
              {last.me.goals > 0 && ` · ⚽ ${last.me.goals}`}{last.me.assists > 0 && ` · 🅰️ ${last.me.assists}`}
              {last.me.rating != null && ` · оценка ${last.me.rating}`}
            </p>
          )}
          {!active && season.awards.length > 0 && (
            <p className="rounded-xl bg-amber-400/15 px-3 py-2 text-sm font-semibold text-amber-300">🏆 {season.awards.join(" · ")}</p>
          )}
          {!active && season.offers.length > 0 && (
            <div className="flex flex-col gap-2 rounded-xl bg-accent-lime/10 p-3">
              <p className="text-sm font-bold text-accent-lime">Предложения от клубов</p>
              {season.offers.map((o) => (
                <div key={o.key} className="flex items-center justify-between">
                  <span className="text-sm text-ink-chalk">{o.name} <span className="text-ink-mist">· {o.rating}</span></span>
                  <button
                    disabled={sign.isPending || o.key === view.club?.key}
                    onClick={() => sign.mutate(o.key)}
                    className="rounded-lg bg-floodlight px-3 py-1 text-xs font-bold text-bg-base disabled:opacity-40"
                  >
                    {o.key === view.club?.key ? "Подписан" : "Перейти"}
                  </button>
                </div>
              ))}
            </div>
          )}
          {active && (
            <button onClick={() => setConfirmLeave(true)} className="text-xs text-ink-mist-dim">Покинуть сезон</button>
          )}
        </div>
      )}

      {tab === "table" && (
        <table className="w-full text-left text-xs">
          <thead className="text-ink-mist">
            <tr><th className="py-1">#</th><th>Клуб</th><th className="text-center">И</th><th className="text-center">Р</th><th className="text-center">О</th></tr>
          </thead>
          <tbody>
            {season.table.map((row, i) => {
              const team = teams[row.team_index];
              return (
                <tr key={row.team_index} className={team?.is_mine ? "font-bold text-accent-lime" : "text-ink-chalk"}>
                  <td className="py-1.5">{i + 1}</td>
                  <td className="max-w-[9rem] truncate">{team?.name} <span className="text-ink-mist-dim">{team?.rating}</span></td>
                  <td className="text-center">{row.played}</td>
                  <td className="text-center">{row.gf - row.ga}</td>
                  <td className="text-center">{row.points}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      {tab === "calendar" && (
        <div className="flex flex-col divide-y divide-white/5">
          {season.rounds.map((r) => {
            const homeMine = r.home === 0;
            const opp = teams[(homeMine ? r.away : r.home) ?? 0];
            const played = r.hs != null;
            const own = homeMine ? r.hs : r.away_score;
            const them = homeMine ? r.away_score : r.hs;
            return (
              <div key={r.index} className="flex items-center gap-3 py-2">
                <span className="w-6 font-mono text-[10px] text-ink-mist">{r.index + 1}</span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-ink-chalk">{homeMine ? "vs" : "@"} {opp?.name}</span>
                  <span className="block text-[10px] text-ink-mist-dim">
                    {played && r.me
                      ? [r.me.goals > 0 && `⚽ ${r.me.goals}`, r.me.assists > 0 && `🅰️ ${r.me.assists}`, r.me.rating != null && `оценка ${r.me.rating}`].filter(Boolean).join(" · ")
                      : formatWhen(r.at)}
                  </span>
                </span>
                {played && (
                  <span className={`font-mono text-sm font-bold ${own! > them! ? "text-accent-lime" : own === them ? "text-ink-mist" : "text-red-400"}`}>
                    {own}:{them}
                  </span>
                )}
              </div>
            );
          })}
        </div>
      )}

      {tab === "scorers" && (
        <div className="flex flex-col divide-y divide-white/5">
          {season.scorers.length === 0 && <p className="py-3 text-center text-sm text-ink-mist">Пока никто не забил</p>}
          {season.scorers.map((s, i) => (
            <div key={`${s.team}-${s.name}`} className={`flex items-center gap-3 py-2 text-sm ${s.name === view.player?.name && s.team === teams[0]?.name ? "font-bold text-accent-lime" : "text-ink-chalk"}`}>
              <span className="w-6 font-mono text-xs text-ink-mist">{i + 1}</span>
              <span className="min-w-0 flex-1 truncate">{s.name} <span className="text-ink-mist">· {s.team}</span></span>
              <span className="font-mono font-bold">{s.goals}</span>
            </div>
          ))}
        </div>
      )}

      {confirmLeave && (
        <ConfirmDialog
          open
          title="Покинуть сезон?"
          description="Сезон закончится без награды за место. Заработанные монеты останутся."
          confirmLabel="Покинуть"
          danger
          onConfirm={() => { setConfirmLeave(false); leave.mutate(); }}
          onCancel={() => setConfirmLeave(false)}
        />
      )}
    </section>
  );
}
