import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { fetchNewbie, openNewbieFirstPack } from "@/api/newbie";
import LoadingScreen from "@/components/common/LoadingScreen";
import OnboardingScreen from "@/components/common/OnboardingScreen";
import stadium from "@/assets/newbie/welcome-stadium.webp";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { takeStartPath } from "@/lib/startLink";
import { RARITY_LABELS, RARITY_TEXT } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

/** The very first screen of a new player: one tap and the «Пак дебютанта»
 * opens — value before any explanation. Players outside the «Путь дебютанта»
 * get the old slides. */
export default function NewbieWelcome({ onFinish }: { onFinish: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: state, isError } = useQuery({ queryKey: ["newbie"], queryFn: fetchNewbie });

  const open = useMutation({
    mutationFn: openNewbieFirstPack,
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["newbie"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      // takeStartPath before onFinish: the link's game comes after the pack;
      // otherwise straight on to the team pack and the first match.
      const returnTo = takeStartPath() ?? "/newbie/next";
      onFinish();
      navigate(`/packs/${data.pack.id}/open`, { state: { result: data, returnTo } });
    },
  });

  // Already opened it (another device, a reload): nothing to welcome to.
  const done = !!state?.active && state.first_pack_done;
  useEffect(() => {
    if (done) onFinish();
  }, [done, onFinish]);

  if (isError || (state && !state.active)) return <OnboardingScreen onFinish={onFinish} />;
  if (!state || done) return <LoadingScreen />;

  const top = state.first_pack_top;
  return (
    <div className="fixed inset-0 z-50 flex flex-col overflow-hidden bg-bg-base">
      {/* A night stadium under the floodlights, darkened towards the text. */}
      <img src={stadium} alt="" aria-hidden="true" className="absolute inset-0 h-full w-full object-cover" />
      <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-b from-black/30 via-black/20 to-bg-base" />
      <div aria-hidden="true" className="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-bg-base via-bg-base/90 to-transparent" />

      <div className="safe-top relative flex items-center justify-center gap-2 pt-5">
        <img src="/brand/victor-fc-crest.jpg" alt="" className="h-8 w-8 rounded-full ring-1 ring-white/20" />
        <span className="font-display text-sm font-bold tracking-wide text-ink-chalk drop-shadow">
          VICTOR <span className="text-accent-lime">FC</span>
        </span>
      </div>

      <div className="relative flex flex-1 flex-col items-center justify-center gap-5 px-8 text-center">
        <DebutPack opening={open.isPending} />
        <div className="space-y-2">
          <p className="font-mono text-micro uppercase tracking-[0.2em] text-accent-lime/90">Добро пожаловать в клуб</p>
          <p className="font-display text-2xl font-black leading-tight text-ink-chalk drop-shadow-[0_2px_12px_rgba(0,0,0,0.8)]">
            Твой первый пак уже&nbsp;ждёт
          </p>
          {top && (
            <p className="text-sm text-ink-mist">
              Внутри гарантированно <span className={`font-bold ${RARITY_TEXT[top]}`}>{RARITY_LABELS[top].toLowerCase()}</span> карта.
              <br />
              Дальше — целая команда и первый матч.
            </p>
          )}
        </div>
        {open.isError && (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(open.error, "Не удалось открыть пак")}
          </p>
        )}
      </div>
      <div className="safe-bottom relative px-6 pb-6 pt-2">
        <button
          onClick={() => {
            haptic("medium");
            open.mutate();
          }}
          disabled={open.isPending}
          className="animate-claim-glow w-full rounded-2xl bg-floodlight py-4 font-display text-lg font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {open.isPending ? "Открываем..." : "Открыть пак"}
        </button>
      </div>
    </div>
  );
}

/** «Пак дебютанта» floating in the light: slow rays behind, a soft lime
 * glow, a gentle hover — and a shake while it opens. */
function DebutPack({ opening }: { opening: boolean }) {
  const reduce = useReducedMotion();
  return (
    <div className="relative flex h-64 w-64 items-center justify-center">
      <motion.div
        aria-hidden="true"
        className="absolute inset-[-30%] rounded-full opacity-60"
        style={{
          background:
            "repeating-conic-gradient(from 0deg, rgba(198,230,58,0.22) 0deg 6deg, transparent 6deg 22deg)",
          maskImage: "radial-gradient(circle, black 20%, transparent 68%)",
          WebkitMaskImage: "radial-gradient(circle, black 20%, transparent 68%)",
        }}
        animate={reduce ? undefined : { rotate: 360 }}
        transition={{ duration: 40, repeat: Infinity, ease: "linear" }}
      />
      <div aria-hidden="true" className="absolute h-44 w-44 rounded-full bg-accent-lime/30 blur-3xl" />
      <motion.img
        src={staticUrl("packs/debut.webp")}
        alt="Пак дебютанта"
        className="relative h-60 w-auto drop-shadow-[0_18px_30px_rgba(0,0,0,0.7)]"
        initial={{ scale: 0.6, opacity: 0, y: 30 }}
        animate={
          opening
            ? { scale: 1.06, opacity: 1, y: 0, rotate: [0, -4, 4, -4, 4, 0] }
            : reduce
              ? { scale: 1, opacity: 1, y: 0 }
              : { scale: 1, opacity: 1, y: [0, -8, 0] }
        }
        transition={
          opening
            ? { duration: 0.5, repeat: Infinity }
            : { scale: { duration: 0.6 }, opacity: { duration: 0.6 }, y: { duration: 3.2, repeat: Infinity, ease: "easeInOut" } }
        }
      />
    </div>
  );
}
