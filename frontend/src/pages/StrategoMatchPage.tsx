import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  acceptStrategoChallenge,
  cancelStrategoChallenge,
  declineStrategoChallenge,
  fetchStrategoMatch,
  forfeitStrategoMatch,
  submitStrategoMove,
} from "@/api/stratego";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import { IconChevronLeft, IconCoin } from "@/components/icons";
import StrategoBoard from "@/components/stratego/StrategoBoard";
import { ROLE_META, WIN_REASON_LABELS, legalTargets } from "@/components/stratego/strategoMeta";
import { formatGameError } from "@/lib/errors";
import type { StrategoCombatPiece, StrategoMatch, StrategoMove } from "@/types";

const RESULT_TITLES: Record<string, string> = { win: "Победа!", draw: "Ничья", loss: "Поражение" };

export default function StrategoMatchPage() {
  const { matchId } = useParams();
  const id = Number(matchId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmForfeit, setConfirmForfeit] = useState(false);

  const { data: match, isLoading, isError } = useQuery({
    queryKey: ["stratego-match", id],
    queryFn: () => fetchStrategoMatch(id),
    // Polling while waiting on the other side also keeps the server's lazy
    // timeout sweep running (see stratego_service._sweep).
    refetchInterval: (q) => {
      const m = q.state.data as StrategoMatch | undefined;
      if (!m) return false;
      if (m.status === "pending_accept") return 5000;
      return m.status === "in_progress" && !m.my_turn ? 4000 : false;
    },
  });

  const setMatch = (m: StrategoMatch) => {
    queryClient.setQueryData(["stratego-match", id], m);
    queryClient.invalidateQueries({ queryKey: ["stratego-matches"] });
    if (m.status === "finished") {
      queryClient.invalidateQueries({ queryKey: ["stratego-info"] });
      queryClient.invalidateQueries({ queryKey: ["stratego-stats"] });
    }
  };
  const move = useMutation({
    mutationFn: ({ from, to }: { from: [number, number]; to: [number, number] }) => submitStrategoMove(id, from, to),
    onSuccess: (m) => { setSelectedId(null); setError(null); setMatch(m); },
    onError: (err) => setError(formatGameError(err, "Ход не принят")),
  });
  const action = useMutation({
    mutationFn: (kind: "accept" | "decline" | "cancel" | "forfeit") =>
      ({ accept: acceptStrategoChallenge, decline: declineStrategoChallenge, cancel: cancelStrategoChallenge, forfeit: forfeitStrategoMatch })[kind](id),
    onSuccess: (m) => { setError(null); setMatch(m); queryClient.invalidateQueries({ queryKey: ["game-limits"] }); },
    onError: (err) => setError(formatGameError(err, "Не получилось")),
  });

  if (isLoading) return <LoadingScreen />;
  if (isError || !match) return <ErrorScreen message="Матч не найден" />;

  const size = match.board_size;
  const selected = match.pieces.find((p) => p.id === selectedId) ?? null;
  const targets = selected && match.my_turn ? legalTargets(match.pieces, selected, size) : [];
  const last = match.history[match.history.length - 1];

  const onCell = (r: number, c: number) => {
    if (!match.my_turn || move.isPending) return;
    const piece = match.pieces.find((p) => p.row === r && p.col === c);
    if (selected && targets.some(([tr, tc]) => tr === r && tc === c)) {
      move.mutate({ from: [selected.row, selected.col], to: [r, c] });
      return;
    }
    setSelectedId(piece?.mine && piece.role !== "cup" && piece.role !== "wall" ? piece.id : null);
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/play/stratego")} className="rounded-full bg-white/5 p-2 text-ink-mist active:scale-95">
          <IconChevronLeft size={16} />
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-base font-bold text-ink-chalk">vs {match.opponent_name || "…"}</p>
          <p className="text-[11px] text-ink-mist">
            Ход {match.ply}/{match.move_limit}
            {match.deadline && match.status === "in_progress" && ` · до ${new Date(match.deadline).toLocaleString("ru-RU", { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" })}`}
          </p>
        </div>
        {match.status === "in_progress" && (
          <button onClick={() => setConfirmForfeit(true)} className="rounded-full bg-white/5 px-3 py-1.5 text-xs text-red-400 active:scale-95">
            Сдаться
          </button>
        )}
      </div>

      {match.status === "pending_accept" && (
        <PendingPanel match={match} busy={action.isPending} onAction={(k) => action.mutate(k)} />
      )}

      {match.status === "finished" && <ResultPanel match={match} />}

      {["declined", "cancelled", "expired"].includes(match.status) && (
        <p className="rounded-xl bg-white/5 px-3 py-2 text-center text-sm text-ink-mist">
          {{ declined: "Вызов отклонён", cancelled: "Вызов отменён", expired: "Вызов истёк" }[match.status as "declined"]}
        </p>
      )}

      {match.status === "in_progress" && (
        <p className={`rounded-xl px-3 py-2 text-center text-sm font-semibold ${match.my_turn ? "bg-accent-green/15 text-accent-green" : "bg-white/5 text-ink-mist"}`}>
          {match.my_turn ? (selected ? "Выбери клетку" : "Твой ход — выбери фишку") : "Ход соперника…"}
          {match.my_auto_moves > 0 && ` · автоходов подряд: ${match.my_auto_moves}/${match.max_auto_moves}`}
        </p>
      )}

      {match.pieces.length > 0 && (
        <StrategoBoard
          size={size}
          pieces={match.pieces}
          selectedId={selectedId}
          targets={targets}
          lastMove={last ? { from: last.from_cell, to: last.to_cell } : null}
          onCellClick={onCell}
        />
      )}

      {selected?.card && (
        <p className="text-center text-[11px] text-ink-mist">
          {ROLE_META[selected.role!].glyph} {ROLE_META[selected.role!].label}: {selected.card.display_name} ({selected.card.position}, {selected.power})
          {" · "}{ROLE_META[selected.role!].hint}
        </p>
      )}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {last?.combat && <CombatBanner move={last} />}

      {(match.lost_mine.length > 0 || match.lost_opponent.length > 0) && (
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <LostList title="Выбыли у тебя" pieces={match.lost_mine} />
          <LostList title="Выбыли у соперника" pieces={match.lost_opponent} />
        </div>
      )}

      <ConfirmDialog
        open={confirmForfeit}
        title="Сдаться?"
        description="Матч засчитается как поражение без награды."
        danger
        confirmLabel="Сдаться"
        onConfirm={() => { setConfirmForfeit(false); action.mutate("forfeit"); }}
        onCancel={() => setConfirmForfeit(false)}
      />
    </div>
  );
}

