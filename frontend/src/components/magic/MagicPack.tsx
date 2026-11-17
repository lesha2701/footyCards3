import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Backdrop } from "@/components/magic/Backdrop";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { buyMagicCreaturePack, fetchMagicHub, magicCreaturePackInvoice } from "@/api/magic";
import { IconCoin } from "@/components/icons";
import { uiArt } from "@/components/magic/art/pngArt";
import CreatureCard from "@/components/magic/CreatureCard";
import { RACE, ROMAN } from "@/components/magic/magicMeta";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { MagicCreature, MagicHub } from "@/types";


/** The «Магический пак» offer: coins or Stars, then the reveal. `look` — "hero": the big
 *  card on top of the mode and in the shop; "strip": one slim row. */
export function MagicPackOffer({ hub, look = "hero", note }: { hub: MagicHub; look?: "hero" | "strip"; note?: string }) {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [error, setError] = useState<string | null>(null);
  const [opened, setOpened] = useState<MagicCreature[] | null>(null);
  const [paying, setPaying] = useState(false);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["magic-hub"] });
  const coins = useMutation({
    mutationFn: buyMagicCreaturePack,
    onSuccess: (r) => { updateBalance(r.balance); hapticNotify("success"); setOpened(r.cards); refresh(); },
    onError: (e) => setError(formatGameError(e, "Не получилось купить пак")),
  });
  const stars = async () => {
    setPaying(true);
    setError(null);
    try {
      if ((await payShopWithStars(magicCreaturePackInvoice)) === "paid") {
        hapticNotify("success");
        const fresh = await queryClient.fetchQuery({ queryKey: ["magic-hub"], queryFn: fetchMagicHub });
        setOpened(fresh.last_pack ?? null);
      }
    } catch (e) {
      setError(formatGameError(e, "Покупка не прошла"));
    } finally {
      setPaying(false);
    }
  };
  const pack = hub.creature_pack;
  if (!pack) return null;
  const art = uiArt("magic_pack");
  const buttons = (
    <div className="grid grid-cols-2 gap-1.5">
      {pack.coins !== null && (
        <button disabled={coins.isPending} onClick={() => { setError(null); coins.mutate(); }}
          className="flex items-center justify-center gap-1 rounded-xl bg-amber-400 py-2 text-xs font-black text-black shadow-[0_0_14px_rgba(251,191,36,0.35)] active:scale-95 disabled:opacity-40">
          {coins.isPending ? "…" : <>{pack.coins} <IconCoin size={12} /></>}
        </button>
      )}
      {pack.stars !== null && (
        <button disabled={paying} onClick={stars}
          className="rounded-xl bg-gradient-to-r from-sky-400 to-indigo-500 py-2 text-xs font-black text-white active:scale-95 disabled:opacity-40">
          {pack.stars} ⭐
        </button>
      )}
    </div>
  );
  return (
    <>
      {look === "strip" ? (
        <div className="flex items-center gap-2.5 rounded-2xl bg-gradient-to-r from-purple-700/45 via-indigo-700/30 to-amber-500/20 p-2 pr-2.5 ring-1 ring-purple-300/30">
          {art && <img src={art} alt="" className="-my-1 h-14 w-auto shrink-0 drop-shadow-[0_0_10px_rgba(192,132,252,0.6)]" />}
          <div className="min-w-0 flex-1">
            <p className="font-display text-sm font-black leading-tight text-ink-chalk">✨ Магический пак</p>
            <p className="truncate text-[10px] text-ink-mist">{note ?? `${pack.size} карт существ — из них собирается армия`}</p>
          </div>
          <div className="w-[118px] shrink-0">{buttons}</div>
        </div>
      ) : (
        <section className="relative overflow-hidden rounded-3xl p-3 ring-1 ring-purple-300/30"
          style={{ background: "radial-gradient(circle at 18% 40%, rgba(192,132,252,0.45), transparent 55%), radial-gradient(circle at 90% 0%, rgba(251,191,36,0.22), transparent 45%), linear-gradient(150deg, #2e1065 0%, #1e1b4b 55%, #0f172a 100%)" }}>
          <div className="flex gap-3">
            {art && (
              // Static: a looping transform under a drop-shadow flickers in phone webviews.
              <img src={art} alt="" className="h-32 w-auto shrink-0 drop-shadow-[0_0_18px_rgba(192,132,252,0.7)]" />
            )}
            <div className="flex min-w-0 flex-1 flex-col">
              <p className="font-display text-lg font-black leading-tight text-ink-chalk">✨ Магический пак</p>
              <p className="mt-0.5 text-[11px] leading-snug text-ink-mist">
                {note ?? `${pack.size} карт существ всех рас. Из них ты собираешь армию героя.`}
              </p>
              <div className="mt-1.5 flex flex-wrap gap-1">
                {[1, 2, 3, 4, 5].filter((t) => pack.odds[t]).map((t) => (
                  <span key={t} className="rounded-full bg-black/35 px-1.5 py-0.5 font-mono text-[9px] text-indigo-100">
                    {ROMAN[t]} {pack.odds[t]}%
                  </span>
                ))}
              </div>
              <div className="mt-auto pt-2">{buttons}</div>
            </div>
          </div>
        </section>
      )}
      {error && <p className="text-micro text-red-400">{error}</p>}
      <AnimatePresence>{opened && <PackReveal cards={opened} onClose={() => setOpened(null)} />}</AnimatePresence>
    </>
  );
}

