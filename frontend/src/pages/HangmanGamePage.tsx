import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimHangmanReward, guessHangmanLetter, startHangman } from "@/api/games";
import { IconCoin, IconFlag, IconTrophy } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { HangmanGuessResult } from "@/types";

type Phase = "idle" | "playing" | "won" | "lost";

const KEYBOARD_ROWS = [
  "АБВГДЕЁЖЗИЙ",
  "КЛМНОПРСТУФ",
  "ХЦЧШЩЪЫЬЭЮЯ",
];

const CATEGORY_LABEL: Record<string, string> = {
  player: "Загадан футболист",
  term: "Загадано футбольное понятие",
};

export default function HangmanGamePage() {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [category, setCategory] = useState<string>("term");
  const [maxWrong, setMaxWrong] = useState(6);
  const [maskedWord, setMaskedWord] = useState<string[]>([]);
  const [guessedLetters, setGuessedLetters] = useState<string[]>([]);
  const [wrongLetters, setWrongLetters] = useState<string[]>([]);
  const [revealedWord, setRevealedWord] = useState<string | null>(null);
  const [claimResult, setClaimResult] = useState<{ reward_coins: number } | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const startMutation = useMutation({
    mutationFn: startHangman,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      setCategory(data.category);
      setMaxWrong(data.max_wrong);
      setMaskedWord(data.masked_word);
      setGuessedLetters([]);
      setWrongLetters([]);
      setRevealedWord(null);
      setClaimResult(null);
      setErrorMsg(null);
      setPhase("playing");
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать игру")),
  });

  const applyGuessResult = (result: HangmanGuessResult) => {
    setMaskedWord(result.masked_word);
    setGuessedLetters(result.guessed_letters);
    setWrongLetters(result.wrong_letters);
    if (result.status === "won") {
      haptic("medium");
      hapticNotify("success");
      setRevealedWord(result.word);
      setPhase("won");
    } else if (result.status === "lost") {
      haptic("heavy");
      hapticNotify("error");
      setRevealedWord(result.word);
      setPhase("lost");
    } else {
      haptic(result.is_correct ? "light" : "medium");
    }
  };

  const guessMutation = useMutation({
    mutationFn: (letter: string) => guessHangmanLetter(sessionId!, letter),
    onSuccess: applyGuessResult,
  });

  const claimMutation = useMutation({
    mutationFn: () => claimHangmanReward(sessionId!),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      setClaimResult(data);
    },
  });

  if (phase === "idle") {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Футбольная виселица</h1>
        <p className="text-sm text-ink-mist">
          Угадай загаданного футболиста или футбольное понятие по буквам. Ошибёшься 6 раз — судья покажет красную,
          и раунд проигран.
        </p>

        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <button
          onClick={() => startMutation.mutate()}
          disabled={startMutation.isPending}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {startMutation.isPending ? "Загрузка..." : "Начать игру"}
        </button>
      </div>
    );
  }

  if (phase === "won" || phase === "lost") {
    const isWin = phase === "won";
    return (
      <div className="flex flex-col items-center gap-5 py-6 text-center">
        {isWin ? <IconTrophy size={40} className="text-accent-lime" /> : <IconFlag size={40} className="text-red-500" />}
        <p className="font-display text-2xl font-bold text-ink-chalk">{isWin ? "Угадал!" : "Не угадал"}</p>
        <p className="text-sm text-ink-mist">
          Загаданное слово: <span className="font-bold text-ink-chalk">{revealedWord}</span>
        </p>

        {!claimResult ? (
          <button
            onClick={() => claimMutation.mutate()}
            disabled={claimMutation.isPending || !isWin}
            className="rounded-2xl bg-floodlight px-6 py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
          >
            {claimMutation.isPending ? "Начисление..." : isWin ? "Забрать награду" : "Награды нет"}
          </button>
        ) : (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              +{claimResult.reward_coins}
              <IconCoin size={16} />
            </p>
          </div>
        )}

        <div className="flex gap-3">
          <button onClick={() => setPhase("idle")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Ещё раз
          </button>
          <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
            Назад
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <p className="text-center text-xs font-semibold text-ink-mist">{CATEGORY_LABEL[category] ?? "Загадано слово"}</p>

      <Gallows wrongCount={wrongLetters.length} maxWrong={maxWrong} />

      <div className="flex flex-wrap justify-center gap-1.5">
        {maskedWord.map((ch, i) =>
          ch === " " ? (
            <span key={i} className="w-3" />
          ) : (
            <span
              key={i}
              className="flex h-9 w-7 items-center justify-center rounded-md border-b-2 border-accent-green bg-white/5 font-display text-base font-bold text-ink-chalk"
            >
              {ch === "_" ? "" : ch}
            </span>
          )
        )}
      </div>

      <p className="text-center font-mono text-xs text-ink-mist-dim">
        Ошибки: {wrongLetters.length}/{maxWrong}
      </p>

      <div className="flex flex-col gap-1.5">
        {KEYBOARD_ROWS.map((row, i) => (
          <div key={i} className="flex justify-center gap-1">
            {row.split("").map((letter) => {
              const isGuessed = guessedLetters.includes(letter);
              const isWrong = wrongLetters.includes(letter);
              return (
                <button
                  key={letter}
                  onClick={() => guessMutation.mutate(letter)}
                  disabled={isGuessed || guessMutation.isPending}
                  className={`flex h-9 w-8 items-center justify-center rounded-lg text-sm font-bold active:scale-90 disabled:active:scale-100 ${
                    isGuessed
                      ? isWrong
                        ? "bg-red-500/20 text-red-400"
                        : "bg-accent-green/20 text-accent-green"
                      : "bg-bg-surface text-ink-chalk"
                  }`}
                >
                  {letter}
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

const MAX_BODY_PARTS = 6;

function Gallows({ wrongCount, maxWrong }: { wrongCount: number; maxWrong: number }) {
  const partsToShow = Math.min(wrongCount, MAX_BODY_PARTS, maxWrong);

  return (
    <div className="relative flex h-40 items-end justify-center overflow-hidden rounded-2xl bg-bg-surface">
      <div className="absolute inset-x-0 bottom-0 h-6 bg-black/20" />
      <div className="absolute bottom-6 left-1/2 h-1 w-28 -translate-x-1/2 rounded-full border border-white/30" />

      <svg viewBox="0 0 120 100" className="relative h-36 w-32">
        {/* goalpost-style gallows */}
        <line x1="20" y1="90" x2="20" y2="10" stroke="white" strokeWidth="4" />
        <line x1="20" y1="10" x2="75" y2="10" stroke="white" strokeWidth="4" />
        <line x1="20" y1="20" x2="35" y2="10" stroke="white" strokeWidth="3" />
        <line x1="75" y1="10" x2="75" y2="24" stroke="#d1d5db" strokeWidth="2" />

        {partsToShow >= 1 && <circle cx="75" cy="34" r="7" fill="white" stroke="#111827" strokeWidth="1" />}
        {partsToShow >= 2 && <rect x="68" y="41" width="14" height="20" rx="3" fill="#3ed17e" />}
        {partsToShow >= 3 && <line x1="68" y1="45" x2="58" y2="58" stroke="#facc15" strokeWidth="3" strokeLinecap="round" />}
        {partsToShow >= 4 && <line x1="82" y1="45" x2="92" y2="58" stroke="#facc15" strokeWidth="3" strokeLinecap="round" />}
        {partsToShow >= 5 && <rect x="69" y="61" width="12" height="10" fill="#1e293b" />}
        {partsToShow >= 6 && (
          <>
            <line x1="72" y1="71" x2="68" y2="86" stroke="#1e293b" strokeWidth="4" strokeLinecap="round" />
            <line x1="78" y1="71" x2="82" y2="86" stroke="#1e293b" strokeWidth="4" strokeLinecap="round" />
          </>
        )}
      </svg>
    </div>
  );
}
