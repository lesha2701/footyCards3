import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  createMagnateBotMatch,
  createMagnateRoom,
  fetchMagnateMatch,
  joinMagnateLobby,
  leaveMagnateMatch,
  sendMagnateAction,
  startMagnateRoom,
} from "@/api/magnate";
import { fetchMyProfile } from "@/api/profile";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import { IconChevronLeft, IconClock, IconCoin, IconChat, IconTrophy } from "@/components/icons";
import MagnateBoard from "@/components/magnate/MagnateBoard";
import MagnateDice from "@/components/magnate/MagnateDice";
import {
  CELL_TYPE_LABELS,
  FINISH_REASON_LABELS,
  MODE_LABELS,
  SEAT_COLORS,
  formatMoney,
  levelLabel,
  secondsLeft,
} from "@/components/magnate/magnateMeta";
import { ApiRequestError } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify, openTelegramLink } from "@/lib/telegram";
import type { MagnateAction, MagnateCell, MagnateMatch, MagnatePlayer } from "@/types";

export default function MagnateMatchPage() {
  const { matchId } = useParams();
  const id = Number(matchId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const prevTurn = useRef<boolean | null>(null);
  const prevStatus = useRef<string | null>(null);

  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: match, isLoading, isError, dataUpdatedAt, refetch } = useQuery({
    queryKey: ["magnate-match", id],
    queryFn: () => fetchMagnateMatch(id),
    enabled: Number.isFinite(id),
    // Polling keeps the table in sync (no WebSocket in v1) and also drives
    // the server's lazy sweep of expired lobbies/turns.
    refetchInterval: (q) => {
      const m = q.state.data as MagnateMatch | undefined;
      if (!m || m.status === "finished" || m.status === "cancelled") return false;
      if (m.status === "lobby") return 2000;
      return m.my_turn ? 3000 : 1500;
    },
  });

  const live = match?.status === "in_progress" || match?.status === "lobby";
  useEffect(() => {
    if (!live) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [live]);

  useEffect(() => {
    if (!match) return;
    if (prevTurn.current === false && match.my_turn) haptic("medium");
    if (prevStatus.current === "in_progress" && match.status === "finished") {
      hapticNotify(match.my_place === 1 ? "success" : "warning");
    }
    prevTurn.current = match.my_turn;
    prevStatus.current = match.status;
  }, [match]);

  const setMatch = (m: MagnateMatch | null) => {
    queryClient.invalidateQueries({ queryKey: ["magnate-matches"] });
    queryClient.invalidateQueries({ queryKey: ["magnate-info"] });
    if (m) queryClient.setQueryData(["magnate-match", id], m);
  };
  const onError = (fallback: string) => (err: unknown) => {
    hapticNotify("error");
    setError(formatGameError(err, fallback));
    if (err instanceof ApiRequestError && err.status === 409) refetch();
  };

  const act = useMutation({
    mutationFn: ({ action, cell }: { action: MagnateAction; cell?: number }) =>
      sendMagnateAction(id, action, match!.version, cell),
    onSuccess: (m) => { setError(null); haptic("light"); setMatch(m); },
    onError: onError("Действие не принято"),
  });
  const leave = useMutation({
    mutationFn: () => leaveMagnateMatch(id),
    onSuccess: (m) => {
      setConfirmLeave(false);
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      setMatch(m);
      if (!m || m.status === "cancelled") navigate("/play/magnate", { replace: true });
    },
    onError: onError("Не получилось выйти"),
  });
  const startRoom = useMutation({
    mutationFn: () => startMagnateRoom(id),
    onSuccess: (m) => { setError(null); setMatch(m); },
    onError: onError("Не удалось начать"),
  });
  const again = useMutation({
    mutationFn: (mode: MagnateMatch["mode"]) =>
      ({ bot: createMagnateBotMatch, public: joinMagnateLobby, private: createMagnateRoom })[mode](),
    onSuccess: (m) => {
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      queryClient.setQueryData(["magnate-match", m.id], m);
      navigate(`/play/magnate/matches/${m.id}`, { replace: true });
    },
    onError: onError("Не удалось начать партию"),
  });

  if (isLoading) return <LoadingScreen />;
  if (isError || !match) return <ErrorScreen message="Партия не найдена" />;

  const busy = act.isPending;
  const me = match.players.find((p) => p.is_me);
  const fetchedAt = dataUpdatedAt || now;
  const turnLeft = secondsLeft(match.deadline, match.server_now, fetchedAt, now);
  const lobbyLeft = secondsLeft(match.lobby_deadline, match.server_now, fetchedAt, now);
  const current = match.turn !== null ? match.players[match.turn] : null;
  const inPlay = match.status === "in_progress";
  const selectedCell = selected !== null ? match.cells[selected] : null;
  const pendingCell = match.pending_cell !== null ? match.cells[match.pending_cell] : null;

  const share = () => {
    if (!profile?.telegram_bot_username || !match.invite_code) return;
    const link = `https://t.me/${profile.telegram_bot_username}?start=magnate_${match.invite_code}`;
    const text = "🏟 Садись за стол «Футбольного магната» — сыграем вчетвером!";
    openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`);
  };

  return (
    <div className="flex flex-col gap-3 pb-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/play/magnate")} className="rounded-full bg-white/5 p-2 text-ink-mist active:scale-95" aria-label="Назад">
          <IconChevronLeft size={16} />
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-base font-bold text-ink-chalk">Футбольный магнат</p>
          <p className="text-[11px] text-ink-mist">
            {MODE_LABELS[match.mode]}
            {inPlay && ` · круг ${match.round}/${match.max_rounds}`}
            {inPlay && match.ends_at && ` · до ${new Date(match.ends_at).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`}
          </p>
        </div>
        {(inPlay || match.status === "lobby") && me && !me.left && (
          <button onClick={() => setConfirmLeave(true)} className="rounded-full bg-white/5 px-3 py-1.5 text-xs text-red-400 active:scale-95">
            Выйти
          </button>
        )}
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {match.status === "lobby" || match.status === "cancelled" ? (
        <LobbyView
          match={match}
          secondsLeft={lobbyLeft}
          busy={startRoom.isPending}
          onShare={share}
          canShare={!!profile?.telegram_bot_username}
          onStart={() => startRoom.mutate()}
        />
      ) : (
        <>
          {match.status === "finished" && (
            <ResultPanel match={match} busy={again.isPending} onAgain={() => again.mutate(match.mode)} />
          )}

          <PlayersStrip players={match.players} turn={match.turn} />

          <MagnateBoard
            cells={match.cells}
            groups={match.groups}
            players={match.players}
            selected={selected}
            highlight={match.my_turn ? [...match.build_options, ...(match.pending_cell !== null ? [match.pending_cell] : [])] : []}
            onSelect={(i) => setSelected((s) => (s === i ? null : i))}
          >
            <MagnateDice dice={match.last_roll?.dice ?? null} rollN={match.last_roll?.n ?? null} />
            {inPlay && current && (
              <p className="text-center text-[11px] font-semibold" style={{ color: SEAT_COLORS[current.seat] }}>
                {match.my_turn ? "Твой ход" : `Ходит ${current.name}`}
                {turnLeft !== null && !current.is_bot && (
                  <span className={`ml-1 font-mono ${turnLeft <= 5 ? "text-red-400" : "text-ink-mist"}`}>· {turnLeft} с</span>
                )}
              </p>
            )}
            <div className="flex w-full flex-col gap-0.5">
              {match.log.slice(-3).map((e) => (
                <p key={e.n} className="truncate text-center text-[9px] leading-tight text-ink-mist">{e.text}</p>
              ))}
            </div>
          </MagnateBoard>

          {inPlay && match.my_turn && me && (
            <ActionPanel
              match={match}
              me={me}
              pendingCell={pendingCell}
              busy={busy}
              turnLeft={turnLeft}
              onAct={(action, cell) => act.mutate({ action, cell })}
            />
          )}

          {selectedCell && <CellInfo cell={selectedCell} match={match} onClose={() => setSelected(null)} />}

          <EventFeed match={match} />
        </>
      )}

      <ConfirmDialog
        open={confirmLeave}
        title={match.status === "lobby" ? "Выйти из лобби?" : "Покинуть партию?"}
        description={
          match.status === "lobby"
            ? match.mode === "private" && match.is_creator
              ? "Комната закроется для всех."
              : "Место освободится, попытка игры вернётся."
            : "Твоё место займёт бот, награды за партию не будет."
        }
        confirmLabel="Выйти"
        danger
        onConfirm={() => leave.mutate()}
        onCancel={() => setConfirmLeave(false)}
      />
    </div>
  );
}

function PlayersStrip({ players, turn }: { players: MagnatePlayer[]; turn: number | null }) {
  return (
    <div className="grid grid-cols-2 gap-1.5">
      {players.map((p) => (
        <div
          key={p.seat}
          className={`flex items-center gap-2 rounded-xl px-2.5 py-1.5 ${turn === p.seat ? "bg-white/10" : "bg-bg-surface"} ${p.bankrupt ? "opacity-50" : ""}`}
          style={turn === p.seat ? { boxShadow: `inset 0 0 0 1.5px ${SEAT_COLORS[p.seat]}` } : undefined}
        >
          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: SEAT_COLORS[p.seat] }} />
          <span className="min-w-0 flex-1">
            <span className={`block truncate text-[11px] font-semibold text-ink-chalk ${p.bankrupt ? "line-through" : ""}`}>
              {p.name}
              {p.is_me && <span className="text-accent-lime"> · ты</span>}
            </span>
            <span className="block font-mono text-[10px] text-ink-mist">
              {p.bankrupt ? "банкрот" : formatMoney(p.cash)}
              {p.in_jail && " · ⛔"}
              {p.left && " · бот"}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

function ActionPanel({
  match, me, pendingCell, busy, turnLeft, onAct,
}: {
  match: MagnateMatch;
  me: MagnatePlayer;
  pendingCell: MagnateCell | null;
  busy: boolean;
  turnLeft: number | null;
  onAct: (action: MagnateAction, cell?: number) => void;
}) {
  const primary = "flex-1 rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50";
  const secondary = "flex-1 rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist active:scale-95 disabled:opacity-50";
  const builds = match.build_options.map((i) => match.cells[i]);
  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-bg-surface p-3">
      <div className="flex items-center justify-between text-[11px] text-ink-mist">
        <span>У тебя {formatMoney(me.cash)}</span>
        {turnLeft !== null && (
          <span className={`flex items-center gap-1 font-mono ${turnLeft <= 5 ? "text-red-400" : ""}`}>
            <IconClock size={11} /> {turnLeft} с
          </span>
        )}
      </div>

      {match.phase === "buy" && pendingCell && (
        <>
          <p className="text-sm text-ink-chalk">
            <span className="font-semibold">«{pendingCell.name}»</span> свободен —{" "}
            {pendingCell.type === "stadium" ? "стадион" : `клуб, группа «${match.groups[pendingCell.group ?? 0]?.name}»`}.
            {pendingCell.rent && <span className="text-ink-mist"> Аренда от {pendingCell.rent[0]} М.</span>}
          </p>
          <div className="flex gap-2">
            <button disabled={busy} onClick={() => onAct("skip")} className={secondary}>Не покупать</button>
            <button disabled={busy} onClick={() => onAct("buy")} className={primary}>
              Купить за {formatMoney(pendingCell.price ?? 0)}
            </button>
          </div>
        </>
      )}

      {match.phase === "roll" && (
        me.in_jail ? (
          <>
            <p className="text-xs text-ink-mist">Ты дисквалифицирован: выбей дубль, заплати штраф или используй апелляцию.</p>
            <div className="flex flex-wrap gap-2">
              <button disabled={busy} onClick={() => onAct("roll")} className={primary}>Бросить (нужен дубль)</button>
              {match.can_pay_bail && (
                <button disabled={busy} onClick={() => onAct("pay_bail")} className={secondary}>Штраф {match.jail_fine} М</button>
              )}
              {match.can_use_card && (
                <button disabled={busy} onClick={() => onAct("use_card")} className={secondary}>Апелляция</button>
              )}
            </div>
          </>
        ) : (
          <button disabled={busy} onClick={() => onAct("roll")} className={`${primary} py-4 text-base`}>
            🎲 Бросить кубики
          </button>
        )
      )}

      {builds.length > 0 && (match.phase === "roll" || match.phase === "end") && (
        <div className="flex flex-col gap-1.5">
          <p className="text-[11px] text-ink-mist">Можно строить — у тебя вся группа:</p>
          {builds.map((c) => (
            <button
              key={c.index}
              disabled={busy}
              onClick={() => onAct("build", c.index)}
              className="flex items-center justify-between rounded-xl bg-white/5 px-3 py-2 text-left text-xs active:scale-[0.98] disabled:opacity-50"
            >
              <span className="text-ink-chalk">
                {c.name} · {c.level >= 3 ? "Арена" : `Трибуна №${c.level + 1}`}
                {c.rent && <span className="text-ink-mist"> → аренда {c.rent[Math.min(c.level + 1, 4)]} М</span>}
              </span>
              <span className="font-mono text-accent-lime">{formatMoney(c.build_cost ?? 0)}</span>
            </button>
          ))}
        </div>
      )}

      {match.phase === "end" && (
        <button disabled={busy} onClick={() => onAct("end")} className={primary}>Завершить ход</button>
      )}
    </div>
  );
}

function CellInfo({ cell, match, onClose }: { cell: MagnateCell; match: MagnateMatch; onClose: () => void }) {
  const owner = cell.owner_seat !== null ? match.players[cell.owner_seat] : null;
  const group = cell.group !== null ? match.groups[cell.group] : null;
  const rentRows = cell.rent
    ? [["База (вся группа — ×2)", cell.rent[0]], ["Трибуны ×1", cell.rent[1]], ["Трибуны ×2", cell.rent[2]], ["Трибуны ×3", cell.rent[3]], ["Арена", cell.rent[4]]]
    : [];
  return (
    <div className="rounded-2xl bg-bg-surface p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          {group && <span className="mb-1 block h-1 w-10 rounded-full" style={{ background: group.color }} />}
          <p className="font-display text-sm font-bold text-ink-chalk">{cell.name}</p>
          <p className="text-[11px] text-ink-mist">
            {cell.type === "club" && group ? `Клуб · ${group.name}` : CELL_TYPE_LABELS[cell.type]}
            {cell.price !== null && ` · цена ${formatMoney(cell.price)}`}
          </p>
        </div>
        <button onClick={onClose} className="rounded-full bg-white/5 px-2.5 py-1 text-[11px] text-ink-mist">Закрыть</button>
      </div>
      {cell.price !== null && (
        <p className="mt-2 text-xs text-ink-chalk">
          {owner ? (
            <>
              Владелец: <span style={{ color: SEAT_COLORS[owner.seat] }}>{owner.name}</span>
              {cell.level > 0 && ` · ${levelLabel(cell.level)}`} · аренда сейчас {formatMoney(cell.current_rent)}
            </>
          ) : (
            "Свободен"
          )}
        </p>
      )}
      {rentRows.length > 0 && (
        <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[11px]">
          {rentRows.map(([label, value]) => (
            <div key={label} className="contents">
              <span className="text-ink-mist">{label}</span>
              <span className="text-right font-mono text-ink-chalk">{value} М</span>
            </div>
          ))}
          <span className="text-ink-mist">Постройка</span>
          <span className="text-right font-mono text-ink-chalk">{cell.build_cost} М</span>
        </div>
      )}
      {cell.type === "stadium" && (
        <p className="mt-2 text-[11px] text-ink-mist">Аренда растёт с числом стадионов у владельца.</p>
      )}
    </div>
  );
}

function EventFeed({ match }: { match: MagnateMatch }) {
  const [open, setOpen] = useState(false);
  const entries = [...match.log].reverse().slice(0, open ? 30 : 6);
  return (
    <div className="rounded-2xl bg-bg-surface p-3">
      <button onClick={() => setOpen((o) => !o)} className="mb-1.5 flex w-full items-center justify-between text-left">
        <span className="font-display text-sm font-bold text-ink-chalk">Лента событий</span>
        <span className="text-[11px] text-ink-mist">{open ? "Свернуть" : "Ещё"}</span>
      </button>
      <div className="flex flex-col gap-1">
        {entries.map((e) => (
          <p key={e.n} className="flex gap-2 text-[11px] leading-snug text-ink-mist">
            <span
              className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full"
              style={{ background: e.seat !== null ? SEAT_COLORS[e.seat] : "rgba(255,255,255,0.3)" }}
            />
            <span className={e.kind === "finish" || e.kind === "bankrupt" ? "font-semibold text-ink-chalk" : ""}>{e.text}</span>
          </p>
        ))}
      </div>
    </div>
  );
}

function ResultPanel({ match, busy, onAgain }: { match: MagnateMatch; busy: boolean; onAgain: () => void }) {
  const navigate = useNavigate();
  const ranked = [...match.players].sort((a, b) => (a.place ?? 9) - (b.place ?? 9));
  const me = match.players.find((p) => p.is_me);
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-accent-lime/25 bg-gradient-to-b from-accent-lime/10 to-transparent p-4">
      <div className="text-center">
        <IconTrophy size={28} className="mx-auto text-accent-lime" />
        <p className="mt-1 font-display text-lg font-bold text-ink-chalk">
          {me?.left ? "Ты покинул партию" : match.my_place === 1 ? "Ты — магнат!" : `${match.my_place ?? "—"}-е место`}
        </p>
        <p className="text-[11px] text-ink-mist">{FINISH_REASON_LABELS[match.finish_reason ?? ""] ?? "Партия завершена"}</p>
        {match.my_reward > 0 && (
          <p className="mt-1 flex items-center justify-center gap-1 font-mono text-sm font-bold text-accent-lime">
            +{match.my_reward} <IconCoin size={13} />
          </p>
        )}
      </div>
      <div className="flex flex-col gap-1">
        {ranked.map((p) => (
          <div key={p.seat} className={`flex items-center gap-2 rounded-xl px-3 py-1.5 ${p.is_me ? "bg-white/10" : "bg-white/5"}`}>
            <span className="w-5 font-display text-sm font-bold text-ink-chalk">{p.place}</span>
            <span className="h-2 w-2 rounded-full" style={{ background: SEAT_COLORS[p.seat] }} />
            <span className="min-w-0 flex-1 truncate text-xs text-ink-chalk">
              {p.name}
              {p.bankrupt && <span className="text-ink-mist"> · банкрот</span>}
              {p.left && <span className="text-ink-mist"> · ушёл</span>}
            </span>
            <span className="font-mono text-[11px] text-ink-mist">{formatMoney(p.capital)}</span>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <button onClick={() => navigate("/play/magnate")} className="flex-1 rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist active:scale-95">
          К играм
        </button>
        <button onClick={onAgain} disabled={busy} className="flex-1 rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50">
          Ещё партию
        </button>
      </div>
    </div>
  );
}

function LobbyView({
  match, secondsLeft: left, busy, canShare, onShare, onStart,
}: {
  match: MagnateMatch;
  secondsLeft: number | null;
  busy: boolean;
  canShare: boolean;
  onShare: () => void;
  onStart: () => void;
}) {
  const navigate = useNavigate();
  if (match.status === "cancelled") {
    return (
      <div className="flex flex-col items-center gap-3 rounded-2xl bg-bg-surface p-6 text-center">
        <p className="font-display text-base font-bold text-ink-chalk">Стол закрыт</p>
        <p className="text-xs text-ink-mist">Партия не началась — попытка игры возвращена.</p>
        <button onClick={() => navigate("/play/magnate")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
          К играм
        </button>
      </div>
    );
  }
  const seats = Array.from({ length: match.seats_total }, (_, i) => match.players.find((p) => p.seat === i));
  const minutes = left !== null ? Math.floor(left / 60) : null;
  return (
    <div className="flex flex-col gap-3">
      <div className="rounded-2xl bg-bg-surface p-4 text-center">
        <p className="font-display text-base font-bold text-ink-chalk">
          {match.mode === "private" ? "Комната для друзей" : "Собираем стол"}
        </p>
        <p className="mt-1 text-xs text-ink-mist">
          {match.mode === "private"
            ? left !== null
              ? `Начни, когда соберётесь. Комната ждёт ещё ${minutes} мин ${left % 60} с — потом свободные места займут боты (или комната закроется, если ты один).`
              : "Начни, когда соберётесь."
            : left !== null
              ? `Свободные места займут боты через ${left} с`
              : "Ждём игроков…"}
        </p>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {seats.map((p, i) => (
          <div key={i} className="flex items-center gap-2 rounded-2xl bg-bg-surface px-3 py-3">
            <span className="h-3 w-3 shrink-0 rounded-full" style={{ background: p ? SEAT_COLORS[i] : "rgba(255,255,255,0.15)" }} />
            <span className={`truncate text-xs ${p ? "font-semibold text-ink-chalk" : "text-ink-mist-dim"}`}>
              {p ? `${p.name}${p.is_me ? " (ты)" : ""}` : "свободно"}
            </span>
          </div>
        ))}
      </div>
      {match.mode === "private" && match.invite_code && (
        <button
          onClick={onShare}
          disabled={!canShare}
          className="flex items-center justify-center gap-2 rounded-2xl bg-accent-cyan/15 py-3 text-sm font-bold text-accent-cyan active:scale-95 disabled:opacity-50"
        >
          <IconChat size={16} /> Пригласить друзей · код {match.invite_code}
        </button>
      )}
      {match.mode === "private" && match.is_creator && (
        <button onClick={onStart} disabled={busy} className="rounded-2xl bg-floodlight py-3.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50">
          Начать — свободные места займут боты
        </button>
      )}
    </div>
  );
}
