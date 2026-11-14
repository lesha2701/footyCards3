import { useMutation } from "@tanstack/react-query";
import { Backdrop } from "@/components/magic/Backdrop";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { feedMagicCaptain, refillMagicGuard, setMagicCaptainTrait, setMagicGuard, setMagicGuardTrait } from "@/api/magic";
import { pngArt, uiArt } from "@/components/magic/art/pngArt";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import type { MagicArmy, MagicCaptain, MagicTrait } from "@/types";

const TIER = ["", "I", "II", "III", "IV", "V"];

function Photo({ path, size }: { path?: string | null; size: number }) {
  const src = path ? staticUrl(path) : uiArt("captain_badge");
  return src
    ? <img src={src} alt="" style={{ width: size, height: size }} className="shrink-0 rounded-full bg-black/30 object-cover object-top ring-1 ring-white/15" />
    : <span style={{ width: size, height: size }} className="flex shrink-0 items-center justify-center rounded-full bg-white/10">🎖</span>;
}

function XpBar({ xp, next, table }: { xp: number; next: number | null | undefined; table: number[] }) {
  const lvl = table.filter((t) => xp >= t).length;
  const from = table[lvl - 1] ?? 0;
  const pct = next ? Math.round(((xp - from) / Math.max(1, next - from)) * 100) : 100;
  return (
    <div className="mt-1 flex items-center gap-1.5">
      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-gradient-to-r from-amber-300 to-fuchsia-400" style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-[9px] text-ink-mist">{next ? `${xp}/${next}` : "макс."}</span>
    </div>
  );
}

function Traits({ traits, all }: { traits: string[]; all: MagicTrait[] }) {
  if (!traits.length) return null;
  return (
    <span className="flex flex-wrap gap-1">
      {traits.map((t) => {
        const x = all.find((a) => a.code === t);
        return <span key={t} className="rounded-full bg-fuchsia-400/15 px-1.5 text-[9px] font-bold text-fuchsia-100">{x?.emoji} {x?.name ?? t}</span>;
      })}
    </span>
  );
}

