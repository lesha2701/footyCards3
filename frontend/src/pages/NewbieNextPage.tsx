import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { fetchNewbie, openNewbieSquadPack } from "@/api/newbie";
import LoadingScreen from "@/components/common/LoadingScreen";
import { IconStadium, IconUsers } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { RARITY_LABELS, RARITY_TEXT } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

/** The «Путь дебютанта» first session in one go: after the debut pack (or
 * the link's game) comes the team pack, then the first Arena match — each
 * from a full screen of its own, without a stop on home, where half the new
 * players used to leave. */
export default function NewbieNextPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: state, isError } = useQuery({ queryKey: ["newbie"], queryFn: fetchNewbie });

  const squad = useMutation({
    mutationFn: openNewbieSquadPack,
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["newbie"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      queryClient.invalidateQueries({ queryKey: ["lineup"] });
      navigate(`/packs/${data.pack.id}/open`, { replace: true, state: { result: data, returnTo: "/newbie/next" } });
    },
  });

  const step = !state?.active || !state.first_pack_done ? null : !state.squad_pack_done ? "squad" : !state.arena_played ? "arena" : null;
  const nothingLeft = isError || (!!state && step === null);
  useEffect(() => {
    if (nothingLeft) navigate("/", { replace: true });
  }, [nothingLeft, navigate]);
  if (!state || !step) return <LoadingScreen />;

  const rarity = state.arena_rarity;
  const Icon = step === "squad" ? IconUsers : IconStadium;
  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg-base">
      <div className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center">
        <p className="font-mono text-micro uppercase tracking-wider text-accent-lime">
          Шаг {step === "squad" ? 2 : 3} из 3
        </p>
        <motion.span
          key={step}
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: [0.6, 1.08, 1], opacity: 1 }}
          transition={{ duration: 0.7 }}
          className="flex h-28 w-28 items-center justify-center rounded-[2rem] bg-bg-surface text-accent-lime shadow-[0_0_60px_-10px_rgba(190,242,100,0.5)]"
        >
          <Icon size={56} />
        </motion.span>
        {step === "squad" ? (
          <div className="space-y-2">
            <p className="font-display text-2xl font-bold text-ink-chalk">Теперь — целая команда</p>
            <p className="text-sm text-ink-mist">
              {state.squad_size} игроков на все позиции. Состав соберётся сам — и сразу в первый матч.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="font-display text-2xl font-bold text-ink-chalk">Команда готова к матчу</p>
            <p className="text-sm text-ink-mist">
              Сыграй первый матч в Card Arena
              {rarity && (
                <>
                  {" "}— за него <span className={`font-bold ${RARITY_TEXT[rarity]}`}>{RARITY_LABELS[rarity].toLowerCase()} карта</span>
                </>
              )}
              .
            </p>
          </div>
        )}
        {squad.isError && (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(squad.error, "Не удалось открыть пак")}
          </p>
        )}
      </div>
      <div className="safe-bottom space-y-1 px-6 pb-6 pt-2">
        <button
          onClick={() => {
            haptic("medium");
            if (step === "squad") squad.mutate();
            else navigate("/play/arena", { replace: true });
          }}
          disabled={squad.isPending}
          className="animate-claim-glow w-full rounded-2xl bg-floodlight px-4 py-4 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {squad.isPending ? "Открываем..." : step === "squad" ? "Получить команду" : "Сыграть первый матч"}
        </button>
        <button onClick={() => navigate("/", { replace: true })} className="w-full py-2 text-xs font-semibold text-ink-mist-dim">
          Позже
        </button>
      </div>
    </div>
  );
}
