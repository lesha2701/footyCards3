import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { type ReactNode, useMemo, useState } from "react";
import { createPortal } from "react-dom";

import { fetchWeeklyTopAwards, markWeeklyTopSeen } from "@/api/weeklyTop";
import { IconCoin, IconPack } from "@/components/icons";
import { frameClass } from "@/lib/cosmetics";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { WeeklyTopAward } from "@/types";

const MEDAL: Record<number, { emoji: string; ring: string; glow: string }> = {
  1: { emoji: "🥇", ring: "from-amber-200 via-amber-400 to-amber-700", glow: "rgba(251,191,36,0.55)" },
  2: { emoji: "🥈", ring: "from-slate-100 via-slate-300 to-slate-500", glow: "rgba(226,232,240,0.45)" },
  3: { emoji: "🥉", ring: "from-orange-200 via-orange-400 to-amber-800", glow: "rgba(251,146,60,0.45)" },
};
const OTHER = { emoji: "🏆", ring: "from-emerald-200 via-lime-300 to-emerald-600", glow: "rgba(163,230,53,0.4)" };
const CONFETTI = ["#facc15", "#a3e635", "#38bdf8", "#f472b6", "#fb923c", "#ffffff"];

/** «Топ недели»: one celebratory popup per ranking the player placed in
 * last week, best places first. Rewards are already granted on the
 * backend; «Забрать» only marks the popup as seen. */
export default function WeeklyTopAwardModal() {
  const user = useAuthStore((s) => s.user);
  const queryClient = useQueryClient();
  const { data: awards } = useQuery({
    queryKey: ["weekly-top-awards"], queryFn: fetchWeeklyTopAwards, enabled: !!user, staleTime: Infinity,
  });
  const [done, setDone] = useState<number[]>([]);
  const queue = (awards ?? []).filter((a) => !done.includes(a.id));
  const current = queue[0];
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const seen = useMutation({
    mutationFn: (id: number) => markWeeklyTopSeen([id]),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ["profile"] }),
  });

  const collect = () => {
    if (!current) return;
    hapticNotify("success");
    updateBalance(current.balance);
    seen.mutate(current.id);
    setDone((d) => [...d, current.id]);
  };

  return createPortal(
    <AnimatePresence mode="wait">
      {current && (
        <AwardCard
          key={current.id}
          award={current}
          position={(awards?.length ?? 0) - queue.length + 1}
          total={awards?.length ?? 0}
          onCollect={collect}
        />
      )}
    </AnimatePresence>,
    document.body,
  );
}

