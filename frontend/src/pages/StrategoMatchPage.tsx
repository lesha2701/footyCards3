import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchMyProfile } from "@/api/profile";
import {
  acceptStrategoChallenge,
  cancelStrategoChallenge,
  createStrategoBotMatch,
  createStrategoChallenge,
  declineStrategoChallenge,
  fetchStrategoMatch,
  forfeitStrategoMatch,
  setStrategoNote,
  startStrategoPuzzle,
  startStrategoTutorial,
  submitStrategoMove,
} from "@/api/stratego";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import { IconChevronLeft, IconCoin } from "@/components/icons";
import BattleOverlay from "@/components/stratego/BattleOverlay";
import RoleIcon from "@/components/stratego/RoleIcon";
import StrategoBoard, { PieceChip } from "@/components/stratego/StrategoBoard";
import { NOTE_LABELS, ROLE_META, WIN_REASON_LABELS, legalTargets } from "@/components/stratego/strategoMeta";
import VictoryOverlay from "@/components/stratego/VictoryOverlay";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify, openTelegramLink } from "@/lib/telegram";
import type { StrategoCombatPiece, StrategoMatch, StrategoMove, StrategoNoteTag, StrategoPiece } from "@/types";

const RESULT_TITLES: Record<string, string> = { win: "Победа!", draw: "Ничья", loss: "Поражение" };
const DIFFICULTY_LABELS: Record<string, string> = { easy: "Лёгкий бот", normal: "Бот", hard: "Сильный бот" };
const NOTE_ORDER: StrategoNoteTag[] = ["cup", "wall", "star", "speedster", "strong", "weak"];

