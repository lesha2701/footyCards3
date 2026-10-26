import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { type RefObject, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { autoFillLineupTemplate } from "@/api/lineups";
import { fetchNewbie, openNewbieArenaCard } from "@/api/newbie";
import { IconGift, IconParty, IconTrophy } from "@/components/icons";
import NewbiePopup from "@/components/newbie/NewbiePopup";
import { formatGameError } from "@/lib/errors";
import { arenaStage, setArenaStage } from "@/lib/newbieGuide";
import { RARITY_LABELS } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Match } from "@/types";

type Target = "pitch" | "tactics" | "play";

const TOUR: { target: Target; title: string; text: string; cta: string }[] = [
  {
    target: "pitch",
    title: "Это твой состав",
    text: "Мы уже расставили игроков из «Твоей команды» по позициям 4-3-3. Позже сможешь менять их тапом по карточке.",
    cta: "Дальше",
  },
  {
    target: "tactics",
    title: "Выбери стиль игры",
    text: "Стили бьют друг друга по кругу. Выбери любой — для первого матча подойдёт «Атака».",
    cta: "Дальше",
  },
  {
    target: "play",
    title: "Жми «Играть матч»",
    text: "Матч идёт сам, а в опасных моментах ты решаешь: бить, пасовать или обводить.",
    cta: "Понятно",
  },
];

/** «Путь дебютанта» on Card Arena: a three-step tour before the first match,
 * the legendary card right after it, a popup to put the card in the squad
 * and test it, and a «well done → tasks» popup after that match. */
