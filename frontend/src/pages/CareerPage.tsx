import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import {
  createCareerSeason,
  fetchCareer,
  leaveCareer,
  respondCareerInvite,
  setCareerLineup,
  startCareerWithoutFriend,
  type CareerSeason,
  type CareerSlot,
  type CareerSquadCard,
  type CareerRoundReport,
  type CareerView,
} from "@/api/career";
import { fetchFriends } from "@/api/friends";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronRight, IconClock, IconCoin, IconFlagCheckered, IconTrophy, IconUsers } from "@/components/icons";
import { FORMATIONS, MENTALITIES, PLAYSTYLES } from "@/lib/clubTactics";
import { formatGameError } from "@/lib/errors";
import { CATEGORY_POSITIONS } from "@/lib/formation";
import { haptic } from "@/lib/telegram";

type Tab = "squad" | "table" | "calendar";

/** Round times in the viewer's own time zone (the server schedules them in
 * its own one, e.g. 12:00/19:00 Moscow). */
function localSlots(view: CareerView): string[] {
  if (!view.slot_times?.length) return view.slots;
  return view.slot_times.map((t) => new Date(t).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }));
}

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

/** "Карьера тренера": a weekly 8-team league (14 rounds, 12:00 and 19:00
 * daily) with the player's own cards, solo or together with a friend. */
export default function CareerPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["career"], queryFn: fetchCareer, refetchInterval: 60_000 });
  const [error, setError] = useState<string | null>(null);
  const onView = (view: CareerView) => {
    setError(null);
    queryClient.setQueryData(["career"], view);
    queryClient.invalidateQueries({ queryKey: ["attention"] });
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));

  if (isLoading || !data) return <ListSkeleton count={4} />;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconFlagCheckered size={20} className="text-accent-lime" />
        Карьера тренера
      </h1>
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      {data.invite && <InviteCard view={data} onView={onView} onError={onError} />}

      {!data.season || data.season.status === "finished" || data.season.my_status === "left" ? (
        <>
          {data.season?.status === "finished" && <FinishedCard season={data.season} />}
          {data.season?.my_status === "left" && data.season.status !== "finished" && (
            <p className="rounded-2xl bg-bg-surface p-4 text-sm text-ink-mist">Ты покинул сезон. Можно начать новый.</p>
          )}
          {!data.invite && <NewSeason view={data} onView={onView} onError={onError} />}
        </>
      ) : data.season.status === "pending" ? (
        <PendingCard season={data.season} onView={onView} onError={onError} />
      ) : (
        <ActiveSeason season={data.season} onView={onView} onError={onError} />
      )}
    </div>
  );
}

type Handlers = { onView: (v: CareerView) => void; onError: (e: unknown) => void };

