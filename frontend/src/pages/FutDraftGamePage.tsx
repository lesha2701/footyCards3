import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  chooseFutDraftFormation,
  claimFutDraftReward,
  fetchFutDraftConfig,
  fetchFutDraftLeaderboard,
  openFutDraftSlot,
  startFutDraft,
  startFutDraftMatch,
  submitFutDraftCardArenaAction,
  submitFutDraftPenaltyKick,
  submitFutDraftPick,
  submitFutDraftTacticoPhase,
} from "@/api/games";
import {
  IconBall,
  IconBoot,
  IconClose,
  IconCoin,
  IconFlagCheckered,
  IconGloves,
  IconGoal,
  IconHelp,
  IconPlus,
  IconShirt,
  IconSwap,
  IconTrophy,
  IconUsers,
  type IconProps,
} from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_TEXT } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type {
  FutDraftCandidate,
  FutDraftClaim,
  FutDraftGameType,
  FutDraftRound,
  FutDraftSlot,
  MatchActionKind,
  MatchPendingMoment,
} from "@/types";

type Phase = "idle" | "choose_formation" | "drafting" | "ready" | "match" | "finished";

const EVENT_STEP_MS = 900;
const RESULT_LABELS: Record<string, string> = { win: "Победа", draw: "Ничья", loss: "Поражение" };
const STRENGTH_HINT =
  "Сила состава = рейтинг игрока × соответствие позиции (сильнее всего на своей родной позиции) × бонус за редкость, " +
  "плюс бонус, если в составе несколько игроков одного клуба или одной страны.";

const GAME_TYPE_META: Record<FutDraftGameType, { label: string; Icon: (p: IconProps) => JSX.Element }> = {
  card_arena: { label: "Card Arena", Icon: IconBall },
  tactico: { label: "Тактико", Icon: IconFlagCheckered },
  penalty: { label: "Пенальти", Icon: IconGoal },
};

const ACTION_LABELS: Record<MatchActionKind, { label: string; Icon: (props: IconProps) => JSX.Element }> = {
  shoot: { label: "Ударить", Icon: IconBoot },
  pass: { label: "Отдать пас", Icon: IconSwap },
  tackle: { label: "Сделать подкат", Icon: IconUsers },
  block: { label: "Заблокировать удар", Icon: IconGoal },
  keeper: { label: "Довериться вратарю", Icon: IconGloves },
  strike: { label: "Ударить!", Icon: IconBoot },
};

