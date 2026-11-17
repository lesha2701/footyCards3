import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { createPortal } from "react-dom";

import { createStreakSaveInvoice, restoreStreakFree } from "@/api/loyalty";
import PlayerCard from "@/components/cards/PlayerCard";
import { IconChevronRight } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { milestonePct, saveDeadline, useLoyaltyStatus } from "@/lib/loyalty";
import { RARITY_LABELS } from "@/lib/rarity";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import type { LoyaltyStatus } from "@/types";

/** «Путь к Центуриону» on the home screen: days in a row towards the
 *  exclusive Beckenbauer card, the 30/60 steps — and, first of all, the
 *  «Страховка серии» offer when one missed day broke a long streak. */
export default function CenturionPath() {
  const { data } = useLoyaltyStatus();
  const [open, setOpen] = useState(false);
  if (!data?.enabled) return null;
  const save = data.streak_save;
  if (!save && (data.centurion_owned || !data.centurion)) return null;

  return (
    <>
      {save && <StreakSaveCard status={data} />}
      {!data.centurion_owned && data.centurion && (
        <button
          onClick={() => setOpen(true)}
          className="centurion-sky relative flex flex-col gap-2.5 overflow-hidden rounded-3xl p-4 text-left ring-1 ring-fuchsia-300/30 active:scale-[0.98]"
        >
          <span className="flex items-start justify-between gap-2">
            <span>
              <span className="block font-display text-[16px] font-black uppercase leading-tight tracking-wide text-fuchsia-100">
                Путь к Центуриону
              </span>
              <span className="mt-0.5 block text-xs text-white/75">
                {data.goal} дней подряд — эксклюзивный {data.centurion.display_name.split(" · ")[0]}
              </span>
            </span>
            <span className="flex shrink-0 items-center gap-1 whitespace-nowrap font-display text-lg font-black text-fuchsia-100">
              🔥 {Math.min(data.streak, data.goal)}
              <span className="text-xs font-bold text-white/60">/{data.goal}</span>
              <IconChevronRight size={18} className="text-white/80" />
            </span>
          </span>
          <PathBar status={data} />
        </button>
      )}
      {open && <CenturionSheet status={data} onClose={() => setOpen(false)} />}
    </>
  );
}

function PathBar({ status }: { status: LoyaltyStatus }) {
  const pct = milestonePct(status.streak, status.goal);
  return (
    <span className="relative mb-4 mt-1 block h-2.5 rounded-full bg-white/10">
      <span
        className="block h-full rounded-full bg-gradient-to-r from-fuchsia-400 via-violet-400 to-amber-300"
        style={{ width: `${pct}%` }}
      />
      {status.milestones.map((m) => (
        <span
          key={m.days}
          className="absolute top-1/2 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center"
          style={{ left: `${milestonePct(m.days, status.goal)}%` }}
        >
          <span
            className={`block h-4 w-4 rounded-full border-2 ${
              m.reached || status.streak >= m.days ? "border-amber-200 bg-amber-300" : "border-white/40 bg-bg-base"
            } ${m.exclusive ? "h-5 w-5 border-fuchsia-200" : ""}`}
          />
          <span className="absolute top-5 whitespace-nowrap font-mono text-[10px] text-white/70">
            {m.exclusive ? "💜" : ""}
            {m.days}
          </span>
        </span>
      ))}
    </span>
  );
}

