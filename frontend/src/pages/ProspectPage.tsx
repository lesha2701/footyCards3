import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import type { MyPlayerAppearance } from "@/api/myPlayer";
import {
  answerProspectStory, buyProspectCosmetic, createProspect, createProspectInvoice, equipProspectCosmetic, fetchProspect,
  setProspectMentor, trainProspect, updateProspect,
  type Prospect, type ProspectDraft, type ProspectShopItem, type ProspectView,
} from "@/api/prospect";
import ShareButton from "@/components/common/ShareButton";
import { IconCoin } from "@/components/icons";
import PlayerAvatar from "@/components/myPlayer/PlayerAvatar";
import {
  BirthdayCard, FriendsTab, GraduateHome, GraduationCard, HallOfGraduates, IncomingDuels, OtherModesCard, SpecPickCard, WeekTournament,
} from "@/components/prospect/ProspectLife";
import { PositionCard, PositionPickCard, PotentialCard } from "@/components/prospect/ProspectPosition";
import { AGE_WORD, BACKDROPS, fmt, payWithStars, PROSPECT_KEY as KEY, roman } from "@/components/prospect/shared";
import { PROSPECT_ART, stageScene } from "@/lib/prospectArt";
import { formatGameError } from "@/lib/errors";
import { EYE_COLORS, EYE_LABELS, HAIR_COLORS, HAIR_LABELS, KIT_COLORS, KIT_PATTERN_LABELS, SKIN_TONES } from "@/lib/myPlayer";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

const LINE_SHORT: Record<string, string> = { GK: "вратарь", DEF: "защита", MID: "центр", FWD: "атака" };
const DEFAULT_LOOK: MyPlayerAppearance = { skin: 1, hair: 1, hair_color: 1, beard: 0, eye_color: 0, kit: 3, kit_pattern: 0 };
// Accessories drawn by PlayerAvatar; the others are a badge on the card.
const AVATAR_ACCESSORY: Record<string, string> = { acc_headband: "headband", acc_band: "captain" };
const BADGE_ACCESSORY: Record<string, string> = { acc_boots: "👟", acc_trophy: "🏆" };
// The child grows on the card: the avatar's scale by stage.
const GROWTH = [0.62, 0.72, 0.82, 0.92, 1];

type Tab = "today" | "growth" | "friends" | "style" | "album";
const TABS: [Tab, string][] = [["today", "Сегодня"], ["growth", "Рост"], ["friends", "Друзья"], ["style", "Стиль"], ["album", "Альбом"]];
// Other modes he plays (the start pages take ?prospect=1).
const MODES = [
  { title: "Пенальти", emoji: "🥅", to: "/play/penalty?prospect=1" },
  { title: "Штрафной", emoji: "🎯", to: "/play/free-kick?prospect=1" },
  { title: "1 на 1", emoji: "🏃", to: "/play/one-on-one?prospect=1" },
];

/** «Воспитанник Академии»: create a child footballer and raise him — the
 * age follows the calendar, the rating follows XP (backend prospect_service
 * holds every number). */
export default function ProspectPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: KEY, queryFn: fetchProspect });
  const [editing, setEditing] = useState(false);
  const set = (v: ProspectView) => queryClient.setQueryData(KEY, v);

  if (isLoading || !data) return <div className="h-64 animate-pulse rounded-3xl bg-bg-surface" aria-busy />;
  if (!data.enabled && !data.prospect) {
    return <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-sm text-legend">«Воспитанник Академии» временно недоступен.</p>;
  }
  if (!data.prospect && data.graduate && !editing) {
    return <GraduateHome view={data} onNewGeneration={() => setEditing(true)} />;
  }
  if (!data.prospect || editing) {
    return <Constructor view={data} onSaved={(v) => { set(v); setEditing(false); }}
      onCancel={data.prospect || data.graduate ? () => setEditing(false) : undefined} />;
  }
  return <Raise view={data} prospect={data.prospect} onView={set} onEdit={() => setEditing(true)} />;
}

