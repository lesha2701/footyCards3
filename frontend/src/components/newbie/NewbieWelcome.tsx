import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { fetchNewbie, openNewbieFirstPack } from "@/api/newbie";
import LoadingScreen from "@/components/common/LoadingScreen";
import OnboardingScreen from "@/components/common/OnboardingScreen";
import { IconPack } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
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
      onFinish();
      navigate(`/packs/${data.pack.id}/open`, { state: { result: data, returnTo: "/" } });
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
    <div className="fixed inset-0 z-50 flex flex-col bg-bg-base">
      <div className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center">
        <motion.span
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: [0.6, 1.08, 1], opacity: 1, rotate: [0, -3, 3, 0] }}
          transition={{ duration: 0.8 }}
          className="flex h-28 w-28 items-center justify-center rounded-[2rem] bg-bg-surface text-accent-lime shadow-[0_0_60px_-10px_rgba(190,242,100,0.5)]"
        >
          <IconPack size={56} />
        </motion.span>
        <div className="space-y-2">
          <p className="font-mono text-micro uppercase tracking-wider text-ink-mist">Добро пожаловать в Victor FC</p>
          <p className="font-display text-2xl font-bold text-ink-chalk">Твой первый пак уже ждёт</p>
          {top && (
            <p className="text-sm text-ink-mist">
              Внутри гарантированно <span className={`font-bold ${RARITY_TEXT[top]}`}>{RARITY_LABELS[top].toLowerCase()}</span> карта.
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
      <div className="safe-bottom px-6 pb-6 pt-2">
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
