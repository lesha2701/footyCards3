import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  challengeProspectDuel, chooseProspectSpec, createProspectInvoice, graduateProspect,
  type Prospect, type ProspectDuel, type ProspectFriend, type ProspectGraduate, type ProspectSpec, type ProspectView,
} from "@/api/prospect";
import ShareButton from "@/components/common/ShareButton";
import { IconCoin } from "@/components/icons";
import PlayerAvatar from "@/components/myPlayer/PlayerAvatar";
import { useAuthStore } from "@/store/authStore";

import { PROSPECT_ART } from "@/lib/prospectArt";

import { BACKDROPS, fmt, payWithStars, roman } from "./shared";

/** «Воспитанник Академии» — the life around the child (backend prospect_life):
 * talents, graduation, the week tournament, friends' duels and gifts, the
 * birthday box, the hall of graduates. Every number comes from the view. */

type Ctx = { view: ProspectView; onView: (v: ProspectView) => void; toast: (t: string) => void; fail: (e: unknown) => void };

const EFFECT_LABEL: Record<string, string> = {
  goal_pct: "за голы", win_pct: "за победы", match_pct: "за матч", train_pct: "с тренировок", story_pct: "из историй",
  atk: "к атаке", def: "к защите",
};

function effectsLine(s: ProspectSpec): string {
  return Object.entries(s.effects ?? {})
    .filter(([, v]) => v)
    .map(([k, v]) => (k === "atk" || k === "def" ? `+${v} ${EFFECT_LABEL[k]}` : `+${v}% опыта ${EFFECT_LABEL[k] ?? k}`))
    .join(" · ");
}

// --- «Сегодня»: event cards on top ----------------------------------------------------------

/** The talent pick: three cards, one tap. */
export function SpecPickCard({ view, onView, toast, fail }: Ctx) {
  const pick = view.spec_pick;
  const choose = useMutation({
    mutationFn: (code: string) => chooseProspectSpec(code),
    onSuccess: (v, code) => { onView(v); const s = pick?.options.find((o) => o.code === code); toast(`${s?.emoji} Талант: ${s?.name}`); },
    onError: fail,
  });
  if (!pick) return null;
  return (
    <section className="rounded-2xl border border-path/40 bg-gradient-to-br from-path/15 to-bg-surface p-3" aria-label="Выбор таланта">
      <p className="text-micro uppercase tracking-wider text-path">Новая ступень · талант №{pick.number}</p>
      <p className="font-display text-base font-bold text-ink-chalk">Кем он станет?</p>
      <p className="text-xs text-ink-mist">Выбор навсегда — таланты копятся, по одному на ступень.</p>
      <div className="mt-2 grid grid-cols-3 gap-1.5">
        {pick.options.map((o) => (
          <button key={o.code} disabled={choose.isPending} onClick={() => choose.mutate(o.code)}
            className="flex flex-col items-center gap-1 rounded-xl bg-bg-raised px-1.5 py-2.5 text-center disabled:opacity-50 active:scale-[0.97]">
            <span className="text-2xl" aria-hidden>{o.emoji}</span>
            <span className="text-xs font-bold text-ink-chalk">{o.name}</span>
            <span className="text-micro leading-tight text-ink-mist">{effectsLine(o) || o.about}</span>
          </button>
        ))}
      </div>
    </section>
  );
}

/** «Коробка на день рождения» (Stars), once per age. */
export function BirthdayCard({ view, p, onView, toast, fail }: Ctx & { p: Prospect }) {
  const b = view.bday;
  const open = useMutation({
    mutationFn: () => payWithStars(() => createProspectInvoice("bday")),
    onSuccess: (v) => { if (v) { onView(v); toast(`🎂 Подарок открыт: +${b?.xp} опыта и обновка в «Стиле»`); } },
    onError: fail,
  });
  if (!b?.today || b.opened) return null;
  return (
    <section className="flex items-center gap-3 rounded-2xl border border-pink-400/30 bg-gradient-to-r from-pink-500/15 to-bg-surface p-3" aria-label="День рождения">
      <span className="text-4xl" aria-hidden>🎂</span>
      <div className="min-w-0 flex-1">
        <p className="font-display text-sm font-bold text-ink-chalk">Сегодня {p.name} {p.age}!</p>
        <p className="text-xs text-ink-mist">Коробка с подарком: +{b.xp} опыта и новая вещь в гардероб</p>
      </div>
      <button disabled={open.isPending} onClick={() => open.mutate()}
        className="shrink-0 rounded-xl bg-amber-400 px-3 py-2 text-xs font-bold text-black disabled:opacity-50">
        ⭐ {b.stars}
      </button>
    </section>
  );
}

