import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimFreePack } from "@/api/freePack";
import {
  IconBrain,
  IconCollection,
  IconGift,
  IconPack,
  IconStadium,
  type IconProps,
} from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

type Slide = {
  Icon: (props: IconProps) => JSX.Element;
  title: string;
  text: string;
};

const SLIDES: Slide[] = [
  {
    Icon: IconPack,
    title: "Добро пожаловать в Victor FC!",
    text: "Собирай карточки футболистов, открывай паки и строй свою коллекцию мечты.",
  },
  {
    Icon: IconCollection,
    title: "Собирай и меняйся",
    text: "Смотри карточки в коллекции, продавай лишние и меняйся дубликатами с другими игроками.",
  },
  {
    Icon: IconBrain,
    title: "Играй и зарабатывай",
    text: "Memory Sequence, Пенальти, Штрафной, Футбольные буквы и Сапёр — проходи мини-игры и получай монеты.",
  },
  {
    Icon: IconStadium,
    title: "Card Arena",
    text: "Собери состав 4-3-3 из своих карточек и сражайся с командами других игроков за победы.",
  },
];

export default function OnboardingScreen({ onFinish }: { onFinish: () => void }) {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const queryClient = useQueryClient();

  const [step, setStep] = useState(0);
  const isLastSlide = step === SLIDES.length;

  const claimMutation = useMutation({
    mutationFn: claimFreePack,
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["free-pack-status"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      onFinish();
      navigate(`/packs/${data.pack.id}/open`, { state: { result: data } });
    },
  });

  const goNext = () => {
    haptic("light");
    setStep((s) => Math.min(s + 1, SLIDES.length));
  };

  const skip = () => {
    onFinish();
    navigate("/packs");
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-bg-base">
      <button
        onClick={skip}
        className="safe-top absolute right-4 top-4 z-10 rounded-full bg-white/10 px-4 py-2 text-xs font-semibold text-ink-chalk"
      >
        Пропустить
      </button>

      <div className="flex flex-1 flex-col">
        <AnimatePresence mode="wait">
          {!isLastSlide ? (
            <motion.div
              key={step}
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -24 }}
              transition={{ duration: 0.25 }}
              className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center"
            >
              <SlideIcon Icon={SLIDES[step].Icon} />
              <div className="space-y-2">
                <p className="font-display text-xl font-bold text-ink-chalk">{SLIDES[step].title}</p>
                <p className="text-sm text-ink-mist">{SLIDES[step].text}</p>
              </div>
            </motion.div>
          ) : (
            <motion.div
              key="cta"
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -24 }}
              transition={{ duration: 0.25 }}
              className="flex flex-1 flex-col items-center justify-center gap-6 px-8 text-center"
            >
              <SlideIcon Icon={IconGift} />
              <div className="space-y-2">
                <p className="font-display text-xl font-bold text-ink-chalk">Готов начать?</p>
                <p className="text-sm text-ink-mist">Забери свой первый бесплатный пак и начни собирать коллекцию!</p>
              </div>
              {claimMutation.isError && (
                <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
                  {formatGameError(claimMutation.error, "Не удалось получить пак")}
                </p>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <div className="safe-bottom flex flex-col items-center gap-4 px-6 pb-6 pt-2">
        <div className="flex items-center gap-1.5">
          {[...SLIDES, null].map((_, i) => (
            <span
              key={i}
              className={`h-1.5 rounded-full transition-all ${
                i === step ? "w-5 bg-floodlight" : "w-1.5 bg-white/15"
              }`}
            />
          ))}
        </div>

        {!isLastSlide ? (
          <button
            onClick={goNext}
            className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
          >
            Далее
          </button>
        ) : (
          <button
            onClick={() => claimMutation.mutate()}
            disabled={claimMutation.isPending}
            className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
          >
            {claimMutation.isPending ? "Открываем..." : "Открыть бесплатный пак"}
          </button>
        )}
      </div>
    </div>
  );
}

function SlideIcon({ Icon }: { Icon: (props: IconProps) => JSX.Element }) {
  return (
    <span className="flex h-20 w-20 items-center justify-center rounded-full bg-bg-surface text-accent-lime">
      <Icon size={36} />
    </span>
  );
}