export default function ArenaNewbieGuide({
  targets, activeIndex, simulating, finished,
}: {
  targets: Record<Target, RefObject<HTMLElement>>;
  activeIndex: number;
  simulating: boolean;
  /** The match that just finished playing out on screen. */
  finished: Match | null;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id ?? 0);
  const { data: state } = useQuery({ queryKey: ["newbie"], queryFn: fetchNewbie });
  const [stage, setStage] = useState(() => arenaStage(userId));
  const [tourStep, setTourStep] = useState(0);
  const [tourClosed, setTourClosed] = useState(false);
  const [popup, setPopup] = useState<null | "card" | "legend" | "victory">(null);
  const [result, setResult] = useState<Match | null>(null);

  const move = (next: typeof stage) => {
    setArenaStage(userId, next);
    setStage(next);
  };

  const active = !!state?.active;
  const tourOn = active && !state.arena_played && !tourClosed && !simulating && !popup;
  const testHint = active && stage.step === "test" && !simulating && !popup;
  const highlighted: Target | null = tourOn ? TOUR[tourStep].target : testHint ? "play" : null;

  // Highlight the element the current hint talks about.
  useEffect(() => {
    const el = highlighted ? targets[highlighted].current : null;
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    el.classList.add("newbie-spotlight");
    return () => el.classList.remove("newbie-spotlight");
  }, [highlighted, targets]);

  // The match is over on screen: what comes next on the path.
  useEffect(() => {
    if (!finished || !state?.active) return;
    setTourClosed(true);
    setResult(finished);
    if (!state.arena_claimed) {
      const t = setTimeout(() => setPopup("card"), 1200);
      return () => clearTimeout(t);
    }
    if (stage.step === "test") {
      const t = setTimeout(() => setPopup("victory"), 1200);
      return () => clearTimeout(t);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [finished?.id]);

  // Back from the card reveal.
  useEffect(() => {
    if (stage.step === "card" && state?.arena_claimed) setPopup("legend");
  }, [stage.step, state?.arena_claimed]);

  const openCard = useMutation({
    mutationFn: openNewbieArenaCard,
    onSuccess: (data) => {
      hapticNotify("success");
      const card = data.cards[0]?.card;
      move({ step: "card", cardName: card ? `${card.player.display_name}` : "", rarity: card?.player.rarity });
      queryClient.invalidateQueries({ queryKey: ["newbie"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      setPopup(null);
      navigate(`/packs/${data.pack.id}/open`, { state: { result: data, returnTo: "/play/arena" } });
    },
  });
  const putInSquad = useMutation({
    mutationFn: () => autoFillLineupTemplate(activeIndex),
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["lineup-templates"] });
      queryClient.invalidateQueries({ queryKey: ["arena-opponent"] });
      move({ ...stage, step: "test" });
      setPopup(null);
    },
  });

  const score = result ? `${result.user_score}:${result.opponent_score}` : "";
  const won = result?.result === "win";

  return (
    <>
      <AnimatePresence>
        {(tourOn || testHint) && (
          <motion.div
            key={tourOn ? tourStep : "test"}
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -12 }}
            className="fixed inset-x-4 top-[calc(4.5rem+env(safe-area-inset-top,0px))] z-[60] mx-auto max-w-sm rounded-2xl bg-bg-surface p-3.5 shadow-2xl ring-1 ring-accent-lime/40"
          >
            {tourOn ? (
              <>
                <div className="mb-1 flex items-center justify-between">
                  <p className="font-display text-base font-bold text-ink-chalk">{TOUR[tourStep].title}</p>
                  <span className="font-mono text-micro text-ink-mist">{tourStep + 1}/{TOUR.length}</span>
                </div>
                <p className="text-xs leading-snug text-ink-mist">{TOUR[tourStep].text}</p>
                <button
                  onClick={() => {
                    haptic("light");
                    if (tourStep < TOUR.length - 1) setTourStep(tourStep + 1);
                    else setTourClosed(true);
                  }}
                  className="mt-2.5 w-full rounded-xl bg-floodlight py-2.5 font-display text-sm font-bold text-bg-base active:scale-95"
                >
                  {TOUR[tourStep].cta}
                </button>
              </>
            ) : (
              <>
                <p className="font-display text-base font-bold text-ink-chalk">Жми «Играть матч»</p>
                <p className="mt-0.5 text-xs leading-snug text-ink-mist">
                  {stage.cardName ? `${stage.cardName} уже в составе — ` : ""}посмотрим новую легендарку в деле!
                </p>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      <NewbiePopup
        open={popup === "card"}
        Icon={IconGift}
        kicker={won ? `Победа ${score}!` : `Матч сыгран · ${score}`}
        title="Поздравляем, ты сыграл свой первый матч!"
        text={
          <>
            Держи заслуженную награду —{" "}
            <b className="text-rarity-legendary">
              {state?.arena_rarity ? RARITY_LABELS[state.arena_rarity].toLowerCase() : "новая"} карту
            </b>
            .
          </>
        }
        cta="Открыть карту"
        onCta={() => openCard.mutate()}
        busy={openCard.isPending}
        error={openCard.error ? formatGameError(openCard.error, "Не удалось открыть карту") : null}
      />
      <NewbiePopup
        open={popup === "legend"}
        Icon={IconParty}
        kicker="Ура!"
        title={`У тебя новая ${stage.rarity ? RARITY_LABELS[stage.rarity].toLowerCase() : ""} карта`}
        text={
          <>
            {stage.cardName && <b className="text-ink-chalk">{stage.cardName}</b>} — давай поставим её в состав и затестим в
            матче!
          </>
        }
        cta="Поставить в состав"
        onCta={() => putInSquad.mutate()}
        busy={putInSquad.isPending}
      />
      <NewbiePopup
        open={popup === "victory"}
        Icon={IconTrophy}
        kicker={won ? `Победа ${score}!` : `Матч сыгран · ${score}`}
        title={won ? "Поздравляем с победой!" : "Отличная игра!"}
        text="Продолжай в том же духе. На главной ждут задания — за каждое сразу награда."
        cta="К заданиям"
        onCta={() => {
          move({ ...stage, step: "done" });
          setPopup(null);
          navigate("/");
        }}
      />
    </>
  );
}