function TraitPicker({ all, have, onPick, busy }: { all: MagicTrait[]; have: string[]; onPick: (code: string) => void; busy: boolean }) {
  return (
    <div className="mt-1.5 rounded-xl bg-fuchsia-500/10 p-1.5 ring-1 ring-fuchsia-300/30">
      <p className="mb-1 text-[10px] font-black text-fuchsia-100">✨ Новая черта — выбери одну навсегда</p>
      <div className="grid grid-cols-2 gap-1">
        {all.filter((t) => !have.includes(t.code)).map((t) => (
          <button key={t.code} disabled={busy} onClick={() => onPick(t.code)}
            className="rounded-lg bg-black/30 px-1.5 py-1 text-left active:scale-95 disabled:opacity-40">
            <span className="block text-[10px] font-bold text-ink-chalk">{t.emoji} {t.name}</span>
            <span className="block text-[9px] leading-tight text-ink-mist">{t.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/** The captains of the stacks: level (XP from runs and from spare copies of the same footballer) and traits. */
export function CaptainsPanel({ army, ids, onArmy }: { army: MagicArmy; ids: number[]; onArmy: (a: MagicArmy) => void }) {
  const [error, setError] = useState<string | null>(null);
  const ok = (a: MagicArmy) => { hapticNotify("success"); setError(null); onArmy(a); };
  const fail = (e: unknown) => setError(formatGameError(e, "Не получилось"));
  const feed = useMutation({ mutationFn: ({ id, n }: { id: number; n: number }) => feedMagicCaptain(id, n), onSuccess: ok, onError: fail });
  const trait = useMutation({ mutationFn: ({ id, code }: { id: number; code: string }) => setMagicCaptainTrait(id, code), onSuccess: ok, onError: fail });
  const caps = ids.map((id) => army.captains.find((c) => c.card.player_id === id)).filter(Boolean) as MagicCaptain[];
  const table = army.captain_xp ?? [];
  if (!caps.length) return null;
  return (
    <section className="rounded-2xl bg-bg-surface p-3">
      <p className="text-xs font-bold text-ink-chalk">🎖 Капитаны армии</p>
      <p className="mb-2 text-[10px] leading-snug text-ink-mist">
        Опыт — за каждый поход и за лишние копии того же футболиста (+{caps[0]?.dup_xp ?? 0}, одна копия в день). Уровень: +5% к атаке и защите отряда; черты — на 3-м и 5-м уровне. Капитаны не гибнут.
      </p>
      <div className="flex flex-col gap-1.5">
        {caps.map((c) => {
          const level = c.level ?? 1;
          const spare = Math.max(0, c.copies - 1);
          const canTrait = (c.traits?.length ?? 0) < (c.trait_slots ?? 0);
          return (
            <div key={c.card.player_id} className="rounded-xl bg-black/25 p-2">
              <div className="flex items-center gap-2">
                <Photo path={c.card.image_path} size={36} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-bold text-ink-chalk">
                    {c.card.name} <span className="rounded-full bg-amber-300 px-1.5 text-[9px] font-black text-black">ур. {level}</span>
                  </p>
                  <XpBar xp={c.xp ?? 0} next={c.next_xp} table={table} />
                  <Traits traits={c.traits ?? []} all={army.traits ?? []} />
                </div>
                <button disabled={!spare || !c.next_xp || !c.fed_left || feed.isPending} onClick={() => feed.mutate({ id: c.card.player_id, n: 1 })}
                  className="shrink-0 rounded-xl bg-amber-400 px-2 py-1.5 text-[10px] font-black leading-tight text-black active:scale-95 disabled:bg-white/10 disabled:text-ink-mist">
                  Дубль → +{c.dup_xp ?? 0}
                  <span className="block font-normal">{c.fed_left ? `лишних: ${spare}` : "завтра"}</span>
                </button>
              </div>
              {canTrait && (
                <TraitPicker all={army.traits ?? []} have={c.traits ?? []} busy={trait.isPending}
                  onPick={(code) => trait.mutate({ id: c.card.player_id, code })} />
              )}
            </div>
          );
        })}
      </div>
      {error && <p className="mt-1.5 text-micro text-red-400">{error}</p>}
    </section>
  );
}

/** «Гвардия»: one levelled stack of a footballer's duplicates beside the army (no leadership). */
export function GuardPanel({ army, onArmy, hardcore }: { army: MagicArmy; onArmy: (a: MagicArmy) => void; hardcore: boolean }) {
  const [error, setError] = useState<string | null>(null);
  const [picking, setPicking] = useState(false);
  const ok = (a: MagicArmy) => { hapticNotify("success"); setError(null); onArmy(a); setPicking(false); };
  const fail = (e: unknown) => setError(formatGameError(e, "Не получилось"));
  const choose = useMutation({ mutationFn: setMagicGuard, onSuccess: ok, onError: fail });
  const refill = useMutation({ mutationFn: ({ id, n }: { id: number; n: number }) => refillMagicGuard(id, n), onSuccess: ok, onError: fail });
  const trait = useMutation({ mutationFn: setMagicGuardTrait, onSuccess: ok, onError: fail });
  const g = army.guard;
  const banner = pngArt(`creatures/${g?.unit ?? "magic_guard"}`) ?? uiArt("guard_banner");
  const table = army.guard_xp ?? [];
  const full = g ? g.count >= g.size : false;
  return (
    <section className="rounded-2xl bg-gradient-to-b from-amber-900/30 to-bg-surface p-3 ring-1 ring-amber-300/20">
      <div className="flex items-center gap-2">
        {banner ? <img src={banner} alt="" className="h-16 w-12 object-contain" /> : <span className="text-3xl">🛡</span>}
        <div className="min-w-0 flex-1">
          <p className="font-display text-sm font-black text-ink-chalk">Гвардия</p>
          <p className="text-[10px] leading-snug text-ink-mist">Отдельный отряд из дублей одного футболиста. Идёт в каждый поход рядом с армией и не тратит лидерство.</p>
        </div>
      </div>
      {!g?.card ? (
        <button onClick={() => setPicking(true)} className="mt-2 w-full rounded-xl bg-amber-400 py-2.5 text-sm font-black text-black active:scale-95">
          Выбрать футболиста гвардии
        </button>
      ) : (
        <>
          <div className="mt-2 flex items-center gap-2 rounded-xl bg-black/25 p-2">
            <Photo path={g.card.image_path} size={42} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-bold text-ink-chalk">
                {g.card.name} <span className="rounded-full bg-amber-300 px-1.5 text-[9px] font-black text-black">ур. {g.level}</span>
              </p>
              <XpBar xp={g.xp} next={g.next_xp} table={table} />
              <p className="mt-0.5 text-[10px] text-ink-chalk">🛡 Бойцов: <b>{g.count}</b> / {g.size}{g.points ? ` · +${g.points}/${g.fighter_points} к следующему` : ""} · тир {TIER[g.tier] ?? g.tier}</p>
              {g.ability && <p className="text-[10px] text-sky-200">✦ {g.ability}</p>}
              <Traits traits={g.traits} all={army.traits ?? []} />
            </div>
            <button onClick={() => setPicking(true)} className="shrink-0 self-start rounded-full bg-white/10 px-2 py-1 text-[9px] text-ink-mist active:scale-95">Сменить</button>
          </div>
          {g.traits.length < g.trait_slots && (
            <TraitPicker all={army.traits ?? []} have={g.traits} busy={trait.isPending} onPick={(code) => trait.mutate(code)} />
          )}
          <p className={`mt-1.5 rounded-lg px-2 py-1 text-[10px] ${hardcore ? "bg-red-500/15 text-red-200" : "bg-amber-400/10 text-amber-100"}`}>
            ⚠️ Гвардия тоже несёт потери: {hardcore ? "в хардкоре павшие гвардейцы гибнут все" : "половина павших гвардейцев гибнет"}. Пополняй дублями.
          </p>
          <p className="mb-1 mt-2 text-[11px] font-bold uppercase tracking-wide text-ink-mist">Пополнить {full ? "· отряд полный" : ""}</p>
          <p className="mb-1.5 text-[9px] text-ink-mist-dim">Очки за копию: тот же футболист 6 · редкость выше 4 · та же 3 · ниже 2. Боец этой гвардии стоит {g.fighter_points}. Чем реже футболист, тем меньше бойцов, но каждый сильнее — общая сила у всех редкостей равная. Одна копия всегда остаётся.</p>
          {g.materials.length === 0 ? (
            <p className="text-caption text-ink-mist">Лишних копий футболистов пока нет.</p>
          ) : (
            <div className="flex max-h-64 flex-col gap-1 overflow-y-auto">
              {g.materials.map((m) => (
                <div key={m.card.player_id} className="flex items-center gap-2 rounded-xl bg-black/20 px-2 py-1">
                  <Photo path={m.card.image_path} size={26} />
                  <p className="min-w-0 flex-1 truncate text-[11px] text-ink-chalk">
                    {m.card.name} <span className="text-ink-mist-dim">×{m.spare}</span>
                  </p>
                  <span className="font-mono text-[9px] text-amber-200">+{m.points}/{g.fighter_points}</span>
                  <button disabled={full || refill.isPending} onClick={() => refill.mutate({ id: m.card.player_id, n: 1 })}
                    className="rounded-lg bg-amber-400 px-2 py-1 text-[10px] font-black text-black active:scale-95 disabled:opacity-40">
                    Сжечь 1
                  </button>
                </div>
              ))}
            </div>
          )}
        </>
      )}
      {error && <p className="mt-1.5 text-micro text-red-400">{error}</p>}

      <AnimatePresence>
        {picking && (
          <Backdrop onClick={() => setPicking(false)} className="fixed inset-0 z-[70] flex items-end justify-center bg-black/70">
            <motion.div initial={{ y: 60 }} animate={{ y: 0 }} exit={{ y: 60 }} onClick={(e) => e.stopPropagation()}
              className="max-h-[75vh] w-full max-w-md overflow-y-auto rounded-t-3xl bg-bg-base p-4 pb-24">
              <p className="font-display text-base font-black text-ink-chalk">Футболист гвардии</p>
              <p className="mb-2 text-micro text-ink-mist">
                Его рейтинг и позиция — сила гвардии; его дубли пополняют её лучше всего.
                {g?.card ? " Смена футболиста сжигает половину опыта гвардии (бойцы остаются)." : ""}
              </p>
              <div className="flex flex-col gap-1">
                {[...army.captains].sort((a, b) => b.copies - a.copies || b.card.rating - a.card.rating).map((c) => (
                  <button key={c.card.player_id} disabled={choose.isPending} onClick={() => choose.mutate(c.card.player_id)}
                    className={`flex items-center gap-2.5 rounded-2xl px-3 py-2 text-left ring-1 active:scale-[0.99] ${g?.card?.player_id === c.card.player_id ? "bg-amber-300/10 ring-amber-300/60" : "bg-bg-surface ring-white/5"}`}>
                    <Photo path={c.card.image_path} size={32} />
                    <span className="min-w-0 flex-1 truncate text-xs font-bold text-ink-chalk">{c.card.name} <span className="font-normal text-ink-mist-dim">{c.card.position} · {c.card.rating}</span></span>
                    <span className="font-mono text-[10px] text-amber-200">копий {c.copies}</span>
                  </button>
                ))}
              </div>
            </motion.div>
          </Backdrop>
        )}
      </AnimatePresence>
    </section>
  );
}
