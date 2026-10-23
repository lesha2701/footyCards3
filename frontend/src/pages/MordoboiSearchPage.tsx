import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { cancelMordoboiSearch, fetchMordoboiSearchStatus, startMordoboiSearch } from "@/api/mordoboi";
import { IconBoxingGlove } from "@/components/icons";
import { formatGameError } from "@/lib/errors";

// Mirrors MATCHMAKING_TIMEOUT_SECONDS in mordoboi_service.py — cosmetic only.
const SEARCH_TIMEOUT_SECONDS = 60;

export default function MordoboiSearchPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<"starting" | "searching" | "timeout" | "error">("starting");
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [secondsLeft, setSecondsLeft] = useState(SEARCH_TIMEOUT_SECONDS);
  // StrictMode double-invokes effects in dev; never POST search twice per attempt.
  const startedAttemptRef = useRef<number | null>(null);

  useEffect(() => {
    if (startedAttemptRef.current === attempt) return;
    startedAttemptRef.current = attempt;
    setPhase("starting");
    setSecondsLeft(SEARCH_TIMEOUT_SECONDS);
    queryClient.removeQueries({ queryKey: ["mordoboi-search-status"] });
    startMordoboiSearch()
      .then(() => setPhase("searching"))
      .catch((err) => {
        setPhase("error");
        setError(formatGameError(err, "Не удалось начать поиск соперника"));
      });
  }, [attempt, queryClient]);

  useEffect(() => {
    if (phase !== "searching") return;
    const interval = setInterval(() => setSecondsLeft((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(interval);
  }, [phase]);

  const { data: status } = useQuery({
    queryKey: ["mordoboi-search-status"],
    queryFn: fetchMordoboiSearchStatus,
    enabled: phase === "searching",
    refetchInterval: () => (phase === "searching" ? 2000 : false),
  });

  useEffect(() => {
    if (!status || phase !== "searching") return;
    if (status.status === "matched" && status.match_id) {
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      navigate(`/play/mordoboi/matches/${status.match_id}`, { replace: true });
    } else if (status.status === "timeout" || status.status === "not_searching") {
      setPhase("timeout");
    }
  }, [status, phase, navigate, queryClient]);

  const cancel = async () => {
    try {
      await cancelMordoboiSearch();
    } catch {
      // Already matched or gone — leaving is still the right outcome.
    }
    navigate("/play/mordoboi");
  };

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-5 text-center">
      <span className="flex h-20 w-20 animate-pulse items-center justify-center rounded-full bg-yellow-500/20">
        <IconBoxingGlove size={36} className="text-yellow-400" />
      </span>
      {phase === "searching" || phase === "starting" ? (
        <>
          <p className="font-display text-lg font-bold text-ink-chalk">Ищем соперника…</p>
          <p className="text-xs text-ink-mist">
            Осталось ~{secondsLeft} с. Если никого не найдём — сыграешь с ботом.
          </p>
          <button onClick={cancel} className="rounded-2xl bg-white/5 px-6 py-3 text-sm font-semibold text-ink-mist active:scale-95">
            Отменить
          </button>
        </>
      ) : (
        <>
          <p className="font-display text-lg font-bold text-ink-chalk">
            {phase === "timeout" ? "Соперник не найден" : "Поиск не начался"}
          </p>
          {error && <p className="text-xs text-red-400">{error}</p>}
          <div className="flex gap-2">
            <button onClick={() => setAttempt((a) => a + 1)} className="rounded-2xl bg-yellow-500 px-6 py-3 text-sm font-bold text-bg-base active:scale-95">
              Ещё раз
            </button>
            <button onClick={() => navigate("/play/mordoboi")} className="rounded-2xl bg-white/5 px-6 py-3 text-sm font-semibold text-ink-mist active:scale-95">
              Назад
            </button>
          </div>
        </>
      )}
    </div>
  );
}
