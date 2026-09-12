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
  submitFutDraftPick,
} from "@/api/games";
import { IconCoin, IconHelp, IconPlus, IconShirt, IconTrophy } from "@/components/icons";
import { CATEGORY_LABELS, type FormationSlot } from "@/lib/formation";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_TEXT } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { FutDraftCandidate, FutDraftClaim, FutDraftMatchResult, FutDraftSlot } from "@/types";

type Phase = "idle" | "choose_formation" | "drafting" | "ready" | "match" | "finished";

const EVENT_STEP_MS = 900;
const RESULT_LABELS: Record<string, string> = { win: "Победа", draw: "Ничья", loss: "Поражение" };
const STRENGTH_HINT =
  "Сила состава = рейтинг игрока × соответствие позиции (сильнее всего на своей родной позиции) × бонус за редкость, " +
  "плюс бонус, если в составе несколько игроков одного клуба или одной страны.";

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
  const [matchHistory, setMatchHistory] = useState<FutDraftMatchResult[]>([]);
  const [currentMatch, setCurrentMatch] = useState<FutDraftMatchResult | null>(null);
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
    setMatchHistory([]);
    setCurrentMatch(null);
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
      setCurrentMatch(result);
      setPhase("match");
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось сыграть матч"));
    } finally {
      setBusy(false);
    }
  };

  const handleMatchFinished = (match: FutDraftMatchResult) => {
    setMatchHistory((prev) => [...prev, match]);
    setCurrentMatch(null);
    if (match.is_finished) {
      hapticNotify(match.wins === 4 ? "success" : "warning");
      setPhase("finished");
      claim(match.session_id);
    } else {
      setPhase("ready");
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

        <div className="flex items-center justify-between rounded-2xl bg-bg-surface px-4 py-3">
          <span className="text-sm text-ink-mist">Стоимость входа</span>
          <span className="flex items-center gap-1 font-mono text-base font-bold text-accent-lime">
            {config?.entry_cost ?? "..."}
            <IconCoin size={14} />
          </span>
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

        <Pitch formation={formation} slots={slots} onSlotClick={openSlot} disabled={busy || pendingSlot !== null} />

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
                    <span className="text-ink-mist">Матч {i + 1} ({RESULT_LABELS[r.result]})</span>
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
      </div>
    );
  }

  if (phase === "match" && currentMatch) {
    return <FutDraftMatchSimulation match={currentMatch} onFinished={handleMatchFinished} />;
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
  disabled,
}: {
  formation: string;
  slots: FutDraftSlot[];
  onSlotClick: (slotCode: string) => void;
  disabled: boolean;
}) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-gradient-to-b from-emerald-950/60 to-emerald-900/30 p-3">
      <p className="text-center font-mono text-[10px] uppercase tracking-wide text-ink-mist-dim">{formation}</p>
      {(["FWD", "MID", "DEF", "GK"] as const).map((category) => (
        <div key={category} className="flex justify-evenly gap-2">
          {slots
            .filter((s) => s.category === category)
            .map((slot) => (
              <button
                key={slot.slot_code}
                onClick={() => (slot.player ? undefined : onSlotClick(slot.slot_code))}
                disabled={disabled || !!slot.player}
                className={`flex min-w-0 max-w-[84px] flex-1 flex-col items-center gap-1 rounded-xl p-1.5 backdrop-blur-sm ${
                  slot.player ? `bg-gradient-to-b ${RARITY_GRADIENTS[slot.player.rarity]} ${RARITY_GLOW[slot.player.rarity]} p-[1.5px]` : "bg-black/30 active:scale-95 disabled:active:scale-100"
                }`}
              >
                {slot.player ? (
                  <div className="flex w-full flex-col items-center gap-1 rounded-[9px] bg-bg-surface p-1">
                    <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                      {slot.player.image_path ? (
                        <img src={staticUrl(slot.player.image_path) ?? undefined} alt="" className="h-full w-full object-cover" loading="lazy" />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <IconShirt size={16} className="text-ink-mist-dim" />
                        </div>
                      )}
                    </div>
                    <span className="truncate w-full text-center font-mono text-[9px] font-bold leading-none text-ink-chalk">{slot.player.rating}</span>
                  </div>
                ) : (
                  <>
                    <IconPlus size={18} className="text-ink-mist-dim" />
                    <span className="text-[9px] text-ink-mist-dim">{CATEGORY_LABELS[slot.category as FormationSlot["category"]] ?? slot.category}</span>
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
          <p className={`text-[10px] font-bold uppercase ${RARITY_TEXT[card.rarity]}`}>{card.rarity}</p>
        </div>
      </div>
    </button>
  );
}

function FutDraftMatchSimulation({
  match,
  onFinished,
}: {
  match: FutDraftMatchResult;
  onFinished: (match: FutDraftMatchResult) => void;
}) {
  const [revealedCount, setRevealedCount] = useState(0);
  const [autoSkip, setAutoSkip] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const finishedFiredRef = useRef(false);

  const total = match.events.length;
  const caughtUp = revealedCount >= total;

  useEffect(() => {
    if (caughtUp) {
      if (!finishedFiredRef.current) {
        finishedFiredRef.current = true;
        const t = setTimeout(() => onFinished(match), 700);
        return () => clearTimeout(t);
      }
      return;
    }
    if (autoSkip) {
      setRevealedCount(total);
      return;
    }
    timerRef.current = setTimeout(() => {
      if (match.events[revealedCount]?.type === "goal") haptic("medium");
      setRevealedCount((c) => c + 1);
    }, EVENT_STEP_MS);
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [revealedCount, caughtUp, autoSkip, total]);

  const skip = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    setAutoSkip(true);
  };

  const revealed = match.events.slice(0, revealedCount);
  const liveUserScore = revealed.filter((e) => e.type === "goal" && e.team === "user").length;
  const liveBotScore = revealed.filter((e) => e.type === "goal" && e.team === "bot").length;
  const currentMinute = revealed.length ? revealed[revealed.length - 1].minute : 0;

  return (
    <div className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-ink-mist-dim">
          {caughtUp ? "Матч завершён" : autoSkip ? "Пропускаем матч..." : `${currentMinute}' · идёт матч...`}
        </span>
        {!autoSkip && !caughtUp && (
          <button onClick={skip} className="rounded-full bg-white/10 px-3 py-1 text-[11px] font-semibold text-ink-chalk">
            Пропустить
          </button>
        )}
      </div>

      <p className="text-center font-mono text-2xl font-bold text-ink-chalk">{liveUserScore} : {liveBotScore}</p>

      {caughtUp && (
        <p
          className={`text-center font-display text-sm font-bold ${
            match.result === "win" ? "text-accent-green" : match.result === "loss" ? "text-red-400" : "text-ink-mist"
          }`}
        >
          {RESULT_LABELS[match.result]}
        </p>
      )}

      <div className="flex max-h-56 flex-col gap-1 overflow-y-auto text-xs">
        {revealed.map((e, i) => (
          <p key={i} className={e.team === "user" ? "text-accent-green" : "text-ink-mist"}>
            <span className="font-mono text-ink-mist-dim">{e.minute}&apos;</span> {e.text}
          </p>
        ))}
      </div>
    </div>
  );
}
