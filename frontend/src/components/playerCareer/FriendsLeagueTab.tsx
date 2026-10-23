import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  cancelFriendsLeague,
  createFriendsLeague,
  fetchFriendsLeague,
  respondFriendsLeague,
  startFriendsLeague,
  type FriendsLeague,
  type FriendsLeagueView,
} from "@/api/playerCareer";
import { ListSkeleton } from "@/components/common/Skeleton";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";

function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("ru-RU", { day: "numeric", month: "short" })} в ${d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

/** «Лига друзей»: invite friends, play 7 rounds for your clubs; friend v
 * friend is a derby with bigger rewards and a head-to-head record. */
export default function FriendsLeagueTab({ hasClub }: { hasClub: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["player-career", "friends"], queryFn: fetchFriendsLeague, refetchInterval: 60_000 });
  const [picked, setPicked] = useState<number[]>([]);
  const [error, setError] = useState<string | null>(null);
  const onData = (v: FriendsLeagueView) => { setError(null); queryClient.setQueryData(["player-career", "friends"], v); };
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));
  const create = useMutation({ mutationFn: () => createFriendsLeague(picked), onSuccess: (v) => { hapticNotify("success"); setPicked([]); onData(v); }, onError });
  const respond = useMutation({
    mutationFn: ({ id, accept }: { id: number; accept: boolean }) => respondFriendsLeague(id, accept), onSuccess: onData, onError,
  });
  const start = useMutation({ mutationFn: (id: number) => startFriendsLeague(id), onSuccess: (v) => { hapticNotify("success"); onData(v); }, onError });
  const cancel = useMutation({ mutationFn: (id: number) => cancelFriendsLeague(id), onSuccess: onData, onError });

  if (isLoading || !data) return <ListSkeleton />;
  const league = data.league;
  return (
    <div className="flex flex-col gap-4" data-testid="friends-league">
      <section className="rounded-2xl bg-gradient-to-br from-accent-cyan/20 to-bg-surface p-4">
        <p className="font-display text-base font-bold text-ink-chalk">🤝 Лига друзей</p>
        <p className="mt-1 text-caption text-ink-mist">
          До 8 друзей, каждый за свой клуб, 7 туров. Матч друг с другом — дерби: награды ×{data.derby_multiplier}. Места 1–3:
          {" "}{data.rewards.join(" / ")} монет и трофей чемпиону.
        </p>
      </section>
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      {data.invites.map((inv) => (
        <section key={inv.id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-4">
          <span className="min-w-0 flex-1 text-sm text-ink-chalk"><b>{inv.owner_name}</b> зовёт тебя в лигу друзей</span>
          <button onClick={() => respond.mutate({ id: inv.id, accept: true })} className="rounded-lg bg-floodlight px-3 py-1.5 text-xs font-bold text-bg-base">Вступить</button>
          <button onClick={() => respond.mutate({ id: inv.id, accept: false })} className="rounded-lg bg-bg-raised px-3 py-1.5 text-xs text-ink-mist">Нет</button>
        </section>
      ))}

      {league && <LeagueBlock league={league} busy={start.isPending || cancel.isPending} onStart={() => start.mutate(league.id)} onCancel={() => cancel.mutate(league.id)} />}

      {data.can_create && (
        <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
          <h2 className="font-display text-base font-bold text-ink-chalk">Новая лига</h2>
          {!hasClub ? (
            <p className="text-sm text-ink-mist">Сначала подпиши контракт с клубом.</p>
          ) : data.friends.length === 0 ? (
            <div className="text-center">
              <p className="text-sm text-ink-mist">У друзей пока нет игроков с клубом.</p>
              <button onClick={() => navigate("/friends")} className="mt-2 rounded-xl bg-bg-raised px-4 py-2 text-xs font-semibold text-ink-chalk">Позвать друзей</button>
            </div>
          ) : (
            <>
              {data.friends.map((f) => {
                const on = picked.includes(f.user_id);
                return (
                  <button
                    key={f.user_id}
                    onClick={() => setPicked((p) => (on ? p.filter((x) => x !== f.user_id) : p.length < 7 ? [...p, f.user_id] : p))}
                    className={`flex items-center justify-between rounded-xl p-3 text-left ${on ? "bg-accent-lime/15 ring-2 ring-accent-lime" : "bg-bg-raised"}`}
                  >
                    <span className="text-sm text-ink-chalk">{f.player_name} <span className="text-ink-mist">· {f.name}</span></span>
                    <span className="text-xs font-bold text-accent-lime">{on ? "✓" : ""}</span>
                  </button>
                );
              })}
              <button
                disabled={!picked.length || create.isPending}
                onClick={() => create.mutate()}
                className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base disabled:opacity-40"
              >
                Позвать ({picked.length})
              </button>
            </>
          )}
        </section>
      )}
    </div>
  );
}

