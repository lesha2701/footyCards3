import { skipToken, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";

import { api } from "@/lib/api";
import { hapticNotify } from "@/lib/telegram";

interface PatronLetter {
  id: number;
  title: string;
  body: string;
}

/** A personal thank-you to a Stars supporter («Покровитель недели»,
 * «Преторианец», stars_patron_service): the bot sends it too, the game shows
 * it once as a letter. Waits for the other login popups. */
export default function StarsPatronLetter() {
  const queryClient = useQueryClient();
  const { data } = useQuery({
    queryKey: ["stars-patron-letters"],
    queryFn: async () => (await api.get<PatronLetter[]>("/stars-patron/letters")).data,
    staleTime: 60_000,
  });
  const { data: streak } = useQuery<unknown[]>({ queryKey: ["streak-rewards"], queryFn: skipToken });
  const { data: comeback } = useQuery<unknown[]>({ queryKey: ["comeback-gifts"], queryFn: skipToken });
  const seen = useMutation({
    mutationFn: (id: number) => api.post(`/stars-patron/letters/${id}/seen`),
    onMutate: (id) =>
      queryClient.setQueryData<PatronLetter[]>(["stars-patron-letters"], (old) => old?.filter((l) => l.id !== id)),
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: ["stars-patron-letters"] });
      void queryClient.invalidateQueries({ queryKey: ["profile"] });
    },
  });
  const letter = streak?.length || comeback?.length ? undefined : data?.[0];
  // «👑 Ты — …»: the leading emoji is the seal of the letter.
  const [seal, ...rest] = (letter?.title ?? "").split(" ");
  const sealed = !!seal && !/[A-Za-zА-Яа-яЁё0-9]/.test(seal);
  const title = sealed ? rest.join(" ") : letter?.title ?? "";

  return (
    <AnimatePresence>
      {letter && (
        <motion.div
          key={letter.id}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onAnimationComplete={() => hapticNotify("success")}
          className="fixed inset-0 z-[90] flex items-center justify-center bg-black/80 px-5 backdrop-blur-sm"
        >
          <motion.div
            initial={{ scale: 0.7, y: 40 }}
            animate={{ scale: 1, y: 0 }}
            transition={{ type: "spring", damping: 15, stiffness: 170 }}
            className="relative w-full max-w-sm overflow-hidden rounded-3xl bg-bg-surface p-6 text-center shadow-2xl ring-2 ring-amber-400/50"
          >
            <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-amber-400/20 to-transparent" />
            <motion.span
              initial={{ scale: 0.4, rotate: -12 }}
              animate={{ scale: [0.4, 1.2, 1], rotate: [-12, 8, 0] }}
              transition={{ duration: 0.7, delay: 0.15 }}
              className="relative mx-auto flex h-20 w-20 items-center justify-center rounded-3xl bg-amber-400/15 text-5xl ring-1 ring-amber-400/40"
            >
              {sealed ? seal : "⭐"}
            </motion.span>
            <p className="relative mt-3 font-mono text-micro uppercase tracking-wider text-amber-300">Личное письмо · VICTOR FC</p>
            <p className="relative mt-1 font-display text-xl font-bold leading-tight text-ink-chalk">{title}</p>
            <p className="relative mt-3 max-h-[45vh] overflow-y-auto whitespace-pre-line text-left text-sm leading-relaxed text-ink-mist">
              {letter.body}
            </p>
            <button
              onClick={() => seen.mutate(letter.id)}
              className="relative mt-5 w-full rounded-2xl bg-gradient-to-r from-amber-300 to-amber-500 py-3.5 font-display text-base font-bold text-bg-base active:scale-95"
            >
              Спасибо!
            </button>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