function pieceName(p: StrategoCombatPiece) {
  return `${ROLE_META[p.role].glyph} ${ROLE_META[p.role].label}${p.card ? ` ${p.card.display_name} (${p.power})` : ""}`;
}

function CombatBanner({ move }: { move: StrategoMove }) {
  const c = move.combat!;
  const outcome = { attacker: `${pieceName(c.attacker)} побеждает`, defender: `${pieceName(c.defender)} устоял`, both: "Обе фишки выбыли" }[c.survivor];
  return (
    <div className="rounded-xl bg-bg-surface px-3 py-2 text-xs text-ink-mist">
      <p className="font-semibold text-ink-chalk">{move.mine ? "Твоя атака" : "Атака соперника"}{move.auto ? " (автоход)" : ""}</p>
      <p>{pieceName(c.attacker)} → {pieceName(c.defender)}</p>
      <p className="mt-0.5 text-ink-chalk">{outcome}</p>
    </div>
  );
}

function LostList({ title, pieces }: { title: string; pieces: StrategoCombatPiece[] }) {
  return (
    <div className="rounded-xl bg-bg-surface p-2">
      <p className="mb-1 font-semibold text-ink-mist">{title}</p>
      {pieces.length === 0 ? <p className="text-ink-mist-dim">—</p> : pieces.map((p) => (
        <p key={p.id} className="truncate text-ink-chalk">{pieceName(p)}</p>
      ))}
    </div>
  );
}

function PendingPanel({ match, busy, onAction }: { match: StrategoMatch; busy: boolean; onAction: (k: "accept" | "decline" | "cancel") => void }) {
  const incoming = match.viewer_side === "opponent";
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4 text-center">
      <p className="text-sm text-ink-chalk">
        {incoming
          ? `${match.opponent_name} вызывает тебя на Стратего`
          : match.opponent_type === "chat"
            ? "Открытый вызов отправлен в чат — ждём первого, кто его примет"
            : "Ждём, пока соперник примет вызов"}
      </p>
      {match.stake_coins > 0 && <p className="text-[11px] text-ink-mist">Ставка: {match.stake_coins} монет с каждой стороны</p>}
      {incoming && <p className="text-[11px] text-ink-mist">Твои фишки встанут по сохранённой расстановке из «Подготовки».</p>}
      <div className="flex gap-2">
        {incoming ? (
          <>
            <button disabled={busy} onClick={() => onAction("accept")} className="flex-1 rounded-xl bg-accent-green py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50">
              Принять
            </button>
            <button disabled={busy} onClick={() => onAction("decline")} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm text-ink-mist active:scale-95 disabled:opacity-50">
              Отклонить
            </button>
          </>
        ) : (
          <button disabled={busy} onClick={() => onAction("cancel")} className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm text-ink-mist active:scale-95 disabled:opacity-50">
            Отменить вызов
          </button>
        )}
      </div>
    </div>
  );
}

function ResultPanel({ match }: { match: StrategoMatch }) {
  const tone = match.result === "win" ? "text-accent-green" : match.result === "loss" ? "text-red-400" : "text-ink-chalk";
  return (
    <div className="flex flex-col items-center gap-1 rounded-2xl bg-bg-surface p-4 text-center">
      <p className={`font-display text-2xl font-bold ${tone}`}>{RESULT_TITLES[match.result ?? "draw"]}</p>
      {match.win_reason && <p className="text-xs text-ink-mist">{WIN_REASON_LABELS[match.win_reason]}</p>}
      {match.my_strength !== null && (
        <p className="font-mono text-xs text-ink-mist">Сила фишек: {match.my_strength} — {match.opponent_strength}</p>
      )}
      <p className="mt-1 flex items-center gap-3 text-sm font-bold text-ink-chalk">
        <span className="flex items-center gap-1"><IconCoin size={14} /> +{match.reward_coins}</span>
        {match.opponent_type !== "friend" && (
          <span className={match.rating_delta >= 0 ? "text-accent-green" : "text-red-400"}>
            Рейтинг {match.rating_delta >= 0 ? "+" : ""}{match.rating_delta}
          </span>
        )}
      </p>
      {match.stake_coins > 0 && <p className="text-[11px] text-ink-mist-dim">Ставка: {match.stake_coins} с каждой стороны</p>}
      <p className="text-[11px] text-ink-mist-dim">Все фишки соперника раскрыты</p>
    </div>
  );
}