/** Incoming friend challenges waiting for his match. */
export function IncomingDuels({ view }: { view: ProspectView }) {
  const navigate = useNavigate();
  const due = (view.duels ?? []).filter((d) => d.can_play && d.incoming);
  if (!due.length) return null;
  return (
    <>
      {due.map((d) => (
        <section key={d.id} className="flex items-center gap-3 rounded-2xl border border-red-400/30 bg-gradient-to-r from-red-500/15 to-bg-surface p-3" aria-label="Вызов">
          <span className="text-3xl" aria-hidden>⚔️</span>
          <div className="min-w-0 flex-1">
            <p className="font-display text-sm font-bold text-ink-chalk">{d.friend} вызывает на дуэль</p>
            <p className="truncate text-xs text-ink-mist">{d.friend_prospect ?? "Его воспитанник"} уже ждёт · {leftText(d.expires_at)}</p>
          </div>
          <button onClick={() => navigate(`/play/otvetka?duel=${d.id}`)} className="shrink-0 rounded-xl bg-red-400 px-3 py-2 text-xs font-bold text-black">
            Принять
          </button>
        </section>
      ))}
    </>
  );
}

/** «Выпускной»: the hero card on the last stage. Two taps — it can't be undone. */
export function GraduationCard({ view, p, onView, toast, fail }: Ctx & { p: Prospect }) {
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [sure, setSure] = useState(false);
  const g = view.graduation;
  const go = useMutation({
    mutationFn: graduateProspect,
    onSuccess: (v) => { onView(v); updateBalance(v.balance); toast(`🎓 ${p.name} — выпускник! +${fmt(g?.coins ?? 0)} монет`); },
    onError: (e) => { setSure(false); fail(e); },
  });
  if (!g?.available) return null;
  return (
    <section className="relative overflow-hidden rounded-2xl border border-legend/50 bg-gradient-to-br from-amber-400/25 via-amber-900/20 to-bg-surface p-4" aria-label="Выпускной">
      <span className="pointer-events-none absolute -right-2 -top-3 text-7xl opacity-20" aria-hidden>🎓</span>
      <p className="text-micro uppercase tracking-wider text-legend">Ступень «{g.stage}»</p>
      <p className="font-display text-lg font-bold text-ink-chalk">Выпускной {p.name}</p>
      <ul className="mt-1 flex flex-col gap-0.5 text-xs text-ink-mist">
        <li>🧊 Рейтинг {p.rating} замрёт навсегда — карточка в «Зале выпускников»</li>
        <li>💼 Он останется в «Менеджере» и на трансферах, контракты сохранятся</li>
        <li>
          🎁 Тебе +{fmt(g.coins)} <span className="inline-flex align-middle"><IconCoin size={10} /></span> и место для нового поколения
          {view.next_dynasty_peak ? ` (ему +${view.next_dynasty_peak} к рейтингу на пике)` : ""}
        </li>
      </ul>
      <button disabled={go.isPending} onClick={() => (sure ? go.mutate() : setSure(true))}
        className={`mt-3 w-full rounded-xl py-2.5 text-sm font-bold disabled:opacity-50 ${sure ? "bg-red-400 text-black" : "bg-legend text-black"}`}>
        {sure ? "Точно? Рост остановится навсегда" : "Устроить выпускной"}
      </button>
      {sure && <button onClick={() => setSure(false)} className="mt-1 w-full py-1 text-micro text-ink-mist">Ещё подрастёт</button>}
    </section>
  );
}