export default function FutDraftGamePage() {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [phase, setPhase] = useState<Phase>("idle");
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [formationOptions, setFormationOptions] = useState<string[]>([]);
  const [formation, setFormation] = useState<string>("");
  const [slots, setSlots] = useState<FutDraftSlot[]>([]);
  const [pendingSlot, setPendingSlot] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<FutDraftCandidate[]>([]);
  const [teamStrength, setTeamStrength] = useState(0);
  const [strengthDelta, setStrengthDelta] = useState<number | null>(null);
  const [showStrengthHint, setShowStrengthHint] = useState(false);
  const [chemistryHints, setChemistryHints] = useState<string[]>([]);
  const [viewingPlayer, setViewingPlayer] = useState<FutDraftCandidate | null>(null);
  const [matchHistory, setMatchHistory] = useState<FutDraftRound[]>([]);
  const [currentRound, setCurrentRound] = useState<FutDraftRound | null>(null);
  const [claimResult, setClaimResult] = useState<FutDraftClaim | null>(null);
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: config } = useQuery({ queryKey: ["fut-draft-config"], queryFn: fetchFutDraftConfig });
  const { data: leaderboard } = useQuery({ queryKey: ["fut-draft-leaderboard"], queryFn: fetchFutDraftLeaderboard });

  useEffect(() => {
    if (strengthDelta === null) return;
    const t = setTimeout(() => setStrengthDelta(null), 1600);
    return () => clearTimeout(t);
  }, [strengthDelta]);

  const resetForNewDraft = () => {
    setSessionId(null);
    setFormationOptions([]);
    setFormation("");
    setSlots([]);
    setPendingSlot(null);
    setCandidates([]);
    setTeamStrength(0);
    setStrengthDelta(null);
    setChemistryHints([]);
    setViewingPlayer(null);
    setMatchHistory([]);
    setCurrentRound(null);
    setClaimResult(null);
    setErrorMsg(null);
  };

  const start = async () => {
    setBusy(true);
    setErrorMsg(null);
    try {
      const data = await startFutDraft();
      updateBalance(data.new_balance);
      resetForNewDraft();
      setSessionId(data.session_id);
      setFormationOptions(data.formation_options);
      setPhase("choose_formation");
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось начать драфт"));
    } finally {
      setBusy(false);
    }
  };

  const chooseFormation = async (code: string) => {
    if (busy || sessionId === null) return;
    setBusy(true);
    haptic("light");
    try {
      const state = await chooseFutDraftFormation(sessionId, code);
      setFormation(state.formation);
      setSlots(state.slots);
      setTeamStrength(state.team_strength);
      setChemistryHints(state.chemistry_hints);
      setPhase("drafting");
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось выбрать схему"));
    } finally {
      setBusy(false);
    }
  };

  const openSlot = async (slotCode: string) => {
    if (busy || sessionId === null || pendingSlot !== null) return;
    setBusy(true);
    haptic("light");
    try {
      const state = await openFutDraftSlot(sessionId, slotCode);
      setPendingSlot(state.pending_slot);
      setCandidates(state.candidates ?? []);
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось открыть позицию"));
    } finally {
      setBusy(false);
    }
  };

  const pick = async (playerId: number) => {
    if (busy || sessionId === null) return;
    setBusy(true);
    haptic("medium");
    try {
      const state = await submitFutDraftPick(sessionId, playerId);
      setSlots(state.slots);
      setPendingSlot(state.pending_slot);
      setCandidates(state.candidates ?? []);
      setTeamStrength(state.team_strength);
      setStrengthDelta(state.last_pick_strength_delta ?? null);
      setChemistryHints(state.chemistry_hints);
      if (state.phase === "ready") {
        hapticNotify("success");
        setPhase("ready");
      }
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось выбрать карту"));
    } finally {
      setBusy(false);
    }
  };

  const claim = async (id: number) => {
    try {
      const data = await claimFutDraftReward(id);
      updateBalance(data.new_balance);
      hapticNotify("success");
      setClaimResult(data);
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось начислить награду"));
    }
  };

  const playMatch = async () => {
    if (busy || sessionId === null) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const result = await startFutDraftMatch(sessionId);
      setCurrentRound(result);
      setPhase("match");
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось сыграть матч"));
    } finally {
      setBusy(false);
    }
  };

  const handleRoundFinished = (round: FutDraftRound) => {
    setMatchHistory((prev) => [...prev, round]);
    setCurrentRound(null);
    if (round.is_finished) {
      hapticNotify(round.wins === 4 ? "success" : "warning");
      setPhase("finished");
      claim(round.session_id);
    } else {
      setPhase("ready");
    }
  };

  const handleRoundStep = (round: FutDraftRound) => {
    if (round.round_in_progress) {
      setCurrentRound(round);
    } else {
      handleRoundFinished(round);
    }
  };

  const playCardArenaAction = async (action: MatchActionKind) => {
    if (busy || sessionId === null) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const round = await submitFutDraftCardArenaAction(sessionId, action);
      handleRoundStep(round);
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось выполнить действие"));
    } finally {
      setBusy(false);
    }
  };

  const playTacticoPhase = async (choice: string) => {
    if (busy || sessionId === null) return;
    setBusy(true);
    setErrorMsg(null);
    haptic("medium");
    try {
      const round = await submitFutDraftTacticoPhase(sessionId, choice);
      handleRoundStep(round);
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось сыграть эпизод"));
    } finally {
      setBusy(false);
    }
  };

  const playPenaltyKick = async (direction: string) => {
    if (busy || sessionId === null) return;
    setBusy(true);
    setErrorMsg(null);
    haptic("medium");
    try {
      const round = await submitFutDraftPenaltyKick(sessionId, direction);
      handleRoundStep(round);
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось пробить пенальти"));
    } finally {
      setBusy(false);
    }
  };

  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-xl font-bold text-ink-chalk">FUT Draft</h1>
        <p className="text-sm text-ink-mist">
          Собери временный состав из случайных карт всей игры — даже тех, которых нет в твоей коллекции. Выбери
          схему, задрафти 11 игроков (сам решай, с какой позиции начать) и сыграй до 4 матчей на вылет. Чем дальше
          пройдёшь — тем больше награда.
        </p>

        <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface px-4 py-3">
          <div className="flex items-center justify-between">
            <span className="text-sm text-ink-mist">Стоимость входа</span>
            <span className="flex items-center gap-1 font-mono text-base font-bold text-accent-lime">
              {config?.entry_cost ?? "..."}
              <IconCoin size={14} />
            </span>
          </div>
          {config && (
            <div className="mt-1 flex flex-col gap-1 border-t border-white/5 pt-2">
              <p className="text-[11px] text-ink-mist-dim">Награда за серию побед</p>
              <div className="flex justify-between gap-1">
                {config.reward_by_wins.map((amount, wins) => (
                  <div key={wins} className="flex flex-1 flex-col items-center gap-0.5 rounded-lg bg-white/5 py-1.5">
                    <span className="text-[9px] text-ink-mist-dim">{wins} поб.</span>
                    <span className="font-mono text-xs font-bold text-accent-lime">{amount}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <button
          onClick={start}
          disabled={busy}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {busy ? "Загрузка..." : "Начать драфт"}
        </button>

        {!!leaderboard?.length && (
          <div className="rounded-2xl bg-bg-surface p-4">
            <p className="mb-2 flex items-center gap-1.5 font-display text-sm font-bold text-ink-chalk">
              <IconTrophy size={14} className="text-accent-lime" />
              Лучшие составы
            </p>
            <div className="flex flex-col gap-2">
              {leaderboard.slice(0, 5).map((entry, i) => (
                <div key={entry.user_id} className="flex items-center justify-between text-sm">
                  <span className="text-ink-mist">{i + 1}. {entry.display_name}</span>
                  <span className="font-mono font-bold text-accent-cyan">{entry.best_squad_strength}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (phase === "choose_formation") {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Выбери схему</h1>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <div className="flex flex-col gap-3">
          {formationOptions.map((code) => (
            <button
              key={code}
              onClick={() => chooseFormation(code)}
              disabled={busy}
              className="rounded-2xl bg-bg-surface py-4 font-display text-lg font-bold text-ink-chalk active:scale-95 disabled:opacity-50"
            >
              {code}
            </button>
          ))}
        </div>
      </div>
    );
  }

  if (phase === "drafting" || phase === "ready") {
    return (
      <div className="flex flex-col gap-4">
        <StrengthBar
          teamStrength={teamStrength}
          delta={strengthDelta}
          showHint={showStrengthHint}
          onToggleHint={() => setShowStrengthHint((v) => !v)}
        />

        <Pitch
          formation={formation}
          slots={slots}
          onSlotClick={openSlot}
          onPlayerClick={(player) => setViewingPlayer(player)}
          disabled={busy || pendingSlot !== null}
        />

        {chemistryHints.length > 0 && (
          <div className="flex flex-col gap-1.5 rounded-2xl bg-accent-green/10 px-4 py-3">
            {chemistryHints.map((hint, i) => (
              <p key={i} className="text-xs font-semibold text-accent-green">✓ {hint}</p>
            ))}
          </div>
        )}

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}

        {pendingSlot && (
          <div className="flex flex-col gap-3">
            <p className="text-xs font-semibold text-ink-mist-dim">Выбери игрока на эту позицию</p>
            {candidates.map((card) => (
              <DraftCandidateCard key={card.id} card={card} disabled={busy} onClick={() => pick(card.id)} />
            ))}
          </div>
        )}

        {phase === "ready" && !pendingSlot && (
          <>
            {matchHistory.length > 0 && (
              <div className="flex flex-col gap-2">
                {matchHistory.map((r, i) => (
                  <div key={i} className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2 text-sm">
                    <span className="flex items-center gap-1.5 text-ink-mist">
                      {(() => {
                        const Icon = GAME_TYPE_META[r.game_type].Icon;
                        return <Icon size={12} />;
                      })()}
                      Матч {i + 1} · {GAME_TYPE_META[r.game_type].label} ({r.result ? RESULT_LABELS[r.result] : ""})
                    </span>
                    <span className="font-mono font-bold text-ink-chalk">{r.user_score}:{r.bot_score}</span>
                  </div>
                ))}
              </div>
            )}
            <button
              onClick={playMatch}
              disabled={busy}
              className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
            >
              {busy ? "Загрузка..." : `Играть матч ${matchHistory.length + 1}/4`}
            </button>
          </>
        )}

        {viewingPlayer && <PlayerDetailModal card={viewingPlayer} onClose={() => setViewingPlayer(null)} />}
      </div>
    );
  }

  if (phase === "match" && currentRound) {
    if (currentRound.game_type === "tactico") {
      return <TacticoRoundPlayer round={currentRound} busy={busy} errorMsg={errorMsg} onChoose={playTacticoPhase} />;
    }
    if (currentRound.game_type === "penalty") {
      return <PenaltyRoundPlayer round={currentRound} busy={busy} errorMsg={errorMsg} onKick={playPenaltyKick} />;
    }
    return (
      <CardArenaRoundPlayer
        round={currentRound}
        busy={busy}
        onAct={playCardArenaAction}
        onFinished={handleRoundFinished}
      />
    );
  }

  const wins = matchHistory.filter((r) => r.result === "win").length;
  return (
    <div className="flex flex-col items-center gap-5 py-6 text-center">
      <IconTrophy size={40} className={wins === 4 ? "text-accent-lime" : "text-ink-mist-dim"} />
      <p className="font-display text-2xl font-bold text-ink-chalk">
        {wins === 4 ? "Идеальный драфт!" : `Драфт окончен — ${wins}/4 побед`}
      </p>

      {!claimResult && !errorMsg ? (
        <p className="text-sm text-ink-mist">Начисление...</p>
      ) : claimResult ? (
        <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
          <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
            Ты получил +{claimResult.reward_coins}
            <IconCoin size={16} />
          </p>
          <p className="text-xs text-accent-green">Сила состава: {claimResult.team_strength}</p>
          {claimResult.is_new_best && <p className="mt-1 text-xs font-bold text-accent-lime">Новый личный рекорд!</p>}
        </div>
      ) : (
        <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>
      )}

      <div className="flex gap-3">
        <button onClick={() => { resetForNewDraft(); setPhase("idle"); }} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
          Ещё раз
        </button>
        <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
          Назад
        </button>
      </div>
    </div>
  );
}

function StrengthBar({
  teamStrength,
  delta,
  showHint,
  onToggleHint,
}: {
  teamStrength: number;
  delta: number | null;
  showHint: boolean;
  onToggleHint: () => void;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface px-4 py-3">
      <div className="flex items-center justify-between">
        <button onClick={onToggleHint} className="flex items-center gap-1.5 text-ink-mist-dim">
          <span className="font-mono text-[10px] uppercase tracking-wide">Сила состава</span>
          <IconHelp size={12} />
        </button>
        <div className="flex items-center gap-2">
          {delta !== null && delta > 0 && (
            <span className="font-mono text-xs font-bold text-accent-green">+{delta}</span>
          )}
          <span className="font-display text-lg font-bold text-accent-lime">{teamStrength}</span>
        </div>
      </div>
      {showHint && <p className="text-[11px] leading-relaxed text-ink-mist">{STRENGTH_HINT}</p>}
    </div>
  );
}

function Pitch({
  formation,
  slots,
  onSlotClick,
  onPlayerClick,
  disabled,
}: {
  formation: string;
  slots: FutDraftSlot[];
  onSlotClick: (slotCode: string) => void;
  onPlayerClick: (player: FutDraftCandidate) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-gradient-to-b from-emerald-950/60 to-emerald-900/30 p-3">
      <p className="text-center font-mono text-[10px] uppercase tracking-wide text-ink-mist-dim">{formation}</p>
      {(["FWD", "MID", "DEF", "GK"] as const).map((category) => (
        <div key={category} className="flex justify-center gap-2">
          {slots
            .filter((s) => s.category === category)
            .map((slot) => (
              <button
                key={slot.slot_code}
                onClick={() => (slot.player ? onPlayerClick(slot.player) : onSlotClick(slot.slot_code))}
                disabled={slot.player ? false : disabled}
                className={`flex h-[104px] w-[72px] shrink-0 flex-col items-center justify-center gap-1 rounded-xl p-1.5 backdrop-blur-sm active:scale-95 disabled:active:scale-100 ${
                  slot.player ? `bg-gradient-to-b ${RARITY_GRADIENTS[slot.player.rarity]} ${RARITY_GLOW[slot.player.rarity]} p-[1.5px]` : "bg-black/30"
                }`}
              >
                {slot.player ? (
                  <div className="flex h-full w-full flex-col items-center justify-center gap-1 rounded-[9px] bg-bg-surface p-1">
                    <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                      {slot.player.image_path ? (
                        <img src={staticUrl(slot.player.image_path) ?? undefined} alt="" className="h-full w-full object-cover" loading="lazy" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <IconShirt size={16} className="text-ink-mist-dim" />
                        </div>
                      )}
                    </div>
                    <span className="font-mono text-[9px] font-bold leading-none text-ink-chalk">{slot.player.rating}</span>
                    <span className="rounded-full bg-black/40 px-1.5 py-0.5 font-mono text-[8px] font-bold leading-none text-accent-cyan">{slot.player.position}</span>
                  </div>
                ) : (
                  <>
                    <IconPlus size={18} className="text-ink-mist-dim" />
                    <span className="font-mono text-[10px] font-bold text-ink-mist-dim">{slot.ideal_position}</span>
                  </>
                )}
              </button>
            ))}
        </div>
      ))}
    </div>
  );
}

function DraftCandidateCard({
  card,
  disabled,
  onClick,
}: {
  card: FutDraftCandidate;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex items-center gap-3 rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[card.rarity]} ${RARITY_GLOW[card.rarity]} p-[1.5px] text-left transition active:scale-[0.98] disabled:active:scale-100`}
    >
      <div className="flex w-full items-center gap-3 rounded-[15px] bg-bg-surface p-3">
        <div className="h-14 w-14 shrink-0 overflow-hidden rounded-xl bg-bg-raised">
          {card.image_path ? (
            <img src={staticUrl(card.image_path) ?? undefined} alt={card.display_name} className="h-full w-full object-cover" />
          ) : (
            <div className="flex h-full w-full items-center justify-center">
              <IconShirt size={20} className="text-ink-mist-dim" />
            </div>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate font-display text-sm font-bold text-ink-chalk">{card.display_name}</p>
          <p className="truncate text-xs text-ink-mist-dim">{card.club} · {card.country}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="font-mono text-xl font-bold text-ink-chalk">{card.rating}</p>
          <div className="flex items-center gap-1">
            <span className="rounded-full bg-white/5 px-1.5 py-0.5 font-mono text-[9px] font-bold text-accent-cyan">{card.position}</span>
            <span className={`text-[10px] font-bold uppercase ${RARITY_TEXT[card.rarity]}`}>{card.rarity}</span>
          </div>
        </div>
      </div>
    </button>
  );
}

function PlayerDetailModal({ card, onClose }: { card: FutDraftCandidate; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6" onClick={onClose}>
      <div
        className={`w-full max-w-xs rounded-2xl bg-gradient-to-b ${RARITY_GRADIENTS[card.rarity]} ${RARITY_GLOW[card.rarity]} p-[1.5px]`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex flex-col items-center gap-3 rounded-[15px] bg-bg-base p-5">
          <button onClick={onClose} className="self-end rounded-full bg-white/10 p-1.5">
            <IconClose size={14} className="text-ink-mist" />
          </button>
          <div className="h-28 w-28 overflow-hidden rounded-2xl bg-bg-surface">
            {card.image_path ? (
              <img src={staticUrl(card.image_path) ?? undefined} alt={card.display_name} className="h-full w-full object-cover" />
            ) : (
              <div className="flex h-full w-full items-center justify-center">
                <IconShirt size={32} className="text-ink-mist-dim" />
              </div>
            )}
          </div>
          <p className="text-center font-display text-lg font-bold text-ink-chalk">{card.display_name}</p>
          <p className={`text-xs font-bold uppercase ${RARITY_TEXT[card.rarity]}`}>{card.rarity}</p>
          <div className="grid w-full grid-cols-3 gap-2 text-center">
            <div className="rounded-xl bg-bg-surface py-2">
              <p className="font-mono text-lg font-bold text-accent-lime">{card.rating}</p>
              <p className="text-[9px] text-ink-mist-dim">Рейтинг</p>
            </div>
            <div className="rounded-xl bg-bg-surface py-2">
              <p className="font-mono text-lg font-bold text-accent-cyan">{card.position}</p>
              <p className="text-[9px] text-ink-mist-dim">Позиция</p>
            </div>
            <div className="rounded-xl bg-bg-surface py-2">
              <p className="truncate px-1 font-mono text-[11px] font-bold text-ink-chalk">{card.club}</p>
              <p className="text-[9px] text-ink-mist-dim">Клуб</p>
            </div>
          </div>
          <p className="text-xs text-ink-mist">{card.country}</p>
        </div>
      </div>
    </div>
  );
}

function CardArenaRoundPlayer({
  round,
  busy,
  onAct,
  onFinished,
}: {
  round: FutDraftRound;
  busy: boolean;
  onAct: (action: MatchActionKind) => void;
  onFinished: (round: FutDraftRound) => void;
}) {
  // Runs the exact same moment-by-moment engine as the real Card Arena
  // (app.services.match_service) against the temporary draft squad — this
  // component mirrors ArenaPage.tsx's MatchSimulation/ActionPrompt closely
  // on purpose, so the round plays out and reads exactly like the real one.
  const [revealedCount, setRevealedCount] = useState(0);
  const [autoSkip, setAutoSkip] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finishedFiredRef = useRef(false);
  const ackedBreakawayRef = useRef(-1);

  const total = round.events.length;
  const caughtUp = revealedCount >= total;
  const isFinished = !round.round_in_progress;

  // An opponent breakaway (empty net) has no meaningful save choice — it
  // still gets a beat of its own instead of just appearing in the log, so
  // it doesn't read as a sudden, unexplained goal.
  const nextEvent = !caughtUp ? round.events[revealedCount] : null;
  const isBreakawayNext =
    !!nextEvent &&
    nextEvent.team === "opponent" &&
    nextEvent.payload?.shot_type === "empty_net" &&
    ackedBreakawayRef.current !== revealedCount;

  useEffect(() => {
    if (caughtUp) {
      if (isFinished && !finishedFiredRef.current) {
        finishedFiredRef.current = true;
        const t = setTimeout(() => onFinished(round), 700);
        return () => clearTimeout(t);
      }
      return;
    }
    if (autoSkip) {
      setRevealedCount(total);
      return;
    }
    if (isBreakawayNext) return; // wait for the player to acknowledge it
    timerRef.current = setTimeout(() => {
      if (["goal", "save", "blocked"].includes(round.events[revealedCount]?.event_type)) haptic("medium");
      setRevealedCount((c) => c + 1);
    }, EVENT_STEP_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealedCount, caughtUp, isFinished, autoSkip, isBreakawayNext, total]);

  // Auto-play any pending action while skipping, so the round resolves
  // itself all the way to the final result without further input.
  useEffect(() => {
    if (!autoSkip || !caughtUp || isFinished || busy) return;
    const pending = round.pending_moment;
    if (!pending) return;
    onAct(pending.actions[Math.floor(Math.random() * pending.actions.length)]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoSkip, caughtUp, isFinished, busy, round]);

  const skip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setAutoSkip(true);
  };

  const ackBreakaway = () => {
    ackedBreakawayRef.current = revealedCount;
    setRevealedCount((c) => c + 1);
  };

  const revealed = round.events.slice(0, revealedCount);
  const currentMinute = revealed.length ? revealed[revealed.length - 1].minute : 0;
  const pendingMoment = caughtUp && !isFinished && !autoSkip ? round.pending_moment : null;

  // The live score only counts goals among the *revealed* events, so it
  // climbs to the final score in step with the commentary instead of
  // spoiling the outcome the instant the round starts.
  const liveUserScore = revealed.filter((e) => e.event_type === "goal" && e.team === "user").length;
  const liveOpponentScore = revealed.filter((e) => e.event_type === "goal" && e.team === "opponent").length;

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 font-mono text-xs text-ink-mist-dim">
          <IconBall size={12} />
          {caughtUp && isFinished ? "Матч завершён" : autoSkip ? "Пропускаем матч..." : `${currentMinute}' · идёт матч...`}
        </span>
        {!autoSkip && !(caughtUp && isFinished) && (
          <button onClick={skip} className="rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold text-ink-chalk">
            Пропустить
          </button>
        )}
      </div>

      <p className="mt-1 text-center font-mono text-lg font-bold text-ink-chalk">{liveUserScore} : {liveOpponentScore}</p>
      {round.opponent_name && <p className="text-center text-sm text-ink-mist">vs {round.opponent_name}</p>}

      {caughtUp && isFinished && round.result && (
        <p
          className={`mt-1 text-center font-display text-sm font-bold ${
            round.result === "win" ? "text-accent-green" : round.result === "loss" ? "text-red-400" : "text-ink-mist"
          }`}
        >
          {RESULT_LABELS[round.result]}
        </p>
      )}

      <div className="flex max-h-56 flex-col gap-1 overflow-y-auto text-xs">
        {revealed.map((e, i) => (
          <p key={i} className={e.team === "user" ? "text-accent-green" : "text-ink-mist"}>
            <span className="font-mono text-ink-mist-dim">{e.minute}&apos;</span> {e.description}
          </p>
        ))}
      </div>

      {isBreakawayNext && !autoSkip && (
        <div className="mt-1 flex flex-col items-center gap-3 rounded-2xl bg-black/20 p-4 text-center">
          <p className="text-sm font-semibold text-ink-chalk">😰 Соперник выходит один на один с твоим вратарём!</p>
          <button
            onClick={ackBreakaway}
            className="rounded-2xl bg-white/10 px-8 py-3 font-display text-base font-bold text-ink-chalk active:scale-95"
          >
            Смотреть
          </button>
        </div>
      )}

      {pendingMoment && <CardArenaActionPrompt pending={pendingMoment} disabled={busy} onAct={onAct} />}
    </div>
  );
}

function CardArenaActionPrompt({
  pending,
  disabled,
  onAct,
}: {
  pending: MatchPendingMoment;
  disabled: boolean;
  onAct: (action: MatchActionKind) => void;
}) {
  // Subtitle under a button shows the actor it concerns, if any — the
  // shooter for "shoot", the teammate for "pass". Defense actions all
  // concern the same named defender, already mentioned in the situation
  // text above, so no per-button subtitle is needed there.
  const subtitleFor = (action: MatchActionKind): string | null => {
    if (action === "shoot") return pending.actors.shooter?.name ?? null;
    if (action === "pass") return pending.actors.pass_target?.name ?? null;
    return null;
  };

  return (
    <div className="mt-1 flex flex-col items-center gap-3 rounded-2xl bg-black/20 p-4 text-center">
      <p className="text-sm font-semibold text-ink-chalk">{pending.description}</p>
      <div className={`grid gap-2 ${pending.actions.length === 1 ? "grid-cols-1" : pending.actions.length === 2 ? "grid-cols-2" : "grid-cols-3"}`}>
        {pending.actions.map((action) => {
          const { label, Icon } = ACTION_LABELS[action];
          const subtitle = subtitleFor(action);
          return (
            <button
              key={action}
              onClick={() => onAct(action)}
              disabled={disabled}
              className="flex flex-col items-center gap-1.5 rounded-2xl bg-bg-surface px-4 py-3 text-sm font-semibold text-ink-chalk active:scale-90 disabled:opacity-40"
            >
              <Icon size={16} />
              {label}
              {subtitle && <span className="text-[10px] font-normal text-ink-mist-dim">{subtitle}</span>}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function TacticoRoundPlayer({
  round,
  busy,
  errorMsg,
  onChoose,
}: {
  round: FutDraftRound;
  busy: boolean;
  errorMsg: string | null;
  onChoose: (choice: string) => void;
}) {
  const meta = GAME_TYPE_META.tactico;
  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 font-mono text-xs text-ink-mist-dim">
          <meta.Icon size={12} />
          {meta.label} · эпизод {round.phase}/{round.total_phases}
        </span>
      </div>

      <p className="text-center font-mono text-2xl font-bold text-ink-chalk">{round.user_score} : {round.bot_score}</p>

      {round.last_phase_result && (
        <p className="rounded-xl bg-white/5 px-3 py-2 text-center text-xs text-ink-mist">{round.last_phase_result}</p>
      )}

      {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}

      <p className="text-center text-xs font-semibold text-ink-mist-dim">Выбери тактику на этот эпизод</p>
      <div className="flex flex-col gap-2">
        {(round.tactic_choices ?? []).map((choice) => (
          <button
            key={choice}
            onClick={() => onChoose(choice)}
            disabled={busy}
            className="rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-chalk active:scale-95 disabled:opacity-50"
          >
            {choice}
          </button>
        ))}
      </div>
    </div>
  );
}

const PENALTY_ZONE_LABELS: Record<string, string> = {
  top_left: "Верх, слева",
  top_center: "Верх, центр",
  top_right: "Верх, справа",
  bottom_left: "Низ, слева",
  bottom_center: "Низ, центр",
  bottom_right: "Низ, справа",
};

function PenaltyRoundPlayer({
  round,
  busy,
  errorMsg,
  onKick,
}: {
  round: FutDraftRound;
  busy: boolean;
  errorMsg: string | null;
  onKick: (direction: string) => void;
}) {
  const meta = GAME_TYPE_META.penalty;
  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-1.5 font-mono text-xs text-ink-mist-dim">
          <meta.Icon size={12} />
          {meta.label} · удар {round.kick_number}
        </span>
      </div>

      <p className="text-center font-mono text-2xl font-bold text-ink-chalk">{round.user_score} : {round.bot_score}</p>

      {round.picked_player && (
        <div className="flex items-center gap-3 rounded-xl bg-white/5 px-3 py-2">
          <div className="h-10 w-10 shrink-0 overflow-hidden rounded-lg bg-bg-raised">
            {round.picked_player.image_path ? (
              <img
                src={staticUrl(round.picked_player.image_path) ?? undefined}
                alt=""
                className="h-full w-full object-cover"
              />
            ) : (
              <div className="flex h-full w-full items-center justify-center">
                <IconShirt size={14} className="text-ink-mist-dim" />
              </div>
            )}
          </div>
          <p className="truncate text-sm font-semibold text-ink-chalk">{round.picked_player.display_name}</p>
        </div>
      )}

      {round.last_kick_result && (
        <p className="rounded-xl bg-white/5 px-3 py-2 text-center text-xs text-ink-mist">{round.last_kick_result}</p>
      )}

      {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}

      <p className="text-center text-xs font-semibold text-ink-mist-dim">Выбери, куда пробить</p>
      <div className="grid grid-cols-3 gap-2">
        {(round.zone_choices ?? []).map((zone) => (
          <button
            key={zone}
            onClick={() => onKick(zone)}
            disabled={busy}
            className="rounded-xl bg-white/5 py-3 text-[11px] font-semibold text-ink-chalk active:scale-95 disabled:opacity-50"
          >
            {PENALTY_ZONE_LABELS[zone] ?? zone}
          </button>
        ))}
      </div>
    </div>
  );
}