function NewSeason({ view, onView, onError }: { view: CareerView } & Handlers) {
  const [params] = useSearchParams();
  const presetFriend = Number(params.get("friend")) || null;
  const [difficulty, setDifficulty] = useState("pro");
  const [withFriend, setWithFriend] = useState<boolean>(!!presetFriend);
  const [friendId, setFriendId] = useState<number | null>(presetFriend);
  const { data: friends } = useQuery({ queryKey: ["friends"], queryFn: fetchFriends, enabled: withFriend });
  const create = useMutation({
    mutationFn: () => createCareerSeason(difficulty, withFriend ? friendId ?? undefined : undefined),
    onSuccess: (v) => { haptic("medium"); onView(v); },
    onError,
  });

  if (!view.enabled) {
    return <p className="rounded-2xl bg-bg-surface p-4 text-sm text-ink-mist">Карьера сейчас недоступна — загляни позже.</p>;
  }
  const pct = view.difficulties.find((d) => d.code === difficulty)?.reward_pct ?? 100;
  return (
    <section className="flex flex-col gap-4 rounded-3xl bg-bg-surface p-4">
      <div className="text-sm text-ink-mist">
        <p className="font-display text-base font-bold text-ink-chalk">Сезон на неделю</p>
        <p className="mt-1">
          8 команд, 14 туров — по два в день, в {localSlots(view).join(" и ")}. Играешь своими карточками: заявка из 16
          игроков, следи за усталостью и травмами. Вход бесплатный.
        </p>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-semibold text-ink-mist">Сложность</p>
        <div className="grid grid-cols-3 gap-1 rounded-xl bg-bg-raised p-1">
          {view.difficulties.map((d) => (
            <button
              key={d.code}
              onClick={() => setDifficulty(d.code)}
              className={`rounded-lg py-2 text-xs font-semibold ${difficulty === d.code ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
            >
              {d.label}
            </button>
          ))}
        </div>
        <p className="mt-1.5 flex items-center gap-1 text-[11px] text-ink-mist">
          Чемпиону: {Math.round(((view.place_rewards[0] ?? 0) * pct) / 100)} <IconCoin size={11} className="text-accent-lime" /> и трофей
        </p>
      </div>

      <label className="flex items-center justify-between gap-3 text-sm text-ink-chalk">
        <span className="flex items-center gap-2"><IconUsers size={16} className="text-accent-lime" /> Сезон с другом</span>
        <input type="checkbox" checked={withFriend} onChange={(e) => setWithFriend(e.target.checked)} className="h-5 w-5 accent-accent-lime" />
      </label>
      {withFriend && (
        <div className="flex flex-col gap-1.5">
          {!friends?.friends.length ? (
            <p className="text-xs text-ink-mist">Пока нет друзей — добавь их в разделе «Друзья» в профиле.</p>
          ) : (
            friends.friends.map(({ user }) => (
              <button
                key={user.id}
                onClick={() => setFriendId(user.id)}
                className={`rounded-xl px-3 py-2 text-left text-sm ${friendId === user.id ? "bg-accent-lime/15 text-accent-lime" : "bg-bg-raised text-ink-chalk"}`}
              >
                {user.first_name || user.username || "Игрок"}
              </button>
            ))
          )}
          <p className="text-[11px] text-ink-mist-dim">Друг будет в той же лиге: два личных матча, общая таблица. Если не ответит за сутки — его место займёт бот.</p>
        </div>
      )}

      <button
        onClick={() => create.mutate()}
        disabled={create.isPending || (withFriend && !friendId)}
        className="rounded-2xl bg-floodlight py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {create.isPending ? "Собираем лигу..." : withFriend ? "Пригласить и начать" : "Начать сезон"}
      </button>
    </section>
  );
}

function InviteCard({ view, onView, onError }: { view: CareerView } & Handlers) {
  const invite = view.invite!;
  const respond = useMutation({ mutationFn: (accept: boolean) => respondCareerInvite(invite.season_id, accept), onSuccess: onView, onError });
  return (
    <section className="rounded-3xl bg-accent-lime/10 p-4 ring-1 ring-accent-lime/30">
      <p className="font-display text-base font-bold text-ink-chalk">{invite.from_name} зовёт в общий сезон</p>
      <p className="mt-1 text-xs text-ink-mist">
        Сложность: {invite.difficulty_label}. Ответить до {formatWhen(invite.expires_at)}.
      </p>
      <div className="mt-3 flex gap-2">
        <button onClick={() => respond.mutate(true)} disabled={respond.isPending} className="flex-1 rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-50">
          Принять
        </button>
        <button onClick={() => respond.mutate(false)} disabled={respond.isPending} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist disabled:opacity-50">
          Отказаться
        </button>
      </div>
    </section>
  );
}

function PendingCard({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const queryClient = useQueryClient();
  const start = useMutation({ mutationFn: () => startCareerWithoutFriend(season.id), onSuccess: onView, onError });
  const cancel = useMutation({
    mutationFn: leaveCareer,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["career"] }),
    onError,
  });
  const friend = season.participants.find((p) => p.status === "invited");
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <p className="font-display text-base font-bold text-ink-chalk">Ждём ответа {friend?.name ?? "друга"}</p>
      <p className="flex items-center gap-1.5 text-xs text-ink-mist">
        <IconClock size={13} /> Если не ответит до {formatWhen(season.invite_expires_at)}, сезон начнётся с ботом вместо него.
      </p>
      {season.is_creator && (
        <div className="flex gap-2">
          <button onClick={() => start.mutate()} disabled={start.isPending} className="flex-1 rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-50">
            Начать без друга
          </button>
          <button onClick={() => cancel.mutate()} disabled={cancel.isPending} className="rounded-xl bg-white/5 px-4 py-2.5 text-sm font-semibold text-ink-mist disabled:opacity-50">
            Отменить
          </button>
        </div>
      )}
    </section>
  );
}

function FinishedCard({ season }: { season: CareerSeason }) {
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div className="flex items-center gap-3">
        <IconTrophy size={28} className={season.final_place === 1 ? "text-rarity-legendary" : "text-ink-mist"} />
        <div>
          <p className="font-display text-base font-bold text-ink-chalk">
            {season.final_place ? `Сезон завершён: ${season.final_place} место` : "Сезон завершён"}
          </p>
          <p className="flex items-center gap-1 text-xs text-ink-mist">
            Заработано: {season.coins_earned} <IconCoin size={11} className="text-accent-lime" />
          </p>
        </div>
      </div>
      <StandingsTable season={season} />
    </section>
  );
}

function ActiveSeason({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const [tab, setTab] = useState<Tab>("squad");
  const [confirmLeave, setConfirmLeave] = useState(false);
  const queryClient = useQueryClient();
  const leave = useMutation({
    mutationFn: leaveCareer,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["career"] }),
    onError,
  });
  const nextRound = season.rounds[season.rounds_played];
  const myMatch = nextRound?.matches.find((m) => m.home === season.my_team_index || m.away === season.my_team_index);
  const opponent = myMatch ? season.teams[myMatch.home === season.my_team_index ? myMatch.away : myMatch.home] : null;
  const myRow = season.table.findIndex((r) => r.team_index === season.my_team_index);

  return (
    <>
      <section className="rounded-3xl bg-bg-surface p-4">
        <div className="flex items-center justify-between text-xs text-ink-mist">
          <span>{season.difficulty_label} · тур {Math.min(season.rounds_played + 1, season.total_rounds)} из {season.total_rounds}</span>
          <span>{myRow >= 0 ? `${myRow + 1} место` : ""}</span>
        </div>
        {opponent && myMatch && (
          <div className="mt-3 flex items-center gap-3">
            <div className="min-w-0 flex-1">
              <p className="text-[10px] uppercase tracking-wider text-ink-mist">Следующий матч · {formatWhen(nextRound.at)}</p>
              <p className="truncate font-display text-base font-bold text-ink-chalk">
                {myMatch.home === season.my_team_index ? "Дома" : "В гостях"}: {opponent.name}
              </p>
              <p className="text-xs text-ink-mist">
                {opponent.is_bot ? `Сила соперника ~${opponent.strength ?? "?"}` : "Матч с другом"}
              </p>
            </div>
          </div>
        )}
      </section>

      <div className="grid grid-cols-3 gap-1 rounded-2xl bg-bg-surface p-1">
        {([["squad", "Состав"], ["table", "Таблица"], ["calendar", "Календарь"]] as [Tab, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`rounded-xl py-2 text-xs font-semibold ${tab === id ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "squad" && <LineupEditor season={season} onView={onView} onError={onError} />}
      {tab === "table" && <section className="rounded-3xl bg-bg-surface p-4"><StandingsTable season={season} /></section>}
      {tab === "calendar" && <Calendar season={season} />}

      <button onClick={() => setConfirmLeave(true)} className="self-center text-xs text-ink-mist-dim underline underline-offset-2">
        Покинуть сезон
      </button>
      <ConfirmDialog
        open={confirmLeave}
        title="Покинуть сезон?"
        description="Оставшиеся матчи будут засчитаны поражениями 0:3, награда за место не начислится."
        danger
        confirmLabel="Покинуть"
        onConfirm={() => { setConfirmLeave(false); leave.mutate(); }}
        onCancel={() => setConfirmLeave(false)}
      />
    </>
  );
}

function StandingsTable({ season }: { season: CareerSeason }) {
  return (
    <table className="w-full text-xs">
      <thead>
        <tr className="text-ink-mist-dim">
          <th className="pb-1 text-left font-normal">#</th>
          <th className="pb-1 text-left font-normal">Команда</th>
          <th className="pb-1 text-right font-normal">И</th>
          <th className="pb-1 text-right font-normal">Р</th>
          <th className="pb-1 text-right font-normal">О</th>
        </tr>
      </thead>
      <tbody>
        {season.table.map((row, i) => {
          const team = season.teams[row.team_index];
          const me = row.team_index === season.my_team_index;
          return (
            <tr key={row.team_index} className={me ? "font-bold text-accent-lime" : !team.is_bot ? "text-accent-cyan" : "text-ink-chalk"}>
              <td className="py-1">{i + 1}</td>
              <td className="max-w-[10rem] truncate py-1">{team.name}</td>
              <td className="py-1 text-right font-mono">{row.played}</td>
              <td className="py-1 text-right font-mono">{row.gf - row.ga > 0 ? "+" : ""}{row.gf - row.ga}</td>
              <td className="py-1 text-right font-mono">{row.points}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function Calendar({ season }: { season: CareerSeason }) {
  const navigate = useNavigate();
  return (
    <section className="flex flex-col gap-2">
      {season.rounds.map((round) => {
        const index = round.matches.findIndex((m) => m.home === season.my_team_index || m.away === season.my_team_index);
        const m = round.matches[index];
        if (!m) return null;
        const home = m.home === season.my_team_index;
        const opp = season.teams[home ? m.away : m.home];
        const played = m.hs !== null && m.as !== null;
        const own = played ? (home ? m.hs! : m.as!) : 0;
        const theirs = played ? (home ? m.as! : m.hs!) : 0;
        const tone = !played ? "text-ink-mist" : own > theirs ? "text-accent-lime" : own < theirs ? "text-red-400" : "text-ink-chalk";
        return (
          <button
            key={round.index}
            disabled={!m.has_events}
            onClick={() => navigate(`/play/career/seasons/${season.id}/rounds/${round.index}/matches/${index}`)}
            className="flex items-center gap-3 rounded-2xl bg-bg-surface px-3 py-2.5 text-left disabled:cursor-default"
          >
            <span className="w-10 shrink-0 font-mono text-[11px] text-ink-mist">Тур {round.index + 1}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-ink-chalk">{home ? "vs" : "@"} {opp.name}</span>
              <span className="block text-[10px] text-ink-mist-dim">{formatWhen(round.at)}</span>
              {round.report && <RoundReport report={round.report} />}
            </span>
            <span className={`font-mono text-sm font-bold ${tone}`}>{played ? `${own}:${theirs}` : "—"}</span>
            {m.has_events && <IconChevronRight size={14} className="text-ink-mist-dim" />}
          </button>
        );
      })}
    </section>
  );
}

function RoundReport({ report }: { report: CareerRoundReport }) {
  const parts: { text: string; tone: string }[] = [];
  if (report.red.length) parts.push({ text: `красная: ${report.red.join(", ")}`, tone: "text-red-400" });
  if (report.suspended.length) parts.push({ text: `дисквал.: ${report.suspended.join(", ")}`, tone: "text-red-400" });
  if (report.yellow.length) parts.push({ text: `жёлтые: ${report.yellow.join(", ")}`, tone: "text-yellow-300" });
  if (report.injured.length) parts.push({ text: `травма: ${report.injured.join(", ")}`, tone: "text-red-400" });
  if (report.form_up.length) parts.push({ text: `в форме: ${report.form_up.join(", ")}`, tone: "text-accent-lime" });
  if (!parts.length) return null;
  return (
    <span className="mt-0.5 block text-[10px] leading-snug">
      {parts.map((p, i) => (
        <span key={i} className={`${p.tone} block truncate`}>{p.text}</span>
      ))}
    </span>
  );
}

function FatigueBar({ value }: { value: number }) {
  const color = value > 70 ? "bg-red-400" : value > 40 ? "bg-amber-400" : "bg-accent-lime";
  return (
    <span className="block h-1 w-12 overflow-hidden rounded-full bg-white/10" title={`Усталость ${value}%`}>
      <span className={`block h-full ${color}`} style={{ width: `${value}%` }} />
    </span>
  );
}

function LineupEditor({ season, onView, onError }: { season: CareerSeason } & Handlers) {
  const [slots, setSlots] = useState<Record<string, number>>(season.lineup);
  const [mentality, setMentality] = useState(season.mentality);
  const [playstyle, setPlaystyle] = useState(season.playstyle);
  const [picking, setPicking] = useState<CareerSlot | null>(null);
  // Reset the local edit only when the saved lineup itself changes — not on
  // every background refetch, which would wipe unsaved changes each minute.
  const savedKey = JSON.stringify(season.lineup);
  useEffect(() => setSlots(JSON.parse(savedKey)), [savedKey]);
  const byId = useMemo(() => new Map(season.squad.map((s) => [s.card_id, s])), [season.squad]);
  const save = useMutation({
    mutationFn: (payload: { formation?: string; slots?: Record<string, number> }) =>
      setCareerLineup({
        slots: payload.slots ?? slots, formation: payload.formation ?? season.formation, mentality, playstyle,
      }),
    onSuccess: (v) => { haptic("light"); onView(v); },
    onError,
  });
  const dirty = JSON.stringify(slots) !== JSON.stringify(season.lineup) || mentality !== season.mentality || playstyle !== season.playstyle;
  const inLineup = new Set(Object.values(slots));
  const bench = season.squad.filter((s) => !inLineup.has(s.card_id));

  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4">
      <div className="grid grid-cols-3 gap-2">
        <Select value={season.formation} options={FORMATIONS} onChange={(f) => save.mutate({ formation: f, slots: {} })} />
        <Select value={mentality} options={MENTALITIES} onChange={setMentality} />
        <Select value={playstyle} options={PLAYSTYLES} onChange={setPlaystyle} />
      </div>
      <p className="text-[11px] text-ink-mist">
        Пустые места, травмированных и дисквалифицированных автоматически заменит лучший свежий игрок заявки.
        Усталость снижает рейтинг, форма ▲ после победы добавляет. Три жёлтые или красная — пропуск тура.
      </p>
      <div className="flex flex-col divide-y divide-white/5">
        {season.slots.map((slot) => (
          <SquadRow key={slot.code} label={slot.code} entry={byId.get(slots[slot.code])} onClick={() => setPicking(slot)} />
        ))}
      </div>
      {bench.length > 0 && (
        <div>
          <p className="mb-1 text-[11px] font-semibold text-ink-mist">Запас</p>
          <div className="flex flex-col divide-y divide-white/5">
            {bench.map((entry) => <SquadRow key={entry.card_id} label="—" entry={entry} />)}
          </div>
        </div>
      )}
      <button
        onClick={() => save.mutate({})}
        disabled={!dirty || save.isPending}
        className="rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
      >
        {save.isPending ? "Сохраняем..." : dirty ? "Сохранить состав" : "Состав сохранён"}
      </button>

      {picking && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60" onClick={() => setPicking(null)}>
          <div
            className="max-h-[75vh] w-full max-w-lg overflow-y-auto rounded-t-3xl bg-bg-surface p-4 pb-[calc(1rem+env(safe-area-inset-bottom))]"
            onClick={(e) => e.stopPropagation()}
          >
            <p className="mb-2 font-display text-base font-bold text-ink-chalk">Позиция {picking.code}</p>
            {season.squad
              .filter((s) => s.card && CATEGORY_POSITIONS[picking.category].includes(s.card.player.position))
              .map((entry) => (
                <SquadRow
                  key={entry.card_id}
                  label={slots[picking.code] === entry.card_id ? "✓" : ""}
                  entry={entry}
                  onClick={() => {
                    const next = { ...slots };
                    for (const [code, id] of Object.entries(next)) if (id === entry.card_id) delete next[code];
                    next[picking.code] = entry.card_id;
                    setSlots(next);
                    setPicking(null);
                  }}
                />
              ))}
          </div>
        </div>
      )}
    </section>
  );
}

function SquadRow({ label, entry, onClick }: { label: string; entry?: CareerSquadCard; onClick?: () => void }) {
  const card = entry?.card;
  return (
    <button onClick={onClick} disabled={!onClick} className="flex w-full items-center gap-3 py-2 text-left">
      <span className="w-10 shrink-0 font-mono text-[10px] text-ink-mist">{label}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm text-ink-chalk">
          {card ? card.player.display_name : entry ? "Карточка продана" : "Авто"}
        </span>
        {card && <span className="text-[10px] text-ink-mist">{card.player.position} · {card.player.rating}</span>}
      </span>
      {entry && entry.form !== 0 && entry.injured_rounds === 0 && entry.suspended_rounds === 0 && (
        <span
          className={`font-mono text-[10px] font-bold ${entry.form > 0 ? "text-accent-lime" : "text-red-400"}`}
          title="Форма на следующий матч"
        >
          {entry.form > 0 ? `▲+${entry.form}` : `▼${entry.form}`}
        </span>
      )}
      {entry && entry.yellows > 0 && entry.suspended_rounds === 0 && (
        <span className="flex items-center gap-0.5" title={`Жёлтых карточек: ${entry.yellows}`}>
          {Array.from({ length: entry.yellows }).map((_, i) => (
            <span key={i} className="h-3 w-2 rounded-[2px] bg-yellow-400" />
          ))}
        </span>
      )}
      {entry && entry.suspended_rounds > 0 ? (
        <span className="flex items-center gap-1 rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-semibold text-red-400">
          <span className="h-3 w-2 rounded-[2px] bg-red-500" /> дисквал. · {entry.suspended_rounds} т.
        </span>
      ) : entry && entry.injured_rounds > 0 ? (
        <span className="rounded-full bg-red-500/15 px-2 py-0.5 text-[10px] font-semibold text-red-400">
          травма · {entry.injured_rounds} т.
        </span>
      ) : entry ? (
        <FatigueBar value={entry.fatigue} />
      ) : null}
    </button>
  );
}

function Select({ value, options, onChange }: { value: string; options: { value: string; label: string }[]; onChange: (v: string) => void }) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="min-w-0 rounded-xl bg-bg-raised px-2 py-2 text-xs text-ink-chalk outline-none"
    >
      {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}
