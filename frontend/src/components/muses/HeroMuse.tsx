import { useMutation, useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchMuses, startMuseDate, type MuseAlbum } from "@/api/muses";
import MuseArt from "@/components/muses/MuseArt";
import MuseHeart from "@/components/muses/MuseHeart";
import { formatGameError } from "@/lib/errors";
import { museHeartState, type MuseHeartState } from "@/lib/museDate";
import { haptic } from "@/lib/telegram";

const STATUS: Record<MuseHeartState, string> = {
  date: "Ждёт свидания",
  inspired: "Вдохновлена",
  bored: "Скучает — бонус не действует",
};

/** The active «Муза» in the home hero («С возвращением»): a square portrait
 * with a heart in the corner (red — today's date waits, brand gradient —
 * inspired, black — misses you). Hover (or tap on a phone) opens a small
 * card: her status, «Профиль музы» (the «Музы» page opened on her — gifts,
 * another Muse) and today's date. Hidden while Muses are off or the player
 * has none. */
export function HeroMusePortrait() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const { data } = useQuery({ queryKey: ["muses"], queryFn: fetchMuses });

  useEffect(() => {
    if (!open) return;
    const close = (e: PointerEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", close);
    return () => document.removeEventListener("pointerdown", close);
  }, [open]);

  if (!data?.enabled || !data.active) return null;
  const active = data.active;

  return (
    <div
      ref={ref}
      className="relative shrink-0"
      // Hover is for a mouse only; on a touch screen the tap toggles it.
      onPointerEnter={(e) => e.pointerType === "mouse" && setOpen(true)}
      onPointerLeave={(e) => e.pointerType === "mouse" && setOpen(false)}
    >
      <button
        type="button"
        onClick={() => {
          haptic("light");
          setOpen(true); // closes on a tap outside / when the mouse leaves
        }}
        className="relative block w-[84px] active:scale-95"
        aria-label={`Муза: ${active.name}`}
        aria-expanded={open}
      >
        <MuseArt muse={active} className="aspect-square w-full rounded-2xl shadow-[0_0_30px_-8px] shadow-pink-400/70" iconClass="text-4xl" />
        <MuseHeart state={museHeartState(data)} className="absolute -right-1.5 -top-1.5" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: 0.15 }}
            className="absolute right-0 top-full z-30 w-60 pt-2"
          >
            <MuseCard album={data} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function MuseCard({ album }: { album: MuseAlbum }) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const date = useMutation({
    mutationFn: startMuseDate,
    onSuccess: (today) => navigate(today.path),
    onError: (err) => setError(formatGameError(err, "Свидание не началось")),
  });
  const active = album.active!;
  const state = museHeartState(album);
  const button = "flex flex-1 items-center justify-center gap-1 rounded-full py-2 text-xs font-bold active:scale-95 disabled:opacity-50";

  return (
    <div className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-bg-raised p-3 text-left shadow-xl">
      <div>
        <p className="truncate font-display text-sm font-bold text-ink-chalk">{active.name}</p>
        <p className="text-caption text-accent-lime">{active.effect_label}</p>
        <p className={`text-caption font-semibold ${state === "bored" ? "text-amber-300" : "text-pink-200"}`}>{STATUS[state]}</p>
      </div>
      <div className="flex gap-2">
        <button type="button" onClick={() => navigate(`/muses?open=${active.id}`)} className={`${button} bg-white/10 text-ink-chalk`}>
          Профиль музы
        </button>
        {album.date.today?.completed ? (
          <span className={`${button} bg-white/5 font-semibold text-ink-mist`}>Свидание ✓</span>
        ) : (
          <button type="button" onClick={() => date.mutate()} disabled={date.isPending}
            className={`${button} bg-gradient-to-r from-pink-500 to-fuchsia-500 text-white`}>
            💞 Свидание
          </button>
        )}
      </div>
      {error && <p className="text-caption text-red-400">{error}</p>}
    </div>
  );
}