function StreakSaveCard({ status }: { status: LoyaltyStatus }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const save = status.streak_save!;
  const done = () => {
    hapticNotify("success");
    queryClient.invalidateQueries({ queryKey: ["loyalty-status"] });
    queryClient.invalidateQueries({ queryKey: ["profile", "me"] });
  };
  const free = useMutation({
    mutationFn: restoreStreakFree,
    onSuccess: done,
    onError: (err) => setError(formatGameError(err, "Не получилось вернуть серию")),
  });
  const stars = useMutation({
    mutationFn: () => payShopWithStars(createStreakSaveInvoice),
    onSuccess: (result) => result === "paid" && done(),
    onError: (err) => setError(formatGameError(err, "Оплата не прошла")),
  });
  const busy = free.isPending || stars.isPending;

  return (
    <div className="rounded-3xl bg-gradient-to-br from-rose-600/40 via-orange-600/25 to-bg-surface p-4 ring-1 ring-rose-300/40">
      <p className="font-display text-[16px] font-black leading-tight text-rose-50">
        💔 Серия {save.saved_streak} дней прервалась
      </p>
      <p className="mt-1 text-xs text-white/80">
        Пропущен всего один день. Верни серию до {saveDeadline(save.until)} — будет {save.restored_streak} дней подряд.
        {save.free_available && " С клубным абонементом — бесплатно."}
      </p>
      <div className="mt-3 flex gap-2">
        {save.free_available && (
          <button
            disabled={busy}
            onClick={() => free.mutate()}
            className="flex-1 whitespace-nowrap rounded-2xl bg-accent-lime py-2.5 font-display text-sm font-bold text-bg-base active:scale-95 disabled:opacity-60"
          >
            Бесплатно
          </button>
        )}
        <button
          disabled={busy}
          onClick={() => stars.mutate()}
          className={`flex-1 whitespace-nowrap rounded-2xl py-2.5 font-display text-sm font-bold active:scale-95 disabled:opacity-60 ${
            save.free_available ? "bg-white/10 text-ink-chalk" : "animate-claim-glow bg-floodlight text-bg-base"
          }`}
        >
          {save.free_available ? `За ⭐ ${save.price_stars}` : `Вернуть за ⭐ ${save.price_stars}`}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-red-300">{error}</p>}
    </div>
  );
}

function CenturionSheet({ status, onClose }: { status: LoyaltyStatus; onClose: () => void }) {
  const player = status.centurion!;
  const left = Math.max(0, status.goal - status.streak);
  return createPortal(
    <AnimatePresence>
      <motion.div
        className="fixed inset-0 z-50 flex items-end justify-center bg-black/70 backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
      >
        <motion.div
          initial={{ y: 80 }}
          animate={{ y: 0 }}
          onClick={(e) => e.stopPropagation()}
          className="centurion-sky max-h-[90vh] w-full max-w-md overflow-y-auto rounded-t-3xl p-5 pb-8"
        >
          <p className="text-center font-display text-xl font-black uppercase tracking-wide text-fuchsia-100">
            Путь к Центуриону
          </p>
          <p className="mt-1 text-center text-xs text-white/75">
            {left > 0 ? `Ещё ${left} дн. подряд — и карта твоя` : "Ты у цели — карта придёт при следующем входе"}
          </p>
          <div className="centurion-glow mx-auto mt-4 w-40">
            <PlayerCard player={player} size="md" />
          </div>
          <ul className="mt-4 flex flex-col gap-1.5 text-xs text-white/80">
            <li>💜 Её нельзя выбить из пака — только за {status.goal} дней подряд без пропусков</li>
            <li>🔒 Навсегда твоя: не продаётся, не меняется, не сжигается</li>
            <li>🛟 Пропустил один день? «Страховка серии» вернёт серию</li>
          </ul>
          <div className="mt-4 flex flex-col gap-1.5">
            {status.milestones.map((m) => {
              const got = m.reached || status.streak >= m.days;
              return (
                <div key={m.days} className={`flex items-center gap-3 rounded-2xl px-3 py-2 ${got ? "bg-amber-300/15" : "bg-white/5"}`}>
                  <span className="w-12 font-display text-lg font-black text-fuchsia-100">{m.days}</span>
                  <span className="flex-1 text-xs text-white/85">
                    {[
                      m.coins ? `${m.coins.toLocaleString("ru-RU")} монет` : null,
                      m.card_rarity ? `${RARITY_LABELS[m.card_rarity]} карта` : null,
                      m.exclusive ? `${player.display_name} + значок «Центурион»` : null,
                    ].filter(Boolean).join(" · ")}
                  </span>
                  <span>{got ? "✅" : "🔒"}</span>
                </div>
              );
            })}
          </div>
          <button onClick={onClose} className="mt-5 w-full rounded-2xl bg-white/10 py-3 font-display text-sm font-bold">
            Понятно
          </button>
        </motion.div>
      </motion.div>
    </AnimatePresence>,
    document.body,
  );
}
