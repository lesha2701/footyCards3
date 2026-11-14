import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { healMagicWounded, magicHealInvoice, reviveMagicFree } from "@/api/magic";
import { pngArt, uiArt } from "@/components/magic/art/pngArt";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import type { MagicCasualties, MagicCasualty, MagicHub, MagicRisk } from "@/types";

const DEFAULT_RISK: MagicRisk = {
  dead_pct: { quick: 50, hardcore: 100 }, wounded_hours: 24, wounded_hours_win: 12,
  essence_per_fighter: { 1: 1, 2: 2, 3: 5, 4: 15, 5: 100 }, hardcore_essence_x: 2,
};

export function EssenceIcon({ size = 14 }: { size?: number }) {
  const img = uiArt("icon_essence");
  return img ? <img src={img} alt="" style={{ width: size, height: size }} className="inline-block align-[-2px]" /> : <span>💠</span>;
}

/** The risk of a run, said plainly before it starts (and wherever a loss can happen). */
export function LossWarning({ risk, mode, compact = false }: { risk?: MagicRisk | null; mode: string; compact?: boolean }) {
  const r = risk ?? DEFAULT_RISK;
  const hard = mode === "hardcore";
  const pct = r.dead_pct[mode] ?? 50;
  if (compact) {
    return (
      <p className={`rounded-xl px-2.5 py-1.5 text-[10px] leading-snug ${hard ? "bg-red-500/15 text-red-200" : "bg-amber-400/10 text-amber-100"}`}>
        ⚠️ {hard
          ? <>Хардкор: <b>все павшие существа погибают навсегда</b> (эссенция ×{r.hardcore_essence_x}).</>
          : <>Павшие существа уходят из коллекции: <b>{pct}% навсегда</b>, остальные ранены на {r.wounded_hours} ч.</>}
      </p>
    );
  }
  return (
    <div className={`rounded-2xl px-3 py-2 text-[11px] leading-snug ring-1 ${hard ? "bg-red-950/50 text-red-100 ring-red-400/40" : "bg-amber-400/10 text-amber-50 ring-amber-300/25"}`}>
      <p className="font-black">{hard ? "🔥 Риск хардкора" : "⚠️ Риск похода"}</p>
      {hard ? (
        <p className="mt-0.5">Все существа, павшие в бою, <b>погибают навсегда</b> и уходят из коллекции. За них — эссенция ×{r.hardcore_essence_x}.</p>
      ) : (
        <p className="mt-0.5">
          Павшие в бою существа уходят из коллекции: <b>{pct}% навсегда</b> (за них эссенция), остальные ранены и вернутся через {r.wounded_hours} ч
          {" "}(через {r.wounded_hours_win} ч, если поход выигран).
        </p>
      )}
      <p className="mt-0.5 opacity-80">Капитаны-футболисты не гибнут никогда. Наёмники с рынка не из коллекции — гибнут первыми. Сдача посреди боя = отряды на поле пали.</p>
    </div>
  );
}

function left(until: string, now: number): string {
  const ms = Math.max(0, new Date(until).getTime() - now);
  const h = Math.floor(ms / 3_600_000);
  const m = Math.floor((ms % 3_600_000) / 60_000);
  return h > 0 ? `${h} ч ${m} мин` : `${m} мин`;
}

function Row({ c, note }: { c: MagicCasualty; note?: string }) {
  const img = pngArt(`creatures/${c.unit}`);
  return (
    <div className="flex items-center gap-2 rounded-xl bg-black/25 px-2 py-1">
      {img ? <img src={img} alt="" className="h-8 w-8 object-contain" /> : <span className="text-lg">{c.emoji}</span>}
      <span className="min-w-0 flex-1 truncate text-caption font-bold text-ink-chalk">{c.name}</span>
      <span className="font-mono text-caption text-ink-chalk">×{c.count}</span>
      {note && <span className="font-mono text-[10px] text-ink-mist">{note}</span>}
    </div>
  );
}