/** Other modes he can play (Пенальти / Штрафной / 1 на 1). */
export function OtherModesCard({ view, routes }: { view: ProspectView; routes: { title: string; emoji: string; to: string }[] }) {
  const navigate = useNavigate();
  const x = view.game_xp;
  if (!x || !routes.length) return null;
  return (
    <section className="rounded-2xl bg-bg-surface p-3" aria-label="Другие режимы">
      <p className="font-display text-sm font-bold text-ink-chalk">Ещё режимы</p>
      <p className="text-xs text-ink-mist">Играет он — +{x.match} за игру, +{x.goal} за гол, +{x.win} за победу (в общий дневной лимит)</p>
      <div className="mt-2 grid grid-cols-3 gap-1.5">
        {routes.map((r) => (
          <button key={r.to} onClick={() => navigate(r.to)} className="flex min-h-[52px] flex-col items-center justify-center rounded-xl bg-bg-raised px-1 text-xs font-semibold text-ink-chalk active:scale-[0.98]">
            <span className="text-lg" aria-hidden>{r.emoji}</span>{r.title}
          </button>
        ))}
      </div>
    </section>
  );
}

// --- «Рост»: the week tournament ----------------------------------------------------------

const MEDAL = ["🥇", "🥈", "🥉"];

export function WeekTournament({ view }: { view: ProspectView }) {
  const w = view.week;
  if (!w) return null;
  return (
    <section className="rounded-2xl border border-legend/20 bg-bg-surface p-3" aria-label="Турнир недели">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-display text-sm font-bold text-ink-chalk">🏆 Турнир набора</p>
          <p className="text-xs text-ink-mist">Больше всех опыта за неделю среди {w.size} ровесников · ещё {w.days_left} дн.</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="font-display text-lg font-bold leading-none text-legend">{w.place ? `${w.place}-й` : "—"}</p>
          <p className="text-micro text-ink-mist">{fmt(w.my_xp)} оп.</p>
        </div>
      </div>
      <div className="mt-2 grid grid-cols-3 gap-1.5">
        {w.prizes.map((coins, i) => (
          <div key={i} className="flex items-center justify-center gap-1 rounded-lg bg-black/20 py-1.5 text-xs font-semibold text-ink-chalk">
            {MEDAL[i] ?? `${i + 1}.`} {fmt(coins)} <IconCoin size={10} />
          </div>
        ))}
      </div>
      {w.top.length > 0 ? (
        <ol className="mt-2 flex flex-col gap-1">
          {w.top.map((e) => (
            <li key={e.place} className={`flex items-center gap-2 rounded-lg px-2 py-1 text-xs ${e.me ? "bg-path/15 text-ink-chalk" : "text-ink-mist"}`}>
              <span className="w-5 text-center">{MEDAL[e.place - 1] ?? <span className="font-mono">{e.place}</span>}</span>
              <span className="min-w-0 flex-1 truncate">{e.name}{e.owner ? <span className="text-ink-mist-dim"> · {e.owner}</span> : null}</span>
              <b className="font-mono">{fmt(e.xp)}</b>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mt-2 text-xs text-ink-mist-dim">На этой неделе ещё никто не набрал опыта — стань первым.</p>
      )}
    </section>
  );
}

// --- «Друзья»: duels + gifts --------------------------------------------------------------

function leftText(iso: string): string {
  const h = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3_600_000));
  return h >= 1 ? `осталось ${h} ч` : "меньше часа";
}

function score(r: ProspectDuel["mine"]): string {
  return r ? `${r.for}:${r.against}` : "—";
}

export function FriendsTab({ view, onView, toast, fail, hasProspect }: Ctx & { hasProspect: boolean }) {
  const navigate = useNavigate();
  const [giftFor, setGiftFor] = useState<number | null>(null);
  const friends = view.friends ?? [];
  const duels = view.duels ?? [];
  const rules = view.duel_rules;
  const stars = view.gift_stars;
  const openWith = new Set(duels.filter((d) => d.status === "open").map((d) => d.friend));
  const challenge = useMutation({
    mutationFn: (f: ProspectFriend) => challengeProspectDuel(f.user_id),
    onSuccess: (r) => { onView(r.view); navigate(`/play/otvetka?duel=${r.duel_id}`); },
    onError: fail,
  });
  const gift = useMutation({
    mutationFn: ({ f, kind }: { f: ProspectFriend; kind: "training" | "coach" }) =>
      payWithStars(() => createProspectInvoice(`gift:${kind}:${f.user_id}`)),
    onSuccess: (v, { f }) => { setGiftFor(null); if (v) { onView(v); toast(`🎁 Подарок для ${f.name} отправлен`); } },
    onError: fail,
  });

  return (
    <div className="flex flex-col gap-3">
      {rules && (
        <section className="rounded-2xl bg-gradient-to-r from-red-500/10 to-bg-surface p-3" aria-label="Дуэли">
          <p className="font-display text-sm font-bold text-ink-chalk">⚔️ Дуэль воспитанников</p>
          <p className="text-xs text-ink-mist">
            Вы оба играете свой матч «Ответки», у каждого {rules.hours} ч. Победа, потом разница голов. Победителю +{rules.win_xp} опыта.
            Вызовов в день: {rules.per_day}.
          </p>
        </section>
      )}

      {duels.length > 0 && (
        <section className="flex flex-col gap-1.5" aria-label="Мои дуэли">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Дуэли</h2>
          {duels.map((d) => (
            <div key={d.id} className="flex items-center gap-2 rounded-xl bg-bg-surface px-3 py-2">
              <span className="text-lg" aria-hidden>{d.status === "open" ? "⏳" : d.won === true ? "🏆" : d.won === false ? "😔" : "🤝"}</span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-ink-chalk">{d.incoming ? "от" : "с"} {d.friend}{d.friend_prospect ? ` · ${d.friend_prospect}` : ""}</p>
                <p className="text-micro text-ink-mist">
                  ты {score(d.mine)} · он {d.status === "open" && d.theirs ? "сыграл" : score(d.theirs)}
                  {d.status === "open" ? ` · ${leftText(d.expires_at)}` : d.status === "expired" ? " · время вышло" : ""}
                </p>
              </div>
              {d.can_play ? (
                <button onClick={() => navigate(`/play/otvetka?duel=${d.id}`)} className="shrink-0 rounded-lg bg-red-400 px-2.5 py-1.5 text-micro font-bold text-black">
                  Играть
                </button>
              ) : (
                <span className={`shrink-0 text-micro font-semibold ${d.won === true ? "text-accent-lime" : d.won === false ? "text-red-300" : "text-ink-mist"}`}>
                  {d.status === "open" ? "ждём" : d.won === true ? "победа" : d.won === false ? "поражение" : "ничья"}
                </span>
              )}
            </div>
          ))}
        </section>
      )}

      <section className="flex flex-col gap-1.5" aria-label="Воспитанники друзей">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Воспитанники друзей</h2>
        {friends.length === 0 && (
          <p className="rounded-xl bg-bg-surface px-3 py-3 text-xs text-ink-mist">
            У друзей пока нет воспитанников. Позови их — растить вместе веселее, а дуэли дают опыт.
          </p>
        )}
        {friends.map((f) => (
          <div key={f.user_id} className="rounded-xl bg-bg-surface p-2">
            <div className="flex items-center gap-2">
              <div className="h-12 w-11 shrink-0 overflow-hidden rounded-lg bg-black/20">
                <PlayerAvatar appearance={f.appearance} number={f.number} className="h-full w-full" background={false} />
              </div>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-semibold text-ink-chalk">{f.name}</p>
                <p className="truncate text-micro text-ink-mist">{f.owner} · {f.age} лет</p>
              </div>
              <b className="font-display text-lg text-ink-chalk">{f.rating}</b>
            </div>
            <div className="mt-1.5 grid grid-cols-2 gap-1.5">
              <button disabled={!hasProspect || challenge.isPending || openWith.has(f.owner)} onClick={() => challenge.mutate(f)}
                className="rounded-lg bg-red-400/90 py-1.5 text-micro font-bold text-black disabled:opacity-40">
                {openWith.has(f.owner) ? "Дуэль идёт" : "⚔️ Вызвать"}
              </button>
              <button onClick={() => setGiftFor(giftFor === f.user_id ? null : f.user_id)}
                className="rounded-lg bg-bg-raised py-1.5 text-micro font-semibold text-ink-chalk">
                🎁 Подарить
              </button>
            </div>
            {giftFor === f.user_id && stars && (
              <div className="mt-1.5 grid grid-cols-2 gap-1.5">
                <button disabled={gift.isPending} onClick={() => gift.mutate({ f, kind: "training" })}
                  className="rounded-lg bg-amber-400 px-1 py-1.5 text-micro font-bold text-black disabled:opacity-50">
                  Тренировка · ⭐ {stars.training}
                </button>
                <button disabled={gift.isPending} onClick={() => gift.mutate({ f, kind: "coach" })}
                  className="rounded-lg bg-amber-400 px-1 py-1.5 text-micro font-bold text-black disabled:opacity-50">
                  Личный тренер · ⭐ {stars.coach}
                </button>
              </div>
            )}
          </div>
        ))}
      </section>
    </div>
  );
}

// --- the graduate and the hall -------------------------------------------------------------

export function GraduateCard({ g, compact = false, share = false }: { g: ProspectGraduate; compact?: boolean; share?: boolean }) {
  return (
    <section className={`relative overflow-hidden rounded-3xl border border-legend/40 ${compact ? `bg-gradient-to-b ${BACKDROPS[g.background] ?? BACKDROPS.bg_yard} p-2.5` : "bg-bg-surface p-4"}`}>
      {!compact && (
        <>
          <img src={PROSPECT_ART.graduation} alt="" aria-hidden className="pointer-events-none absolute inset-x-0 top-0 h-[300px] w-full object-cover object-top" />
          <span className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/40 via-transparent via-40% to-bg-surface to-70%" />
        </>
      )}
      <div className="relative flex items-start justify-between">
        <div className="min-w-0">
          <p className="truncate text-micro uppercase tracking-wider text-legend">
            {compact ? `🎓 ${roman(g.generation)} поколение` : `🎓 Выпускник · ${roman(g.generation)} поколение`}
          </p>
          <p className={`truncate font-display font-bold text-ink-chalk ${compact ? "text-sm" : "text-xl"}`}>{g.name}</p>
          <p className="text-xs text-ink-mist">#{g.number} · {g.position}{g.owner ? ` · ${g.owner}` : ""}</p>
        </div>
        <div className="text-right">
          <p className={`font-display font-bold leading-none text-legend ${compact ? "text-2xl" : "text-4xl"}`}>{g.rating}</p>
          <p className="text-micro text-ink-mist">{"★".repeat(g.potential)}</p>
        </div>
      </div>
      {!compact && (
        <>
          <div className="relative mx-auto mt-1 h-40 w-36">
            <PlayerAvatar appearance={g.appearance} number={g.number} className="h-full w-full" background={false} />
          </div>
          {g.specs.length > 0 && (
            <div className="relative mt-1 flex flex-wrap justify-center gap-1">
              {g.specs.map((s) => <span key={s.code} className="rounded-full bg-black/30 px-2 py-0.5 text-micro text-ink-chalk">{s.emoji} {s.name}</span>)}
            </div>
          )}
          <p className="relative mt-2 text-center text-micro text-ink-mist">
            {g.stats.matches ?? 0} матчей · {g.stats.goals ?? 0} голов · {g.stats.wins ?? 0} побед
            {g.graduated_at ? ` · выпуск ${new Date(g.graduated_at).toLocaleDateString("ru-RU")}` : ""}
          </p>
          {share && <ShareButton kind="prospect" id={0} label="Поделиться выпускником" className="relative mt-2" />}
        </>
      )}
    </section>
  );
}

/** The home without a growing child: the active graduate + the next generation. */
export function GraduateHome({ view, onNewGeneration }: { view: ProspectView; onNewGeneration: () => void }) {
  const navigate = useNavigate();
  const g = view.graduate!;
  return (
    <div className="flex flex-col gap-4">
      <GraduateCard g={g} share />
      <section className="rounded-2xl bg-bg-surface p-3" aria-label="Менеджер">
        <p className="font-display text-sm font-bold text-ink-chalk">💼 Взрослая карьера</p>
        <p className="text-xs text-ink-mist">{g.name} играет в «Менеджере» с рейтингом {g.rating}: в твоём клубе или по контракту — и доступен для трансферов.</p>
        <button onClick={() => navigate("/play/manager")} className="mt-2 w-full rounded-xl bg-bg-raised py-2 text-xs font-semibold text-ink-chalk">Открыть «Менеджер»</button>
      </section>
      <section className="relative overflow-hidden rounded-2xl border border-path/40 bg-gradient-to-br from-path/20 to-bg-surface p-4" aria-label="Новое поколение">
        <span className="pointer-events-none absolute -right-1 -top-2 text-6xl opacity-20" aria-hidden>🌱</span>
        <p className="text-micro uppercase tracking-wider text-path">Династия</p>
        <p className="font-display text-lg font-bold text-ink-chalk">Новое поколение · {roman((view.generations ?? 1) + 1)}</p>
        <p className="text-xs text-ink-mist">
          Возьми в Академию следующего воспитанника{view.next_dynasty_peak ? ` — опыт старших даёт ему +${view.next_dynasty_peak} к рейтингу на пике` : ""}.
          Выпускник при этом остаётся в «Менеджере», пока не выпустится следующий.
        </p>
        <button onClick={onNewGeneration} className="mt-3 w-full rounded-xl bg-path py-2.5 text-sm font-bold text-bg-base active:scale-[0.99]">
          Взять нового воспитанника
        </button>
      </section>
      <HallOfGraduates view={view} />
    </div>
  );
}

export function HallOfGraduates({ view }: { view: ProspectView }) {
  const hall = view.hall;
  if (!hall || (!hall.mine.length && !hall.top.length)) return null;
  return (
    <>
      {hall.mine.length > 0 && (
        <section className="flex flex-col gap-1.5" aria-label="Моя династия">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Моя династия</h2>
          <div className="grid grid-cols-2 gap-2">
            {hall.mine.map((g) => (
              <div key={g.id} className={g.status === "retired" ? "opacity-70" : ""}><GraduateCard g={g} compact /></div>
            ))}
          </div>
        </section>
      )}
      {hall.top.length > 0 && (
        <section className="flex flex-col gap-1.5" aria-label="Зал выпускников">
          <div className="relative h-24 overflow-hidden rounded-2xl">
            <img src={PROSPECT_ART.hall} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover object-top" />
            <span className="absolute inset-0 bg-gradient-to-t from-bg-base/90 to-transparent" />
            <h2 className="absolute bottom-2 left-3 font-display text-base font-bold text-ink-chalk">🏛 Зал выпускников</h2>
          </div>
          <ol className="flex flex-col gap-1">
            {hall.top.map((g, i) => (
              <li key={g.id} className="flex items-center gap-2 rounded-xl bg-bg-surface px-2.5 py-1.5">
                <span className="w-6 text-center text-sm">{MEDAL[i] ?? <span className="font-mono text-xs text-ink-mist">{i + 1}</span>}</span>
                <div className="h-9 w-8 shrink-0 overflow-hidden rounded-md bg-black/20">
                  <PlayerAvatar appearance={g.appearance} number={g.number} className="h-full w-full" background={false} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-ink-chalk">{g.name} <span className="text-micro text-ink-mist">{roman(g.generation)}</span></p>
                  <p className="truncate text-micro text-ink-mist">{g.owner} · {g.position}</p>
                </div>
                <b className="font-display text-base text-legend">{g.rating}</b>
              </li>
            ))}
          </ol>
        </section>
      )}
    </>
  );
}
