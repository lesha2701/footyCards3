import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { startMuseDate, type MuseAlbum } from "@/api/muses";
import { IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { haptic } from "@/lib/telegram";

const timeOf = (iso: string) =>
  new Date(iso).toLocaleString("ru-RU", { weekday: "short", hour: "2-digit", minute: "2-digit" });

/** Whether the active Muse is inspired (her bonus works) — one short line. */
export function MuseMoodLine({ album }: { album: MuseAlbum }) {
  const { date } = album;
  if (date.inspired_until) {
    return <p className="text-caption text-pink-200">Вдохновлена до {timeOf(date.inspired_until)}</p>;
  }
  if (!date.required) return null;
  return <p className="text-caption font-semibold text-amber-300">Муза скучает — бонус не действует, сходи на свидание</p>;
}

/** «Свидание»: once a day a random mini-game with the active Muse — an
 * extra attempt, any result counts. Opens the game with ?muse=1. */
export default function MuseDateButton({ album, className = "" }: { album: MuseAlbum; className?: string }) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: startMuseDate,
    onSuccess: (date) => navigate(date.path),
    onError: (err) => setError(formatGameError(err, "Свидание не началось")),
  });
  if (!album.active) return null;
  const today = album.date.today;
  if (today?.completed) {
    return (
      <p className={`rounded-full bg-pink-500/10 px-3 py-2 text-center text-xs font-semibold text-pink-200 ${className}`}>
        Свидание сегодня было ✓ · завтра — новое
      </p>
    );
  }
  return (
    <div className={className}>
      <button
        onClick={() => {
          haptic("light");
          start.mutate();
        }}
        disabled={start.isPending}
        className="flex w-full items-center justify-center gap-1 rounded-full bg-gradient-to-r from-pink-500 to-fuchsia-500 py-2.5 text-xs font-bold text-white active:scale-95 disabled:opacity-50"
      >
        💞 {today ? `Продолжить свидание: ${today.game_title}` : "Свидание: случайная мини-игра"} · +{album.date.coins}
        <IconCoin size={12} />
      </button>
      {error && <p className="mt-1 text-center text-caption text-red-400">{error}</p>}
    </div>
  );
}