function Raise({ view, prospect: p, onView, onEdit }: {
  view: ProspectView; prospect: Prospect; onView: (v: ProspectView) => void; onEdit: () => void;
}) {
  const [params, setParams] = useSearchParams();
  const tab: Tab = TABS.some(([id]) => id === params.get("tab")) ? (params.get("tab") as Tab) : "today";
  const setTab = (id: Tab) => setParams(id === "today" ? {} : { tab: id }, { replace: true });
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const stage = view.stages[p.stage];
  const toast = (text: string) => { setError(null); setNotice(text); hapticNotify("success"); };
  const fail = (err: unknown) => { setNotice(null); setError(formatGameError(err, "Не получилось")); };
  const ctx = { view, onView, toast, fail };

  return (
    <div className="flex flex-col gap-4">
      <ProspectCard view={view} p={p} onEdit={onEdit} />
      <StageLadder view={view} p={p} />
      {!view.enabled && <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-xs text-legend">Воспитанник временно на каникулах — рост на паузе.</p>}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      <AnimatePresence>
        {notice && (
          <motion.p initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
            className="rounded-xl bg-path/10 px-3 py-2 text-xs text-path">{notice}</motion.p>
        )}
      </AnimatePresence>
      <div className="grid grid-cols-5 gap-1 rounded-2xl bg-bg-surface p-1" role="tablist" aria-label="Разделы воспитанника">
        {TABS.map(([id, label]) => {
          const dot = (id === "today" && (!!view.spec_pick || !!view.position_pick || !!view.graduation?.available || (!!view.bday?.today && !view.bday.opened)))
            || (id === "friends" && (view.duels ?? []).some((d) => d.can_play));
          return (
            <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
              className={`relative rounded-xl py-2 text-[11px] font-semibold ${tab === id ? "bg-path text-bg-base" : "text-ink-mist"}`}>
              {label}
              {dot && <span className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full bg-red-400" aria-label="есть новое" />}
            </button>
          );
        })}
      </div>
      {tab === "today" && (
        <div className="flex flex-col gap-3">
          <GraduationCard {...ctx} p={p} />
          <PositionPickCard {...ctx} />
          <SpecPickCard {...ctx} />
          <BirthdayCard {...ctx} p={p} />
          <IncomingDuels view={view} />
          <TodayTab view={view} p={p} stageName={stage.name} onView={onView} toast={toast} fail={fail} />
          <OtherModesCard view={view} routes={MODES} />
        </div>
      )}
      {tab === "growth" && <GrowthTab view={view} p={p} onView={onView} toast={toast} fail={fail} />}
      {tab === "friends" && <FriendsTab {...ctx} hasProspect />}
      {tab === "style" && <StyleTab view={view} p={p} onView={onView} toast={toast} fail={fail} />}
      {tab === "album" && <AlbumTab view={view} p={p} />}
    </div>
  );
}

function ProspectCard({ view, p, onEdit }: { view: ProspectView; p: Prospect; onEdit: () => void }) {
  const stage = view.stages[p.stage];
  const pct = Math.round((p.xp_in_point / p.xp_per_point) * 100);
  // The default backdrop is the scene of his stage; bought backdrops stay as they are.
  const scene = p.background === "bg_yard";
  return (
    <section className={`relative overflow-hidden rounded-3xl border border-path/30 p-4 ${scene ? "bg-bg-surface" : `bg-gradient-to-b ${BACKDROPS[p.background] ?? BACKDROPS.bg_yard}`}`}>
      {scene && (
        <>
          <img src={stageScene(p.stage_code)} alt="" aria-hidden data-testid="prospect-scene"
            className="pointer-events-none absolute inset-x-0 top-0 h-[300px] w-full object-cover object-top" />
          <span className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/40 via-transparent via-40% to-bg-surface to-70%" />
        </>
      )}
      <div className="relative flex items-start justify-between">
        <div>
          <p className="text-micro uppercase tracking-wider text-path">
            Воспитанник Академии{p.generation > 1 ? ` · ${roman(p.generation)} поколение` : ""}
          </p>
          <h1 className="font-display text-xl font-bold text-ink-chalk">{p.name}</h1>
          <p className="text-xs text-ink-mist">#{p.number} · {p.universal ? "универсал" : p.position} · {p.foot === "left" ? "левша" : "правша"}</p>
        </div>
        <div className="text-right">
          <p className="font-display text-4xl font-bold leading-none text-ink-chalk">{p.rating}</p>
          <p className="text-micro uppercase tracking-wider text-ink-mist">рейтинг</p>
        </div>
      </div>
      <div className="relative mx-auto mt-1 flex h-44 w-40 items-end justify-center">
        <motion.div className="h-full w-full origin-bottom" initial={false} animate={{ scale: GROWTH[p.stage] ?? 1 }}>
          <PlayerAvatar appearance={p.appearance} number={p.number} className="h-full w-full" background={false}
            accessory={AVATAR_ACCESSORY[p.accessory ?? ""] ?? null} />
        </motion.div>
        {p.accessory && BADGE_ACCESSORY[p.accessory] && (
          <span className="absolute bottom-2 right-0 text-2xl" aria-hidden>{BADGE_ACCESSORY[p.accessory]}</span>
        )}
      </div>
      {p.specs.length > 0 && (
        <div className="relative mt-1 flex flex-wrap justify-center gap-1" aria-label="Таланты">
          {p.specs.map((sp) => <span key={sp.code} className="rounded-full bg-black/30 px-2 py-0.5 text-micro text-ink-chalk">{sp.emoji} {sp.name}</span>)}
        </div>
      )}
      <div className="relative mt-2 grid grid-cols-3 gap-2 text-center">
        <Stat value={`${p.age} ${AGE_WORD(p.age)}`} label={view.bday?.today ? "🎂 ДР сегодня!" : `ДР через ${p.days_to_birthday} дн.`} />
        <Stat value={`${stage.emoji} ${stage.name}`} label={`потолок ${p.stage_cap}`} />
        <Stat value={p.potential ? "★".repeat(p.potential) : "★ ?"} label={p.peak ? `пик ${p.peak}` : "потенциал скрыт"} />
      </div>
      <div className="relative mt-3">
        <div className="flex justify-between text-micro text-ink-mist">
          <span>до +1 к рейтингу</span>
          <span className="font-mono">{fmt(p.xp_in_point)} / {fmt(p.xp_per_point)}</span>
        </div>
        <div className="mt-1 h-2 overflow-hidden rounded-full bg-black/30">
          <motion.div className="h-full rounded-full bg-path" initial={false} animate={{ width: `${p.capped ? 100 : pct}%` }} />
        </div>
        {p.capped && (
          <p className="mt-1 text-caption text-legend">
            Упёрся в потолок ступени — опыт копится{p.banked_points ? ` (+${p.banked_points} в запасе)` : ""}
            {p.days_to_next_stage !== null ? `, новая ступень через ${p.days_to_next_stage} дн.` : ""}
          </p>
        )}
      </div>
      <button onClick={onEdit} className="absolute left-3 top-[42%] rounded-full bg-black/30 px-2.5 py-1 text-micro text-ink-mist">✏️ Изменить</button>
      <ShareButton kind="prospect" id={0} label="Поделиться" compact className="absolute right-3 top-[42%]" />
    </section>
  );
}

function Stat({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-xl bg-black/25 px-1.5 py-1.5">
      <p className="truncate font-display text-sm font-bold text-ink-chalk">{value}</p>
      <p className="truncate text-micro text-ink-mist">{label}</p>
    </div>
  );
}

function StageLadder({ view, p }: { view: ProspectView; p: Prospect }) {
  return (
    <section className="grid grid-cols-5 gap-1" aria-label="Ступени">
      {view.stages.map((s, i) => (
        <div key={s.code} className={`rounded-xl px-1 py-2 text-center ${i === p.stage ? "bg-path/20 ring-1 ring-path" : i < p.stage ? "bg-bg-surface" : "bg-bg-surface opacity-50"}`}>
          <p className="text-lg leading-none" aria-hidden>{i < p.stage ? "✅" : s.emoji}</p>
          <p className="mt-1 truncate text-micro font-semibold text-ink-chalk">{s.name}</p>
          <p className="text-micro text-ink-mist">{s.from_age}+</p>
        </div>
      ))}
    </section>
  );
}

type TabProps = { view: ProspectView; p: Prospect; onView: (v: ProspectView) => void; toast: (t: string) => void; fail: (e: unknown) => void };

function TodayTab({ view, p, stageName, onView, toast, fail }: TabProps & { stageName: string }) {
  const navigate = useNavigate();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const t = view.training!;
  const story = view.story;
  const train = useMutation({
    mutationFn: (drill: string) => trainProspect(drill),
    onSuccess: (r) => {
      onView(r.view);
      toast(`${r.drill}: ${"⭐".repeat(r.grade)} · +${r.xp} опыта${r.streak_bonus ? ` · серия! +${r.streak_bonus}` : ""}${r.potential_up ? " · потенциал вырос! ★" : ""}`);
    },
    onError: fail,
  });
  const answer = useMutation({
    mutationFn: ({ code, option }: { code: string; option: number }) => answerProspectStory(code, option),
    onSuccess: (r) => {
      onView(r.view);
      if (r.coins_spent) updateBalance(r.view.balance);
      toast(r.won === false ? `Не вышло… но +${r.xp} опыта`
        : `+${r.xp} опыта${r.trial_credit ? " · 🏅 победа в испытании засчитана" : ""}${r.potential_up ? " · потенциал вырос! ★" : ""}`);
    },
    onError: fail,
  });
  const extra = useMutation({
    mutationFn: () => payWithStars(() => createProspectInvoice("training")),
    onSuccess: (v) => { if (v) { onView(v); toast("Доп. тренировка готова"); } },
    onError: fail,
  });
  const canTrain = t.free_available || t.extra_credits > 0;
  const capLeft = Math.max(0, (view.daily_xp_cap ?? 0) - (view.xp_today ?? 0));

  return (
    <div className="flex flex-col gap-3">
      {story && (
        <section className="rounded-2xl border border-legend/30 bg-legend/5 p-3" aria-label="История дня">
          <p className="text-micro uppercase tracking-wider text-legend">История · {stageName}</p>
          <p className="font-display text-base font-bold text-ink-chalk">{story.title}</p>
          <p className="text-xs text-ink-mist">{story.text}</p>
          <div className="mt-2 flex flex-col gap-1.5">
            {story.options.map((o, i) => (
              <button key={o.label} disabled={answer.isPending} onClick={() => answer.mutate({ code: story.code, option: i })}
                className="flex items-center gap-2 rounded-xl bg-bg-surface px-3 py-2 text-left disabled:opacity-50 active:scale-[0.99]">
                <span className="min-w-0 flex-1 text-sm text-ink-chalk">{o.label}</span>
                <span className="shrink-0 text-right text-micro text-ink-mist">
                  {o.chance !== null ? `${o.chance}%: +${o.win_xp}${o.trial ? " и 🏅 победа в испытании" : ""} · иначе +${o.xp}` : `+${o.xp}`}
                  {o.coins > 0 && <span className="ml-1 inline-flex items-center gap-0.5 text-legend">−{fmt(o.coins)}<IconCoin size={10} /></span>}
                </span>
              </button>
            ))}
          </div>
        </section>
      )}

      <section className="rounded-2xl bg-bg-surface p-3" aria-label="Матч">
        <div className="flex items-center gap-3">
          <span className="text-3xl" aria-hidden>⚽</span>
          <div className="min-w-0 flex-1">
            <p className="font-display text-sm font-bold text-ink-chalk">Сыграть в «Ответке»</p>
            <p className="text-xs text-ink-mist">
              Играет сам {p.name}, против сверстников. Матч +{view.otvetka_xp?.match}, гол +{view.otvetka_xp?.goal}, победа +{view.otvetka_xp?.win}
            </p>
            <p className="text-micro text-ink-mist-dim">Опыт за матчи сегодня: {view.xp_today} / {view.daily_xp_cap}{capLeft === 0 ? " — лимит, завтра ещё" : ""}</p>
          </div>
        </div>
        <button onClick={() => navigate("/play/otvetka?prospect=1")}
          className="mt-2 w-full rounded-xl bg-path py-2.5 text-sm font-bold text-bg-base active:scale-[0.99]">
          На поле
        </button>
      </section>

      <section className="rounded-2xl bg-bg-surface p-3" aria-label="Тренировка">
        <div className="flex items-center justify-between">
          <p className="font-display text-sm font-bold text-ink-chalk">Тренировка дня</p>
          <p className="text-micro text-ink-mist">🔥 серия {t.streak} · каждые {t.streak_days} дн. +{t.streak_bonus_xp}</p>
        </div>
        <p className="text-xs text-ink-mist">
          {t.free_available ? `Бесплатная тренировка: ~${t.xp} опыта, оценка тренера ×0.8…×1.3` : t.extra_credits > 0 ? `Доп. тренировок: ${t.extra_credits}` : "Сегодня уже тренировался"}
        </p>
        {t.universal && <p className="text-micro text-ink-mist-dim">Универсал: что он тренирует, то тренер и предложит на «Юношах»</p>}
        <div className={`mt-2 grid gap-1.5 ${t.drills.length === 4 ? "grid-cols-2" : "grid-cols-3"}`}>
          {t.drills.map((d) => (
            <button key={d.code} disabled={!canTrain || train.isPending} onClick={() => train.mutate(d.code)}
              className="flex min-h-[44px] flex-col items-center justify-center rounded-xl bg-bg-raised px-1.5 py-1 text-xs font-semibold text-ink-chalk disabled:opacity-40 active:scale-[0.98]">
              {d.title}
              {t.universal && <span className="text-[10px] font-normal text-ink-mist">{LINE_SHORT[d.line]}</span>}
            </button>
          ))}
        </div>
        {!canTrain && t.extra_bought_today < t.extra_max && (
          <button disabled={extra.isPending} onClick={() => extra.mutate()}
            className="mt-2 w-full rounded-xl bg-amber-400 py-2 text-xs font-bold text-black disabled:opacity-50">
            Ещё тренировка · ⭐ {t.extra_stars}
          </button>
        )}
      </section>
    </div>
  );
}

function GrowthTab({ view, p, onView, toast, fail }: TabProps) {
  const [picking, setPicking] = useState(false);
  const bonus = view.bonus ?? { academy: 0, mentor: 0, coach: 0, deficit: 0 };
  const coach = useMutation({
    mutationFn: () => payWithStars(() => createProspectInvoice("coach")),
    onSuccess: (v) => { if (v) { onView(v); toast("Личный тренер приступил к работе"); } },
    onError: fail,
  });
  const scout = useMutation({
    mutationFn: () => payWithStars(() => createProspectInvoice("scout")),
    onSuccess: (v) => { if (v) { onView(v); toast(`Скаут: ${"★".repeat(v.prospect?.potential ?? 0)}`); } },
    onError: fail,
  });
  const mentor = useMutation({
    mutationFn: (id: number | null) => setProspectMentor(id),
    onSuccess: (v) => { onView(v); setPicking(false); toast(v.mentor ? `Наставник: ${v.mentor.name}` : "Наставник снят"); },
    onError: fail,
  });
  const rival = view.rival;
  const cohort = view.cohort;

  return (
    <div className="flex flex-col gap-3">
      <WeekTournament view={view} />
      <section className="rounded-2xl bg-bg-surface p-3" aria-label="Бонусы к опыту">
        <p className="font-display text-sm font-bold text-ink-chalk">Бонус к опыту: +{view.bonus_pct}%</p>
        <ul className="mt-1 flex flex-col gap-1 text-xs text-ink-mist">
          <li>🏋️ Тренировочная база Академии: +{bonus.academy}%</li>
          <li>🧑‍🏫 Наставник: +{bonus.mentor}%</li>
          <li>⭐ Личный тренер: +{bonus.coach}%</li>
          {!!bonus.deficit && <li>🧭 Дефицитная позиция: +{bonus.deficit}%</li>}
        </ul>
      </section>
      <PotentialCard view={view} p={p} />
      <PositionCard view={view} p={p} onView={onView} toast={toast} fail={fail} />

      <section className="rounded-2xl bg-bg-surface p-3" aria-label="Наставник">
        <div className="flex items-center gap-2">
          <div className="min-w-0 flex-1">
            <p className="font-display text-sm font-bold text-ink-chalk">Наставник</p>
            <p className="truncate text-xs text-ink-mist">
              {view.mentor ? `${view.mentor.name} (${view.mentor.rating}) · +${view.mentor.pct}% опыта` : "Карта «Академии» из твоей коллекции даёт бонус к опыту"}
            </p>
          </div>
          <button onClick={() => setPicking(!picking)} className="shrink-0 rounded-lg bg-bg-raised px-2.5 py-1.5 text-micro text-ink-chalk">
            {picking ? "Свернуть" : view.mentor ? "Сменить" : "Выбрать"}
          </button>
        </div>
        {picking && (
          <div className="mt-2 flex max-h-56 flex-col gap-1 overflow-y-auto">
            {(view.mentor_options ?? []).length === 0 && <p className="text-xs text-ink-mist">Нет карт «Академии» — их дают паки «Академия».</p>}
            {(view.mentor_options ?? []).map((o) => (
              <button key={o.card_id} disabled={mentor.isPending} onClick={() => mentor.mutate(o.card_id)}
                className={`flex items-center gap-2 rounded-xl px-2.5 py-2 text-left ${view.mentor?.card_id === o.card_id ? "bg-path/20 ring-1 ring-path" : "bg-bg-raised"}`}>
                <span className="w-9 font-mono text-micro text-ink-mist">{o.position}</span>
                <span className="min-w-0 flex-1 truncate text-sm text-ink-chalk">{o.name}</span>
                <b className="text-sm text-path">{o.rating}</b>
              </button>
            ))}
            {view.mentor && (
              <button onClick={() => mentor.mutate(null)} className="rounded-xl bg-bg-raised py-2 text-xs text-ink-mist">Убрать наставника</button>
            )}
          </div>
        )}
      </section>

      <section className="grid grid-cols-2 gap-2">
        <div className="flex flex-col rounded-2xl bg-bg-surface p-3">
          <p className="font-display text-sm font-bold text-ink-chalk">Личный тренер</p>
          <p className="flex-1 text-xs text-ink-mist">
            {view.coach?.active ? `До ${new Date(view.coach.until!).toLocaleDateString("ru-RU")}` : `+${view.coach?.pct}% опыта на ${view.coach?.days} дн.`}
          </p>
          <button disabled={coach.isPending} onClick={() => coach.mutate()}
            className="mt-2 rounded-xl bg-amber-400 py-2 text-xs font-bold text-black disabled:opacity-50">
            {view.coach?.active ? "Продлить" : "Нанять"} · ⭐ {view.coach?.stars}
          </button>
        </div>
        <div className="flex flex-col rounded-2xl bg-bg-surface p-3">
          <p className="font-display text-sm font-bold text-ink-chalk">Скаут</p>
          <p className="flex-1 text-xs text-ink-mist">
            {p.potential ? `Потенциал ${"★".repeat(p.potential)} — пик ${p.peak}` : `Узнать потенциал сейчас (сам откроется в U-19). Пик ${view.peak_range[0]}–${view.peak_range[1]}`}
          </p>
          {!p.potential && (
            <button disabled={scout.isPending} onClick={() => scout.mutate()}
              className="mt-2 rounded-xl bg-amber-400 py-2 text-xs font-bold text-black disabled:opacity-50">
              Позвать · ⭐ {view.scout?.stars}
            </button>
          )}
        </div>
      </section>

      {rival && (
        <section className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3" aria-label="Соперник">
          <span className="text-2xl" aria-hidden>🆚</span>
          <div className="min-w-0 flex-1">
            <p className="font-display text-sm font-bold text-ink-chalk">Ровесник-соперник: {rival.name}</p>
            <p className="text-xs text-ink-mist">
              Рейтинг {rival.rating} · {rival.ahead > 0 ? `ты впереди на ${rival.ahead}` : rival.ahead < 0 ? `он впереди на ${-rival.ahead}` : "идёте вровень"}
            </p>
          </div>
        </section>
      )}

      {cohort && (
        <section className="rounded-2xl bg-bg-surface p-3" aria-label="Набор">
          <p className="font-display text-sm font-bold text-ink-chalk">Набор {cohort.key}</p>
          <p className="text-xs text-ink-mist">{cohort.size} воспитанников начали в ту же неделю{cohort.place ? ` · ты ${cohort.place}-й` : ""}</p>
          <ol className="mt-2 flex flex-col gap-1">
            {cohort.top.slice(0, 10).map((e) => (
              <li key={e.user_id} className={`flex items-center gap-2 rounded-lg px-2 py-1 text-xs ${e.me ? "bg-path/15 text-ink-chalk" : "text-ink-mist"}`}>
                <span className="w-5 font-mono">{e.place}</span>
                <span className="min-w-0 flex-1 truncate">{e.name}{e.owner ? <span className="text-ink-mist-dim"> · {e.owner}</span> : null}</span>
                <b className="font-mono">{e.rating}</b>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

function StyleTab({ view, p, onView, toast, fail }: TabProps) {
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const buy = useMutation({
    mutationFn: (item: ProspectShopItem) =>
      item.coins > 0 ? buyProspectCosmetic(item.code) : payWithStars(() => createProspectInvoice(`cos:${item.code}`)),
    onSuccess: (v, item) => {
      if (!v) return;
      onView(v);
      updateBalance(v.balance);
      toast(`${item.emoji} ${item.name} — твоё`);
    },
    onError: fail,
  });
  const equip = useMutation({
    mutationFn: (item: ProspectShopItem) => {
      const on = item.kind === "background" ? p.background === item.code : p.accessory === item.code;
      return equipProspectCosmetic(item.kind, on && item.kind === "accessory" ? null : item.code);
    },
    onSuccess: onView,
    onError: fail,
  });
  const groups: [ProspectShopItem["kind"], string][] = [["background", "Фон карточки"], ["accessory", "Аксессуары"]];
  return (
    <div className="flex flex-col gap-3">
      {groups.map(([kind, title]) => (
        <section key={kind} className="flex flex-col gap-1.5">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">{title}</h2>
          <div className="grid grid-cols-2 gap-2">
            {(view.shop ?? []).filter((i) => i.kind === kind).map((item) => {
              const on = kind === "background" ? p.background === item.code : p.accessory === item.code;
              return (
                <button key={item.code} disabled={buy.isPending || equip.isPending}
                  onClick={() => (item.owned ? equip.mutate(item) : buy.mutate(item))}
                  className={`flex flex-col items-start gap-0.5 rounded-2xl p-3 text-left ${on ? "bg-path/20 ring-1 ring-path" : "bg-bg-surface"}`}>
                  <span className="text-2xl" aria-hidden>{item.emoji}</span>
                  <span className="text-sm font-semibold text-ink-chalk">{item.name}</span>
                  {item.season && !item.owned && <span className="rounded-full bg-sky-400/15 px-1.5 text-micro text-sky-300">сезонное · успей</span>}
                  <span className="text-micro text-ink-mist">
                    {item.owned ? (on ? "Надето" : "Надеть") : item.coins > 0
                      ? <span className="inline-flex items-center gap-0.5">{fmt(item.coins)} <IconCoin size={10} /></span>
                      : `⭐ ${item.stars}`}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      ))}
    </div>
  );
}

function AlbumTab({ view, p }: { view: ProspectView; p: Prospect }) {
  const s = p.stats;
  return (
    <div className="flex flex-col gap-3">
      <section className="grid grid-cols-4 gap-2 text-center">
        <Stat value={String(s.matches ?? 0)} label="матчей" />
        <Stat value={String(s.goals ?? 0)} label="голов" />
        <Stat value={String(s.wins ?? 0)} label="побед" />
        <Stat value={String(s.trainings ?? 0)} label="тренир." />
      </section>
      <section className="flex flex-col gap-1.5" aria-label="Альбом">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Альбом взросления</h2>
        {p.memories.map((m) => (
          <div key={`${m.code}-${m.day}`} className="flex items-center gap-2 rounded-xl bg-bg-surface px-3 py-2">
            <span className="min-w-0 flex-1 text-sm text-ink-chalk">{m.text}</span>
            <span className="shrink-0 font-mono text-micro text-ink-mist">{new Date(m.day).toLocaleDateString("ru-RU")}</span>
          </div>
        ))}
      </section>
      <HallOfGraduates view={view} />
    </div>
  );
}

function Constructor({ view, onSaved, onCancel }: { view: ProspectView; onSaved: (v: ProspectView) => void; onCancel?: () => void }) {
  const existing = view.prospect;
  const [draft, setDraft] = useState<ProspectDraft>(() =>
    existing
      ? { name: existing.name, number: existing.number, foot: existing.foot, appearance: existing.appearance }
      : { name: "", number: 10, foot: "right", appearance: DEFAULT_LOOK },
  );
  const [error, setError] = useState<string | null>(null);
  const setLook = (patch: Partial<MyPlayerAppearance>) => setDraft((d) => ({ ...d, appearance: { ...d.appearance, ...patch, beard: 0 } }));
  const save = useMutation({
    mutationFn: () => (existing ? updateProspect(draft) : createProspect(draft)),
    onSuccess: (v) => { hapticNotify("success"); onSaved(v); },
    onError: (err) => setError(formatGameError(err, "Не получилось сохранить")),
  });
  const canSave = draft.name.trim().length >= 2 && draft.number >= 1 && draft.number <= 99;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">{existing ? "Изменить воспитанника" : "🌱 Новый воспитанник"}</h1>
      {!existing && !!view.graduate && (
        <p className="-mt-2 rounded-xl bg-path/10 px-3 py-2 text-xs text-path">
          🌱 {roman((view.generations ?? 1) + 1)} поколение династии{view.next_dynasty_peak ? `: +${view.next_dynasty_peak} к рейтингу на пике` : ""}.
          {" "}{view.graduate.name} остаётся в «Менеджере».
        </p>
      )}
      {!existing && (
        <p className="-mt-2 text-sm text-ink-mist">
          Ему {view.start_age} лет. Каждые {view.days_per_year} дней — год жизни: двор, детская школа, юноши, U-19 и дебют. Играй за него в «Ответке»,
          тренируй каждый день и принимай решения — к пику (рейтинг {view.peak_range[0]}–{view.peak_range[1]}) он придёт примерно за 100 дней.
        </p>
      )}
      <div className="relative mx-auto flex h-48 w-full items-end justify-center overflow-hidden rounded-2xl bg-bg-surface">
        <img src={existing ? stageScene(existing.stage_code) : PROSPECT_ART.empty} alt="" aria-hidden
          className="pointer-events-none absolute inset-0 h-full w-full object-cover object-top" />
        <span className="pointer-events-none absolute inset-0 bg-gradient-to-t from-bg-base/80 to-transparent" />
        <div className="relative h-full w-36 origin-bottom" style={{ transform: `scale(${GROWTH[existing?.stage ?? 0]})` }}>
          <PlayerAvatar appearance={draft.appearance} number={draft.number} className="h-full w-full" background={false} />
        </div>
      </div>
      <section className="flex flex-col gap-4 rounded-2xl bg-bg-surface p-4">
        <label className="flex flex-col gap-1">
          <span className="text-xs font-semibold text-ink-mist">Имя</span>
          <input value={draft.name} maxLength={20} placeholder="Например, Лёва Мячиков"
            onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
            className="rounded-xl bg-bg-raised px-3 py-2 text-sm text-ink-chalk outline-none" />
        </label>
        <div className="flex gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-ink-mist">Номер</span>
            <input type="number" min={1} max={99} inputMode="numeric" value={draft.number}
              onChange={(e) => setDraft((d) => ({ ...d, number: Math.max(0, Math.min(99, Number(e.target.value) || 0)) }))}
              className="w-20 rounded-xl bg-bg-raised px-3 py-2 text-sm text-ink-chalk outline-none" />
          </label>
          <div className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-ink-mist">Рабочая нога</span>
            <div className="flex gap-1.5">
              {(["right", "left"] as const).map((f) => (
                <button key={f} onClick={() => setDraft((d) => ({ ...d, foot: f }))}
                  className={`rounded-lg px-3 py-2 text-xs font-semibold ${draft.foot === f ? "bg-path text-bg-base" : "bg-bg-raised text-ink-chalk"}`}>
                  {f === "right" ? "Правая" : "Левая"}
                </button>
              ))}
            </div>
          </div>
        </div>
        <p className="rounded-xl bg-bg-raised px-3 py-2 text-xs text-ink-mist">
          🔄 <b className="text-ink-chalk">Позиция: {existing && !existing.universal ? existing.position : "универсал"}.</b>{" "}
          {existing && !existing.universal
            ? `Сменить можно во вкладке «Рост» за ⭐ ${view.position_change?.stars ?? ""}.`
            : `До «${view.stages[2]?.name ?? "Юношей"}» играет везде, а там тренер предложит 2–3 позиции — по тому, что он тренирует, и по талантам. Редкие позиции дают бонус.`}
        </p>
        <Swatches label="Кожа" colors={SKIN_TONES} value={draft.appearance.skin} onChange={(skin) => setLook({ skin })} />
        <Chips label="Причёска" options={HAIR_LABELS} value={draft.appearance.hair} onChange={(hair) => setLook({ hair })} />
        <Swatches label="Цвет волос" colors={HAIR_COLORS} value={draft.appearance.hair_color} onChange={(hair_color) => setLook({ hair_color })} />
        <Swatches label="Глаза" colors={EYE_COLORS} names={EYE_LABELS} value={draft.appearance.eye_color ?? 0} onChange={(eye_color) => setLook({ eye_color })} />
        <Swatches label="Цвет формы" colors={KIT_COLORS} value={draft.appearance.kit} onChange={(kit) => setLook({ kit })} />
        <Chips label="Рисунок" options={KIT_PATTERN_LABELS} value={draft.appearance.kit_pattern} onChange={(kit_pattern) => setLook({ kit_pattern })} />
      </section>
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
      <div className="flex gap-2">
        {onCancel && (
          <button onClick={onCancel} className="flex-1 rounded-2xl bg-bg-surface py-3 text-sm font-semibold text-ink-mist">Отмена</button>
        )}
        <button disabled={!canSave || save.isPending} onClick={() => save.mutate()}
          className="flex-1 rounded-2xl bg-path py-3 text-sm font-bold text-bg-base disabled:opacity-40 active:scale-[0.99]">
          {existing ? "Сохранить" : "Начать путь"}
        </button>
      </div>
    </div>
  );
}

function Swatches({ label, colors, value, onChange, names }: {
  label: string; colors: string[]; value: number; onChange: (i: number) => void; names?: string[];
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-ink-mist">{label}</span>
      <div className="flex flex-wrap gap-2">
        {colors.map((color, i) => (
          <button key={color} aria-label={names?.[i] ?? `${label} ${i + 1}`} onClick={() => onChange(i)}
            className={`h-8 w-8 rounded-full border-2 ${value === i ? "border-path" : "border-white/10"}`} style={{ backgroundColor: color }} />
        ))}
      </div>
    </div>
  );
}

function Chips({ label, options, value, onChange }: { label: string; options: string[]; value: number; onChange: (i: number) => void }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-ink-mist">{label}</span>
      <div className="flex flex-wrap gap-1.5">
        {options.map((option, i) => (
          <button key={option} onClick={() => onChange(i)}
            className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${value === i ? "bg-path text-bg-base" : "bg-bg-raised text-ink-chalk"}`}>
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}