function AwardCard({ award, position, total, onCollect }: {
  award: WeeklyTopAward; position: number; total: number; onCollect: () => void;
}) {
  const medal = MEDAL[award.rank] ?? OTHER;
  const frame = frameClass(award.cosmetic_style);
  const pieces = useMemo(
    () => Array.from({ length: 26 }, (_, i) => ({
      x: (Math.random() - 0.5) * 340, y: -120 - Math.random() * 260, r: Math.random() * 540 - 270,
      color: CONFETTI[i % CONFETTI.length], delay: 0.25 + Math.random() * 0.25, w: 6 + Math.random() * 6,
    })),
    [],
  );

  return (
    <motion.div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-black/75 px-5 backdrop-blur-sm"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div
        className="relative w-full max-w-sm overflow-hidden rounded-3xl border border-white/10 bg-bg-surface px-6 pb-6 pt-8 text-center"
        initial={{ y: 60, scale: 0.9, opacity: 0 }}
        animate={{ y: 0, scale: 1, opacity: 1 }}
        exit={{ y: -40, scale: 0.95, opacity: 0 }}
        transition={{ type: "spring", damping: 20, stiffness: 260 }}
      >
        {total > 1 && (
          <span className="absolute right-4 top-3 rounded-full bg-white/10 px-2 py-0.5 font-mono text-micro text-ink-mist">
            {position} / {total}
          </span>
        )}

        {/* Light rays + the medal popping in, confetti bursting out of it. */}
        <div className="relative mx-auto flex h-40 w-40 items-center justify-center">
          <motion.div
            className="absolute inset-[-45%] rounded-full opacity-70"
            style={{
              background: `repeating-conic-gradient(${medal.glow} 0deg 6deg, transparent 6deg 24deg)`,
              maskImage: "radial-gradient(circle, black 20%, transparent 68%)",
              WebkitMaskImage: "radial-gradient(circle, black 20%, transparent 68%)",
            }}
            animate={{ rotate: 360 }}
            transition={{ duration: 14, repeat: Infinity, ease: "linear" }}
            aria-hidden
          />
          <motion.div
            className="absolute inset-0 rounded-full"
            style={{ background: `radial-gradient(circle, ${medal.glow}, transparent 70%)` }}
            animate={{ scale: [1, 1.12, 1] }}
            transition={{ duration: 2.2, repeat: Infinity }}
            aria-hidden
          />
          <motion.div
            className={`relative flex h-28 w-28 items-center justify-center rounded-full bg-gradient-to-br p-1 ${medal.ring}`}
            initial={{ scale: 0, rotate: -160 }}
            animate={{ scale: 1, rotate: 0 }}
            transition={{ type: "spring", damping: 10, stiffness: 160, delay: 0.1 }}
          >
            <span className="flex h-full w-full flex-col items-center justify-center rounded-full bg-bg-base/80">
              <span className="text-5xl leading-none">{medal.emoji}</span>
              <span className="mt-1 font-display text-lg font-black text-ink-chalk">#{award.rank}</span>
            </span>
          </motion.div>
          {pieces.map((p, i) => (
            <motion.span
              key={i}
              className="absolute left-1/2 top-1/2 rounded-sm"
              style={{ width: p.w, height: p.w * 0.45, background: p.color }}
              initial={{ x: 0, y: 0, opacity: 0, rotate: 0 }}
              animate={{ x: p.x, y: [0, p.y, p.y + 320], opacity: [0, 1, 0], rotate: p.r }}
              transition={{ duration: 1.8, delay: p.delay, ease: "easeOut" }}
              aria-hidden
            />
          ))}
        </div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.35 }}>
          <p className="mt-2 text-micro font-semibold uppercase tracking-widest text-accent-lime">Топ недели</p>
          <p className="mt-1 font-display text-2xl font-black text-ink-chalk">{award.rank}-е место!</p>
          <p className="mt-1 text-sm text-ink-mist">
            «{award.metric_label}» · <span className="font-mono text-ink-chalk">{award.value.toLocaleString("ru-RU")}</span>
          </p>
        </motion.div>

        <motion.div
          className="mt-5 flex flex-col gap-2"
          initial="hidden"
          animate="shown"
          variants={{ shown: { transition: { staggerChildren: 0.12, delayChildren: 0.55 } } }}
        >
          {award.coins > 0 && (
            <Reward>
              <IconCoin size={18} className="text-accent-lime" />
              <span className="font-mono text-base font-bold text-accent-lime">+{award.coins.toLocaleString("ru-RU")}</span>
            </Reward>
          )}
          {award.pack_name && (
            <Reward>
              <IconPack size={18} className="text-accent-cyan" />
              <span className="text-sm font-semibold text-ink-chalk">
                {award.pack_name}{award.cards ? ` · ${award.cards} карт в коллекции` : ""}
              </span>
            </Reward>
          )}
          {award.cosmetic_name && (
            <Reward>
              <span className={`h-6 w-6 rounded-full p-[3px] ${frame ?? "bg-white/20"}`}>
                <span className="block h-full w-full rounded-full bg-bg-surface" />
              </span>
              <span className="text-sm font-semibold text-ink-chalk">Рамка «{award.cosmetic_name}»</span>
            </Reward>
          )}
        </motion.div>

        <button
          onClick={onCollect}
          className="mt-6 w-full rounded-2xl bg-floodlight py-3 font-display text-base font-black text-bg-base active:scale-95"
        >
          {position < total ? "Забрать и дальше" : "Забрать"}
        </button>
      </motion.div>
    </motion.div>
  );
}

function Reward({ children }: { children: ReactNode }) {
  return (
    <motion.div
      className="flex items-center justify-center gap-2 rounded-xl bg-bg-raised px-3 py-2.5"
      variants={{ hidden: { opacity: 0, scale: 0.8 }, shown: { opacity: 1, scale: 1 } }}
    >
      {children}
    </motion.div>
  );
}