function LeagueBlock({ league, busy, onStart, onCancel }: { league: FriendsLeague; busy: boolean; onStart: () => void; onCancel: () => void }) {
  if (league.status === "lobby") {
    const joined = league.members.filter((m) => m.status === "accepted").length;
    return (
      <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4" data-testid="friends-lobby">
        <h2 className="font-display text-base font-bold text-ink-chalk">Сбор лиги · {league.owner_name}</h2>
        {league.members.map((m) => (
          <p key={m.user_id} className="flex justify-between text-sm text-ink-chalk">
            {m.name}
            <span className={m.status === "accepted" ? "text-accent-lime" : m.status === "declined" ? "text-red-400" : "text-ink-mist"}>
              {m.status === "accepted" ? "в лиге" : m.status === "declined" ? "отказался" : "ждём ответа"}
            </span>
          </p>
        ))}
        {league.is_owner ? (
          <div className="mt-1 grid grid-cols-2 gap-2">
            <button disabled={busy || joined < 2} onClick={onStart} className="rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-40">
              Начать ({joined})
            </button>
            <button disabled={busy} onClick={onCancel} className="rounded-xl bg-bg-raised py-2.5 text-sm text-ink-mist">Отменить</button>
          </div>
        ) : (
          <p className="text-caption text-ink-mist">Ждём, когда {league.owner_name} начнёт лигу</p>
        )}
      </section>
    );
  }
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4" data-testid="friends-active">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">
          {league.status === "finished" ? `Лига завершена${league.champion ? ` · 🏆 ${league.champion}` : ""}` : `Тур ${league.rounds_played + 1} из ${league.total_rounds}`}
        </h2>
      </div>
      {league.status === "active" && league.next_round_at && (
        <p className="text-sm text-ink-mist">Следующий тур: <b className="text-ink-chalk">{when(league.next_round_at)}</b></p>
      )}
      <table className="w-full text-left text-xs">
        <thead className="text-ink-mist">
          <tr><th className="py-1">#</th><th>Клуб</th><th className="text-center">И</th><th className="text-center">Р</th><th className="text-center">О</th></tr>
        </thead>
        <tbody>
          {league.table.map((row, i) => (
            <tr key={row.team_index} className={row.is_me ? "font-bold text-accent-lime" : row.is_friend ? "text-ink-chalk" : "text-ink-mist"}>
              <td className="py-1.5">{i + 1}</td>
              <td className="max-w-[10rem] truncate">{row.name}{row.owner_name && <span className="text-ink-mist-dim"> · {row.owner_name}</span>}</td>
              <td className="text-center">{row.played}</td>
              <td className="text-center">{row.gf - row.ga}</td>
              <td className="text-center">{row.points}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {league.h2h.length > 0 && (
        <div className="rounded-xl bg-bg-raised p-3">
          <p className="mb-1 text-xs font-bold text-ink-chalk">Личные встречи</p>
          {league.h2h.map((h) => (
            <p key={h.name} className="text-xs text-ink-mist">{h.name}: {h.won}–{h.drawn}–{h.lost}</p>
          ))}
        </div>
      )}
      <div className="rounded-xl bg-bg-raised p-3">
        <p className="mb-1 text-xs font-bold text-ink-chalk">Игроки</p>
        {league.players.map((p) => (
          <p key={p.name} className={`flex justify-between text-xs ${p.is_me ? "font-bold text-accent-lime" : "text-ink-chalk"}`}>
            <span className="truncate">{p.name} · {p.team}</span>
            <span>⚽ {p.goals} · 🅰️ {p.assists}{p.avg_rating != null ? ` · ${p.avg_rating}` : ""}</span>
          </p>
        ))}
      </div>
      <div className="flex flex-col gap-2">
        {league.rounds.map((r) => {
          const mine = r.matches.find((m) => m.mine);
          if (!mine) return null;
          return (
            <div key={r.index} className={`flex items-center gap-2 rounded-xl p-2 text-xs ${mine.derby ? "bg-fuchsia-500/15" : "bg-bg-raised"}`}>
              <span className="w-10 font-mono text-ink-mist">Т{r.index + 1}</span>
              <span className="min-w-0 flex-1 truncate text-ink-chalk">{mine.home} — {mine.away}{mine.derby && " · 🔥 дерби"}</span>
              <span className="font-mono font-bold text-ink-chalk">{mine.hs != null ? `${mine.hs}:${mine.away_score}` : when(r.at)}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