export default function StrategoMatchPage() {
  const { matchId } = useParams();
  const id = Number(matchId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmForfeit, setConfirmForfeit] = useState(false);
  const [battle, setBattle] = useState<StrategoMove | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [noteFor, setNoteFor] = useState<StrategoPiece | null>(null);
  const [tipHidden, setTipHidden] = useState(false);
  const seenPly = useRef<number | null>(null);
  const seenStatus = useRef<string | null>(null);

  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: match, isLoading, isError } = useQuery({
    queryKey: ["stratego-match", id],
    queryFn: () => fetchStrategoMatch(id),
    // Polling while waiting on the other side also keeps the server's lazy
    // timeout sweep running (see stratego_service._sweep).
    refetchInterval: (q) => {
      const m = q.state.data as StrategoMatch | undefined;
      if (!m) return false;
      if (m.status === "pending_accept") return 5000;
      if (m.status !== "in_progress" || m.my_turn) return false;
      return m.live ? 2000 : 4000;
    },
  });

  // Duel animation + haptics for moves we haven't shown yet, and the end
  // screen when the match finishes while this page is open.
  useEffect(() => {
    if (!match) return;
    if (seenPly.current === null) {
      seenPly.current = match.ply;
      seenStatus.current = match.status;
      return;
    }
    if (match.ply > seenPly.current) {
      const fresh = match.history.filter((h) => h.ply > (seenPly.current ?? 0));
      const fight = [...fresh].reverse().find((h) => h.combat);
      if (fight?.combat) {
        setBattle(fight);
        const mineSurvived = fight.combat.survivor === "attacker" ? fight.combat.attacker.mine
          : fight.combat.survivor === "defender" ? fight.combat.defender.mine : false;
        hapticNotify(mineSurvived ? "success" : "error");
      } else if (fresh.some((h) => !h.mine)) {
        haptic("light");
      }
      seenPly.current = match.ply;
    }
    if (seenStatus.current === "in_progress" && match.status === "finished") {
      setShowResult(true);
      hapticNotify(match.result === "win" ? "success" : match.result === "loss" ? "error" : "warning");
    }
    seenStatus.current = match.status;
  }, [match]);

  const setMatch = (m: StrategoMatch) => {
    queryClient.setQueryData(["stratego-match", id], m);
    queryClient.invalidateQueries({ queryKey: ["stratego-matches"] });
    if (m.status === "finished") {
      queryClient.invalidateQueries({ queryKey: ["stratego-info"] });
      queryClient.invalidateQueries({ queryKey: ["stratego-stats"] });
      queryClient.invalidateQueries({ queryKey: ["stratego-puzzle"] });
    }
  };
  const move = useMutation({
    mutationFn: ({ from, to }: { from: [number, number]; to: [number, number] }) => submitStrategoMove(id, from, to),
    onSuccess: (m) => { setSelectedId(null); setError(null); haptic("light"); setMatch(m); },
    onError: (err) => { hapticNotify("error"); setError(formatGameError(err, "Ход не принят")); },
  });
  const action = useMutation({
    mutationFn: (kind: "accept" | "decline" | "cancel" | "forfeit") =>
      ({ accept: acceptStrategoChallenge, decline: declineStrategoChallenge, cancel: cancelStrategoChallenge, forfeit: forfeitStrategoMatch })[kind](id),
    onSuccess: (m) => { setError(null); setMatch(m); queryClient.invalidateQueries({ queryKey: ["game-limits"] }); },
    onError: (err) => setError(formatGameError(err, "Не получилось")),
  });
  const note = useMutation({
    mutationFn: ({ pieceId, tag }: { pieceId: number; tag: StrategoNoteTag | null }) => setStrategoNote(id, pieceId, tag),
    onSuccess: (m) => { setNoteFor(null); setMatch(m); },
    onError: (err) => setError(formatGameError(err, "Не удалось сохранить пометку")),
  });
  const rematch = useMutation({
    mutationFn: async (m: StrategoMatch) => {
      if (m.mode === "puzzle") return startStrategoPuzzle();
      if (m.mode === "tutorial") return startStrategoTutorial();
      if (m.opponent_type === "bot") return createStrategoBotMatch(m.difficulty === "easy" ? "easy" : "hard");
      return createStrategoChallenge(m.opponent_user_id!);
    },
    onSuccess: (m) => {
      setShowResult(false);
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      navigate(`/play/stratego/matches/${m.id}`, { replace: true });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось начать матч")),
  });
  const closeBattle = useCallback(() => setBattle(null), []);

  if (isLoading) return <LoadingScreen />;
  if (isError || !match) return <ErrorScreen message="Матч не найден" />;

  const size = match.board_size;
  const inPlay = match.status === "in_progress";
  const selected = match.pieces.find((p) => p.id === selectedId) ?? null;
  const blocked = match.blocked_move;
  const targets = selected && match.my_turn
    ? legalTargets(match.pieces, selected, size, match.lakes).filter(
      ([r, c]) => !(blocked && blocked[0][0] === selected.row && blocked[0][1] === selected.col && blocked[1][0] === r && blocked[1][1] === c),
    )
    : [];
  const last = match.history[match.history.length - 1];

  const onCell = (r: number, c: number) => {
    const piece = match.pieces.find((p) => p.row === r && p.col === c);
    if (inPlay && match.my_turn && !move.isPending && selected && targets.some(([tr, tc]) => tr === r && tc === c)) {
      move.mutate({ from: [selected.row, selected.col], to: [r, c] });
      return;
    }
    if (piece && !piece.mine && piece.hidden && inPlay) {
      setNoteFor(piece); // mark a suspected wall / cup / star
      return;
    }
    if (!inPlay || !match.my_turn) return;
    setSelectedId(piece?.mine && piece.role !== "cup" && piece.role !== "wall" ? piece.id : null);
    if (piece?.mine) haptic("light");
  };

  const share = () => {
    if (!profile?.telegram_bot_username) return;
    const url = `https://t.me/${profile.telegram_bot_username}`;
    const text = match.mode === "puzzle"
      ? "🏆 Решил «Задачу дня» в Футбольном Стратего! Попробуй и ты"
      : `🏆 Я выиграл в «Футбольном Стратего» у ${match.opponent_name}! Сыграем?`;
    openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(url)}&text=${encodeURIComponent(text)}`);
  };
  const canRematch = match.mode !== "normal" || match.opponent_type === "bot"
    || ((match.opponent_type === "friend" || match.opponent_type === "chat") && !!match.opponent_user_id);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/play/stratego")} className="rounded-full bg-white/5 p-2 text-ink-mist active:scale-95">
          <IconChevronLeft size={16} />
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-base font-bold text-ink-chalk">
            {match.mode === "puzzle" ? match.puzzle?.title ?? "Задача дня" : match.mode === "tutorial" ? "Обучение" : `vs ${match.opponent_name || "…"}`}
          </p>
          <p className="text-caption text-ink-mist">
            {match.mode === "puzzle"
              ? `Ход ${Math.min(match.puzzle?.moves ?? 0, Math.floor(match.ply / 2) + 1)} из ${match.puzzle?.moves ?? "—"}`
              : `Ход ${match.ply}/${match.move_limit}`}
            {match.opponent_type === "bot" && match.mode === "normal" && match.difficulty && ` · ${DIFFICULTY_LABELS[match.difficulty]}`}
            {match.live && " · онлайн"}
            {!match.live && match.deadline && inPlay && ` · до ${new Date(match.deadline).toLocaleString("ru-RU", { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" })}`}
          </p>
        </div>
        {match.live && inPlay && match.deadline && <LiveTimer deadline={match.deadline} mine={match.my_turn} />}
        {inPlay && match.mode === "normal" && (
          <button onClick={() => setConfirmForfeit(true)} className="rounded-full bg-white/5 px-3 py-1.5 text-xs text-red-400 active:scale-95">
            Сдаться
          </button>
        )}
      </div>

      {match.mode === "puzzle" && match.puzzle && inPlay && (
        <p className="rounded-xl bg-bg-surface px-3 py-2 text-xs text-ink-mist">
          {match.puzzle.description} Захвати Кубок за {match.puzzle.moves} хода.
        </p>
      )}

      {match.mode === "tutorial" && inPlay && !tipHidden && (
        <TutorialTip match={match} selected={!!selected} onHide={() => setTipHidden(true)} />
      )}

      {match.status === "pending_accept" && (
        <PendingPanel match={match} busy={action.isPending} onAction={(k) => action.mutate(k)} />
      )}

      {match.status === "finished" && <ResultPanel match={match} onOpen={() => setShowResult(true)} />}

      {["declined", "cancelled", "expired"].includes(match.status) && (
        <p className="rounded-xl bg-white/5 px-3 py-2 text-center text-sm text-ink-mist">
          {{ declined: "Вызов отклонён", cancelled: "Матч закрыт", expired: "Вызов истёк" }[match.status as "declined"]}
        </p>
      )}

      {inPlay && (
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
          lastMoveMine={last?.mine}
          lakes={match.lakes}
          notes={match.notes}
          onCellClick={onCell}
        />
      )}

      {selected?.role && (
        <p className="text-center text-caption text-ink-mist">
          <RoleIcon role={selected.role} size={12} className="mr-1 inline align-[-2px] text-accent-lime" />
          {ROLE_META[selected.role].label}
          {selected.card && `: ${selected.card.display_name} (${selected.card.position}, ${selected.power})`}
          {selected.card?.skill_name && ` · ${selected.card.skill_name} +${selected.card.skill_bonus} ${selected.card.skill_kind === "atk" ? "в атаке" : "в защите"}`}
          {" · "}{ROLE_META[selected.role].hint}
        </p>
      )}
      {inPlay && !selected && match.mode !== "puzzle" && (
        <p className="text-center text-micro text-ink-mist-dim">Нажми на фишку соперника, чтобы пометить её: «Стенка?», «Кубок?»…</p>
      )}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {last?.combat && <CombatBanner move={last} onReplay={() => setBattle(last)} />}

      {(match.lost_mine.length > 0 || match.lost_opponent.length > 0) && (
        <div className="grid grid-cols-2 gap-2">
          <Trophies title="Выбыли у тебя" pieces={match.lost_mine} />
          <Trophies title="Твои трофеи" pieces={match.lost_opponent} />
        </div>
      )}

      <BattleOverlay move={battle} onClose={closeBattle} />
      <VictoryOverlay
        match={showResult && !battle ? match : null}
        onClose={() => setShowResult(false)}
        onRematch={canRematch ? () => rematch.mutate(match) : undefined}
        rematchLabel={match.mode === "puzzle" ? "Ещё раз" : match.mode === "tutorial" ? "Ещё тренировка" : "Реванш"}
        onShare={profile?.telegram_bot_username && match.mode !== "tutorial" ? share : undefined}
      />

      {noteFor && (
        <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={() => setNoteFor(null)}>
          <div className="safe-bottom w-full rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="font-display text-base font-bold text-ink-chalk">Пометить фишку соперника</p>
            <p className="mb-3 text-caption text-ink-mist">
              Пометку видишь только ты.{noteFor.moved ? " Эта фишка уже ходила — значит, это не Кубок и не Стенка." : ""}
            </p>
            <div className="grid grid-cols-3 gap-2">
              {NOTE_ORDER.map((tag) => (
                <button
                  key={tag}
                  onClick={() => note.mutate({ pieceId: noteFor.id, tag })}
                  className={`rounded-xl py-2.5 text-xs font-semibold active:scale-95 ${
                    match.notes[String(noteFor.id)] === tag ? "bg-amber-300 text-bg-base" : "bg-white/5 text-ink-chalk"
                  }`}
                >
                  {NOTE_LABELS[tag]}
                </button>
              ))}
            </div>
            {match.notes[String(noteFor.id)] && (
              <button onClick={() => note.mutate({ pieceId: noteFor.id, tag: null })} className="mt-3 w-full py-2 text-xs text-ink-mist">
                Убрать пометку
              </button>
            )}
          </div>
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

function LiveTimer({ deadline, mine }: { deadline: string; mine: boolean }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, []);
  const left = Math.max(0, Math.ceil((new Date(deadline).getTime() - now) / 1000));
  const label = `${Math.floor(left / 60)}:${String(left % 60).padStart(2, "0")}`;
  return (
    <span className={`rounded-full px-2.5 py-1 font-mono text-xs font-bold ${
      mine && left <= 10 ? "animate-pulse bg-red-500/20 text-red-300" : mine ? "bg-accent-green/15 text-accent-green" : "bg-white/5 text-ink-mist"
    }`}
    >
      {label}
    </span>
  );
}

const TUTORIAL_TIPS = [
  "Нажми свою фишку — подсветятся клетки, куда она может пойти. Кубок и Стенки стоят на месте.",
  "Ходи на подсвеченную клетку. Красные фишки — соперник: кто есть кто, ты не знаешь, пока не вступишь в бой.",
  "Встань на фишку соперника — будет бой. Больший рейтинг побеждает, Стенка выбивает всех, кроме Подкатчика.",
  "Кубок никогда не ходит. Ищи фишки соперника, которые ни разу не двигались (без точки снизу) — Кубок среди них.",
  "Нажми на фишку соперника, чтобы пометить её: «Стенка?», «Кубок?». Так проще помнить, что ты уже выяснил.",
];

function TutorialTip({ match, selected, onHide }: { match: StrategoMatch; selected: boolean; onHide: () => void }) {
  const fought = match.history.some((h) => h.combat);
  const step = match.ply === 0 ? (selected ? 1 : 0) : !fought ? 2 : match.ply < 12 ? 3 : 4;
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-accent-lime/30 bg-accent-lime/10 p-3">
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-floodlight font-mono text-caption font-bold text-bg-base">
        {step + 1}
      </span>
      <p className="flex-1 text-xs leading-relaxed text-ink-chalk">{TUTORIAL_TIPS[step]}</p>
      <button onClick={onHide} className="text-caption text-ink-mist">Скрыть</button>
    </div>
  );
}

function pieceName(p: StrategoCombatPiece) {
  return `${ROLE_META[p.role].label}${p.card ? ` ${p.card.display_name} (${p.power})` : ""}`;
}

function CombatBanner({ move, onReplay }: { move: StrategoMove; onReplay: () => void }) {
  const c = move.combat!;
  const outcome = { attacker: `${pieceName(c.attacker)} побеждает`, defender: `${pieceName(c.defender)} устоял`, both: "Обе фишки выбыли" }[c.survivor];
  return (
    <button onClick={onReplay} className="rounded-xl bg-bg-surface px-3 py-2 text-left text-xs text-ink-mist active:scale-[0.99]">
      <p className="font-semibold text-ink-chalk">{move.mine ? "Твоя атака" : "Атака соперника"}{move.auto ? " (автоход)" : ""}</p>
      <p>{pieceName(c.attacker)} → {pieceName(c.defender)}</p>
      <p className="mt-0.5 text-ink-chalk">{outcome}</p>
    </button>
  );
}

function Trophies({ title, pieces }: { title: string; pieces: StrategoCombatPiece[] }) {
  return (
    <div className="rounded-xl bg-bg-surface p-2">
      <p className="mb-1.5 text-caption font-semibold text-ink-mist">{title} · {pieces.length}</p>
      {pieces.length === 0 ? <p className="text-caption text-ink-mist-dim">—</p> : (
        <div className="flex flex-wrap gap-1">
          {pieces.map((p) => (
            <span key={p.id} className="flex h-8 w-8 items-center justify-center" title={pieceName(p)}>
              <PieceChip piece={{ ...p, row: 0, col: 0, hidden: false, revealed: true, moved: true, power: p.power || null }} />
            </span>
          ))}
        </div>
      )}
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
      {match.stake_coins > 0 && <p className="text-caption text-ink-mist">Ставка: {match.stake_coins} монет с каждой стороны</p>}
      {incoming && <p className="text-caption text-ink-mist">Твои фишки встанут по сохранённой расстановке из «Подготовки».</p>}
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

function ResultPanel({ match, onOpen }: { match: StrategoMatch; onOpen: () => void }) {
  const tone = match.result === "win" ? "text-accent-green" : match.result === "loss" ? "text-red-400" : "text-ink-chalk";
  const title = match.mode === "puzzle"
    ? (match.result === "win" && match.win_reason === "cup_captured" ? "Задача решена!" : "Не вышло")
    : RESULT_TITLES[match.result ?? "draw"];
  return (
    <button onClick={onOpen} className="flex flex-col items-center gap-1 rounded-2xl bg-bg-surface p-4 text-center active:scale-[0.99]">
      <p className={`font-display text-2xl font-bold ${tone}`}>{title}</p>
      {match.win_reason && <p className="text-xs text-ink-mist">{WIN_REASON_LABELS[match.win_reason]}</p>}
      {match.my_strength !== null && match.mode === "normal" && (
        <p className="font-mono text-xs text-ink-mist">Сила фишек: {match.my_strength} — {match.opponent_strength}</p>
      )}
      <p className="mt-1 flex items-center gap-3 text-sm font-bold text-ink-chalk">
        <span className="flex items-center gap-1"><IconCoin size={14} /> +{match.reward_coins}</span>
        {match.mode === "normal" && match.opponent_type !== "friend" && (
          <span className={match.rating_delta >= 0 ? "text-accent-green" : "text-red-400"}>
            Рейтинг {match.rating_delta >= 0 ? "+" : ""}{match.rating_delta}
          </span>
        )}
      </p>
      {match.stake_coins > 0 && <p className="text-caption text-ink-mist-dim">Ставка: {match.stake_coins} с каждой стороны</p>}
      {match.my_player_xp > 0 && <p className="text-caption text-accent-lime">Мой игрок: +{match.my_player_xp} опыта</p>}
      <p className="text-caption text-ink-mist-dim">Все фишки соперника раскрыты · нажми, чтобы сыграть ещё</p>
    </button>
  );
}
