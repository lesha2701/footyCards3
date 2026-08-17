import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { cancelPenaltySearch, fetchPenaltyMatch, fetchPenaltySearchStatus, startPenaltySearch } from "@/api/penalty";
import { fetchPublicProfile } from "@/api/profile";
import { UserBadge } from "@/components/common/UserBadge";
import { IconTarget, IconUsers } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import type { ProfilePublic } from "@/types";

const REVEAL_PAUSE_MS = 3000;
// Mirrors the backend's MATCHMAKING_TIMEOUT_SECONDS (penalty_match_service.py) —
// purely cosmetic, the server is the actual source of truth for the timeout.
const SEARCH_TIMEOUT_SECONDS = 60;

export default function PenaltySearchPage({ userCardId }: { userCardId: number }) {
  const navigate = useNavigate();
  const [phase, setPhase] = useState<"starting" | "searching" | "timeout" | "reveal" | "error">("starting");
  const [error, setError] = useState<string | null>(null);
  const [opponent, setOpponent] = useState<ProfilePublic | null>(null);
  // Bumping this re-runs the search-start effect below for a genuine retry
  // (e.g. after a timeout) — a plain empty-deps effect would only ever fire
  // once per mount.
  const [searchAttempt, setSearchAttempt] = useState(0);
  const revealTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Guards against React 18 StrictMode's dev-only double-invoke of effects
  // (mount → cleanup → mount) firing startPenaltySearch() twice for the same
  // attempt — the second call would 409 ("Ты уже ищешь соперника") and knock
  // phase back to "error" right after the first call's "searching" landed.
  // Keyed by attempt number (rather than a plain boolean, as PackOpenPage's
  // one-shot hasStartedRef uses) so a later, genuine retry isn't blocked.
  const startedAttemptRef = useRef<number | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(SEARCH_TIMEOUT_SECONDS);

  useEffect(() => {
    if (startedAttemptRef.current === searchAttempt) return;
    startedAttemptRef.current = searchAttempt;
    setPhase("starting");
    setSecondsLeft(SEARCH_TIMEOUT_SECONDS);
    startPenaltySearch(userCardId)
      .then(() => setPhase("searching"))
      .catch((err) => {
        setPhase("error");
        setError(formatGameError(err, "Не удалось начать поиск соперника"));
      });
  }, [searchAttempt, userCardId]);

  useEffect(() => {
    if (phase !== "searching") return;
    const interval = setInterval(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(interval);
  }, [phase]);

  // Clears any pending reveal→match-navigation timer if the player leaves
  // this page during the 3s reveal window, so it can't fire later and force
  // a navigation regardless of where they've gone (mirrors PackOpenPage's
  // timerRef cleanup pattern).
  useEffect(() => {
    return () => {
      if (revealTimerRef.current) clearTimeout(revealTimerRef.current);
    };
  }, []);

  const { data: status } = useQuery({
    queryKey: ["penalty-search-status"],
    queryFn: fetchPenaltySearchStatus,
    enabled: phase === "searching",
    refetchInterval: () => (phase === "searching" ? 2000 : false),
  });

  useEffect(() => {
    if (!status) return;
    if (status.status === "timeout" || status.status === "not_searching") {
      // "not_searching" happens when the pairing algorithm drops our own
      // entry as stale during a pairing attempt (active match / card
      // traded away / hourly limit — see get_search_status's
      // re-validation). Without this branch the player would poll a
      // nonexistent search forever, with only "Отменить" as an escape —
      // and that call would itself 404 since the row is already gone.
      // Treat it the same as a plain timeout.
      setPhase("timeout");
    } else if (status.status === "matched" && status.match_id) {
      const matchId = status.match_id;
      fetchPenaltyMatchOpponentAndReveal(matchId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.status, status?.match_id]);

  const fetchPenaltyMatchOpponentAndReveal = async (matchId: number) => {
    try {
      const match = await fetchPenaltyMatch(matchId);
      if (match.opponent_user_id) {
        const profile = await fetchPublicProfile(match.opponent_user_id);
        setOpponent(profile);
      }
      setPhase("reveal");
      revealTimerRef.current = setTimeout(() => navigate(`/play/penalty/matches/${matchId}`), REVEAL_PAUSE_MS);
    } catch {
      // The match exists even if the reveal fetch failed for some reason —
      // don't strand the player on a dead search screen over a cosmetic step.
      navigate(`/play/penalty/matches/${matchId}`);
    }
  };

  const handleCancel = async () => {
    try {
      await cancelPenaltySearch();
    } catch {
      // Ignore — if this fails because pairing already happened, the
      // player is about to be redirected into the match anyway.
    }
    navigate("/play/penalty/matches");
  };

  if (phase === "error") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-sm text-red-400">{error}</p>
        <button
          onClick={() => navigate("/play/penalty/matches")}
          className="rounded-2xl bg-white/5 px-6 py-3 text-sm font-bold text-ink-chalk active:scale-95"
        >
          Назад
        </button>
      </div>
    );
  }

  if (phase === "timeout") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <IconUsers size={40} className="text-ink-mist-dim" />
        <p className="font-display text-lg font-bold text-ink-chalk">Соперник не найден</p>
        <p className="text-sm text-ink-mist">Попробуй ещё раз</p>
        <div className="flex w-full gap-2">
          <button
            onClick={() => navigate("/play/penalty/matches")}
            className="flex-1 rounded-2xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95"
          >
            Назад
          </button>
          <button
            onClick={() => setSearchAttempt((n) => n + 1)}
            className="flex-1 rounded-2xl bg-accent py-3 text-sm font-bold text-bg-base active:scale-95"
          >
            Попробовать снова
          </button>
        </div>
      </div>
    );
  }

  if (phase === "reveal") {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <p className="text-sm text-accent-lime">Соперник найден!</p>
        {opponent ? (
          <>
            <img
              src={opponent.avatar_url ?? staticUrl("players/placeholder/player_placeholder.webp")}
              alt="avatar"
              className="h-20 w-20 rounded-full ring-2 ring-accent-lime object-cover"
            />
            <p className="flex items-center gap-1.5 font-display text-xl font-bold text-ink-chalk">
              {opponent.username ?? opponent.first_name ?? "Игрок"}
              <UserBadge badge={opponent.active_badge} />
            </p>
            <p className="text-sm text-ink-mist">Рейтинг Пенальти: {opponent.penalty_rating}</p>
          </>
        ) : (
          <p className="text-sm text-ink-mist">Загрузка...</p>
        )}
        <p className="animate-pulse text-xs text-ink-mist-dim">Матч начинается...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
      <IconTarget size={40} className="animate-pulse text-accent-lime" />
      <p className="font-display text-lg font-bold text-ink-chalk">Ищем соперника...</p>
      <p className={`font-mono text-2xl font-bold tabular-nums ${secondsLeft <= 10 ? "text-red-400" : "text-ink-mist"}`}>
        0:{String(secondsLeft).padStart(2, "0")}
      </p>
      <button
        onClick={handleCancel}
        className="rounded-2xl bg-white/5 px-6 py-3 text-sm font-bold text-ink-chalk active:scale-95"
      >
        Отменить
      </button>
    </div>
  );
}