const TIER_WORD = ["", "обычная", "редкая", "эпическая", "легендарная", "диамант"];

/** A fresh pack: one big card at a time (tap — the next), or «Пропустить» — all of them at once. */
export function PackReveal({ cards, onClose }: { cards: MagicCreature[]; onClose: () => void }) {
  const [i, setI] = useState(-1); // -1: the closed pack; cards.length: the summary
  const done = i >= cards.length;
  const next = () => setI((v) => Math.min(cards.length, v + 1));
  const c = i >= 0 && !done ? cards[i] : null;
  return (
    <Backdrop onClick={done ? onClose : next}
      className="fixed inset-0 z-[70] flex flex-col items-center justify-center bg-black/90 px-6">
      {!done && (
        <button onClick={(e) => { e.stopPropagation(); setI(cards.length); }}
          className="absolute right-4 top-[max(1rem,env(safe-area-inset-top))] rounded-full bg-white/15 px-3 py-1.5 text-xs font-bold text-white active:scale-95">
          Пропустить ⏭
        </button>
      )}
      {i === -1 && (
        <>
          <motion.img src={uiArt("magic_pack") ?? undefined} alt="" className="w-56 drop-shadow-[0_0_40px_rgba(192,132,252,0.7)]"
            initial={{ scale: 0.85, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ duration: 0.35 }} />
          <p className="mt-4 font-display text-lg font-black text-amber-200">Нажми, чтобы открыть</p>
        </>
      )}
      {c && (
        <div key={i} className="flex flex-col items-center [perspective:1000px]">
          <div className="w-56"><CreatureCard c={c} reveal delay={0.05} /></div>
          <motion.p initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }}
            className="mt-4 font-display text-xl font-black text-ink-chalk">{c.name}</motion.p>
          <p className="text-caption text-ink-mist">{ROMAN[c.tier]} · {TIER_WORD[c.tier]} · {RACE[c.faction] ?? ""} · ×{c.fighters} бойцов</p>
          <p className="mt-4 font-mono text-micro text-ink-mist-dim">{i + 1} / {cards.length} · нажми — следующая</p>
        </div>
      )}
      {done && (
        <>
          <p className="mb-3 font-display text-xl font-black text-amber-200">✨ В паке</p>
          <div className="grid w-full max-w-xs grid-cols-3 gap-2">
            {cards.map((x, k) => <CreatureCard key={k} c={x} delay={k * 0.06} />)}
          </div>
          <p className="mt-5 text-caption text-ink-mist">Нажми, чтобы закрыть</p>
        </>
      )}
    </Backdrop>
  );
}
