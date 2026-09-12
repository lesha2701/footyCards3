import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  chooseFutDraftFormation,
  claimFutDraftReward,
  fetchFutDraftLeaderboard,
  startFutDraft,
  startFutDraftMatch,
  submitFutDraftPick,
} from "@/api/games";
import { IconCoin, IconShirt, IconTrophy } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { RARITY_GRADIENTS, RARITY_GLOW, RARITY_TEXT } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { FutDraftCandidate, FutDraftClaim, FutDraftMatchResult, FutDraftPick } from "@/types";

type Phase = "idle" | "choose_formation" | "drafting" | "ready" | "finished";

const RESULT_LABELS: Record<string, string> = { win: "Победа", draw: "Ничья", loss: "Поражение" };

export default function FutDraftGamePage() {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [phase, setPhase] = useState<Phase>("idle");
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [formationOptions, setFormationOptions] = useState<string[]>([]);
  const [formation, setFormation] = useState<string>("");
  const [slotIndex, setSlotIndex] = useState(0);
  const [totalSlots, setTotalSlots] = useState(11);
  const [slotCategory, setSlotCategory] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<FutDraftCandidate[]>([]);
  const [picks, setPicks] = useState<FutDraftPick[]>([]);
  const [teamStrength, setTeamStrength] = useState<number | null>(null);
  const [matchResults, setMatchResults] = useState<FutDraftMatchResult[]>([]);
  const [claimResult, setClaimResult] = useState<FutDraftClaim | null>(null);
  const [busy, setBusy] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const { data: leaderboard } = useQuery({ queryKey: ["fut-draft-leaderboard"], queryFn: fetchFutDraftLeaderboard });

  const resetForNewDraft = () => {
    setSessionId(null);
    setFormationOptions([]);
    setFormation("");
    setSlotIndex(0);
    setTotalSlots(11);
    setSlotCategory(null);
    setCandidates([]);
    setPicks([]);
    setTeamStrength(null);
    setMatchResults([]);
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
      setSlotIndex(state.slot_index);
      setTotalSlots(state.total_slots);
      setSlotCategory(state.slot_category);
      setCandidates(state.candidates ?? []);
      setPicks(state.picks);
      setPhase("drafting");
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось выбрать схему"));
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
      setSlotIndex(state.slot_index);
      setSlotCategory(state.slot_category);
      setCandidates(state.candidates ?? []);
      setPicks(state.picks);
      if (state.phase === "ready") {
        setTeamStrength(state.team_strength);
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
    setBusy(true);
    try {
      const data = await claimFutDraftReward(id);
      updateBalance(data.new_balance);
      hapticNotify("success");
      setClaimResult(data);
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось начислить награду"));
    } finally {
      setBusy(false);
    }
  };

  const playMatch = async () => {
    if (busy || sessionId === null) return;
    setBusy(true);
    setErrorMsg(null);
    try {
      const result = await startFutDraftMatch(sessionId);
      setMatchResults((prev) => [...prev, result]);
      if (result.result === "win") haptic("medium");
      else haptic("heavy");
      if (result.is_finished) {
        hapticNotify(result.wins === 4 ? "success" : "warning");
        setPhase("finished");
        claim(sessionId);
      }
    } catch (err) {
      setErrorMsg(formatGameError(err, "Не удалось сыграть матч"));
    } finally {
      setBusy(false);
    }
  };

  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-xl font-bold text-ink-chalk">FUT Draft</h1>
        <p className="text-sm text-ink-mist">
          Заплати за вход и собери временный состав из случайных карт всей игры — даже тех, которых нет в твоей
          коллекции. Выбери схему, задрафти 11 игроков по одному на позицию и сыграй до 4 матчей на вылет.
          Чем дальше пройдёшь — тем больше награда.
        </p>

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

  if (phase === "drafting") {
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between rounded-2xl bg-bg-surface px-4 py-3">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wide text-ink-mist-dim">Слот</p>
            <p className="font-display text-lg font-bold text-ink-chalk">{slotIndex + 1}/{totalSlots}</p>
          </div>
          <div className="text-right">
            <p className="font-mono text-[10px] uppercase tracking-wide text-ink-mist-dim">Линия</p>
            <p className="font-display text-lg font-bold text-ink-chalk">{slotCategory}</p>
          </div>
        </div>

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}

        <div className="flex flex-col gap-3">
          {candidates.map((card) => (
            <DraftCandidateCard key={card.id} card={card} disabled={busy} onClick={() => pick(card.id)} />
          ))}
        </div>

        {picks.length > 0 && (
          <div className="rounded-2xl bg-bg-surface p-3">
            <p className="mb-2 text-xs font-semibold text-ink-mist-dim">Уже в составе</p>
            <div className="flex flex-wrap gap-1.5">
              {picks.map((p) => (
                <span key={p.slot_code} className="rounded-full bg-white/5 px-2 py-1 text-[10px] text-ink-mist">
                  {p.player.display_name}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  }

  if (phase === "ready") {
    const nextRound = matchResults.length + 1;
    return (
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between rounded-2xl bg-bg-surface px-4 py-3">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-wide text-ink-mist-dim">Схема</p>
            <p className="font-display text-lg font-bold text-ink-chalk">{formation}</p>
          </div>
          <div className="text-right">
            <p className="font-mono text-[10px] uppercase tracking-wide text-ink-mist-dim">Сила состава</p>
            <p className="font-display text-lg font-bold text-accent-lime">{teamStrength}</p>
          </div>
        </div>

        {matchResults.length > 0 && (
          <div className="flex flex-col gap-2">
            {matchResults.map((r, i) => (
              <div key={i} className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2 text-sm">
                <span className="text-ink-mist">Матч {i + 1} ({RESULT_LABELS[r.result]})</span>
                <span className="font-mono font-bold text-ink-chalk">{r.user_score}:{r.bot_score}</span>
              </div>
            ))}
          </div>
        )}

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}

        <button
          onClick={playMatch}
          disabled={busy}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {busy ? "Играем..." : `Играть матч ${nextRound}/4`}
        </button>

        <div className="rounded-2xl bg-bg-surface p-3">
          <p className="mb-2 text-xs font-semibold text-ink-mist-dim">Состав</p>
          <div className="flex flex-wrap gap-1.5">
            {picks.map((p) => (
              <span key={p.slot_code} className={`rounded-full px-2 py-1 text-[10px] ${RARITY_TEXT[p.player.rarity]}`}>
                {p.player.display_name}
              </span>
            ))}
          </div>
        </div>
      </div>
    );
  }

  const wins = matchResults.filter((r) => r.result === "win").length;
  return (
    <div className="flex flex-col items-center gap-5 py-6 text-center">
      <IconTrophy size={40} className={wins === 4 ? "text-accent-lime" : "text-ink-mist-dim"} />
      <p className="font-display text-2xl font-bold text-ink-chalk">
        {wins === 4 ? "Идеальный драфт!" : `Драфт окончен — ${wins}/4 побед`}
      </p>

      {busy && !claimResult ? (
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
      ) : errorMsg ? (
        <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>
      ) : null}

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