/** Essence, the wounded with their timers, and healing them now (essence / Stars). */
export function WoundedCard({ hub }: { hub: MagicHub }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(t);
  }, []);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["magic-hub"] });
  const heal = useMutation({
    mutationFn: healMagicWounded,
    onSuccess: () => { hapticNotify("success"); refresh(); },
    onError: (e) => setError(formatGameError(e, "Не получилось вылечить")),
  });
  const stars = async () => {
    setPaying(true);
    setError(null);
    try {
      if ((await payShopWithStars(magicHealInvoice)) === "paid") { hapticNotify("success"); refresh(); }
    } catch (e) {
      setError(formatGameError(e, "Покупка не прошла"));
    } finally {
      setPaying(false);
    }
  };
  const revive = useMutation({
    mutationFn: reviveMagicFree,
    onSuccess: () => { hapticNotify("success"); refresh(); },
    onError: (e) => setError(formatGameError(e, "Не получилось воскресить")),
  });
  const wounded = hub.wounded ?? [];
  const essence = hub.essence ?? 0;
  const cost = hub.heal_essence ?? 0;
  const woundedIcon = uiArt("icon_wounded");
  return (
    <section className="rounded-3xl bg-bg-surface p-3">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-xs font-bold text-ink-chalk">
          {woundedIcon ? <img src={woundedIcon} alt="" className="h-5 w-5" /> : "🩹"} Лазарет
        </p>
        <span className="flex items-center gap-1 rounded-full bg-cyan-400/15 px-2 py-0.5 font-mono text-caption font-bold text-cyan-100">
          <EssenceIcon /> {essence} эссенции
        </span>
      </div>
      {hub.revive && hub.revive.dead.length > 0 && (
        <div className="mt-2 rounded-2xl bg-gradient-to-br from-amber-300/25 to-sky-400/15 p-2.5 ring-1 ring-amber-200/50">
          <p className="text-xs font-black text-amber-100">🕊 Бесплатное воскрешение — один раз</p>
          <p className="mt-0.5 text-[10px] leading-snug text-ink-chalk">
            Верни всех, кто погиб навсегда в последнем походе. Подарок новичку: доступен только один раз{hub.revive.essence ? `, эссенция за них (${hub.revive.essence}) уйдёт` : ""}.
          </p>
          <div className="mt-1.5 flex flex-col gap-1">{hub.revive.dead.map((c) => <Row key={c.unit} c={c} />)}</div>
          <button disabled={revive.isPending} onClick={() => { setError(null); revive.mutate(); }}
            className="mt-2 w-full rounded-xl bg-amber-300 py-2 text-xs font-black text-black active:scale-95 disabled:opacity-40">
            Воскресить бесплатно
          </button>
        </div>
      )}
      {wounded.length === 0 ? (
        <p className="mt-1.5 text-caption text-ink-mist">Раненых нет. Павшие в походе существа отдыхают здесь и сами возвращаются в коллекцию.</p>
      ) : (
        <>
          <div className="mt-2 flex flex-col gap-1">
            {wounded.map((w, i) => <Row key={i} c={w} note={`⏳ ${left(w.until, now)}`} />)}
          </div>
          <div className="mt-2 grid grid-cols-2 gap-1.5">
            <button disabled={heal.isPending || essence < cost} onClick={() => { setError(null); heal.mutate(); }}
              className="flex items-center justify-center gap-1 rounded-xl bg-cyan-400 py-2 text-xs font-black text-black active:scale-95 disabled:opacity-40">
              Вылечить · {cost} <EssenceIcon size={12} />
            </button>
            {hub.heal_stars ? (
              <button disabled={paying} onClick={stars}
                className="rounded-xl bg-gradient-to-r from-sky-400 to-indigo-500 py-2 text-xs font-black text-white active:scale-95 disabled:opacity-40">
                Вылечить · {hub.heal_stars} ⭐
              </button>
            ) : <span />}
          </div>
        </>
      )}
      {hub.refill_today && (
        <p className="mt-2 rounded-xl bg-emerald-400/10 px-2.5 py-1.5 text-[10px] text-emerald-200">
          🎁 Коллекция опустела — сегодня ты получил бесплатный стартовый набор существ.
        </p>
      )}
      {error && <p className="mt-1.5 text-micro text-red-400">{error}</p>}
    </section>
  );
}

/** The end of a run: who died for good (and the essence), who is wounded till when. */
export function CasualtiesBlock({ cas }: { cas?: MagicCasualties | null }) {
  const extra = cas && (cas.guard_lost || cas.captains_xp) ? (
    <p className="mt-1 text-[10px] text-ink-mist">
      {cas.captains_xp ? `🎖 Капитаны и гвардия: +${cas.captains_xp} опыта` : ""}
      {cas.guard_lost ? ` · 🛡 гвардия потеряла ${cas.guard_lost}` : ""}
    </p>
  ) : null;
  if (!cas || (cas.dead.length === 0 && cas.wounded.length === 0)) {
    return <><p className="mt-2 rounded-xl bg-emerald-400/10 px-3 py-2 text-xs text-emerald-200">🛡 Армия вернулась без потерь из коллекции</p>{extra}</>;
  }
  return (
    <div className="mt-2 flex flex-col gap-1 rounded-2xl bg-black/30 p-2 text-left">
      {extra}
      {cas.dead.length > 0 && (
        <>
          <p className="flex items-center justify-between text-[11px] font-black text-red-300">
            <span>💀 Погибли навсегда</span>
            {cas.essence > 0 && <span className="flex items-center gap-1 text-cyan-200">+{cas.essence} <EssenceIcon size={12} /></span>}
          </p>
          {cas.dead.map((c) => <Row key={c.unit} c={c} />)}
        </>
      )}
      {cas.wounded.length > 0 && (
        <>
          <p className="mt-1 text-[11px] font-black text-amber-200">
            🩹 Ранены — вернутся {cas.until ? new Date(cas.until).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "позже"}
            {cas.won_faster ? " (победа: вдвое быстрее)" : ""}
          </p>
          {cas.wounded.map((c) => <Row key={c.unit} c={c} />)}
        </>
      )}
    </div>
  );
}
