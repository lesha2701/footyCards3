import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { artOf } from "@/lib/gameArt";
import { motion } from "framer-motion";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { fetchMagicHub, startMagicRun } from "@/api/magic";
import { Skeleton } from "@/components/common/Skeleton";
import { IconCoin } from "@/components/icons";
import { EssenceShop } from "@/components/magic/EssenceShop";
import Coach, { type CoachStep } from "@/components/magic/Coach";
import { MagicCollection } from "@/components/magic/MagicCollection";
import { MagicPackOffer } from "@/components/magic/MagicPack";
import { LossWarning, WoundedCard } from "@/components/magic/MagicLosses";
import { MagicRunsCard, MagicSkins } from "@/components/magic/MagicShop";
import { uiArt } from "@/components/magic/art/pngArt";
import { ArtIcon, HeroArt } from "@/components/magic/art/mapObjects";
import StackToken from "@/components/magic/StackToken";
import { DIFFICULTY_TONE, FACTION_THEME, SKIN_CLASS, fmt } from "@/components/magic/magicMeta";
import { formatGameError } from "@/lib/errors";
import { hapticSelection } from "@/lib/telegram";
import { usePersistentState } from "@/lib/usePersistentState";
import { useCoach } from "@/components/magic/useCoach";
import type { MagicDifficultyCode, MagicHeroClassCode, MagicHub, MagicMode, MagicModeCode, MagicFactionCode } from "@/types";

type Tab = "run" | "army" | "cards" | "looks";
const TABS: [Tab, string, string][] = [["run", "⚔️", "Поход"], ["army", "🛡", "Армия"], ["cards", "🃏", "Коллекция"], ["looks", "🎨", "Облик"]];

const days = (n: number) => `${n} ${n % 10 === 1 && n % 100 !== 11 ? "день" : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? "дня" : "дней"}`;

/** The first visit: what the mode is, in a few popups (numbers from the hub, not copy). */
function introSteps(hub: MagicHub): CoachStep[] {
  const m = (code: string) => (hub.modes ?? []).find((x) => x.code === code);
  const quick = m("quick"), hard = m("hardcore"), adv = m("adventure");
  const modes = [
    quick && `«${quick.label}» — ${days(quick.days)} против героя-соперника`,
    hard && `«${hard.label}» — огромная карта и ${days(hard.days)}`,
    adv && `«${adv.label}» — ${days(adv.days)} без соперника и босс Безликий в конце`,
  ].filter(Boolean).join("; ");
  return [
    { icon: "⚽", title: "Мяч и Магия", text: "Ты — герой-тренер. Ведёшь армию волшебных существ по карте, громишь лагеря, собираешь сундуки, а в конце похода выходишь на финальную битву." },
    { icon: "✨", title: "Армия — это карты", text: `Существа — карты твоей коллекции. Открой «Магический пак» (${hub.creature_pack?.size ?? ""} карт): он всегда сверху на этом экране и в магазине.`.replace(" ()", "") },
    { icon: "🎖", title: "Капитаны — футболисты", text: "Каждый отряд ведёт твой футболист: рейтинг даёт атаку и защиту, позиция — особую черту, редкость — до какого уровня существ он дотягивается." },
    { icon: "🪄", title: "Раса и класс", text: "Раса героя даёт заклинания, класс — ману, силу магии и шаги по карте. Армию можно собрать из существ любых рас." },
    { icon: "🗺️", title: "Режимы", text: modes ? `${modes}.` : "Выбери режим похода: короткий, хардкор или большое приключение." },
    { icon: "⚠️", title: "Береги армию", text: "Павшие в бою уходят из коллекции: часть навсегда (за них дают эссенцию), остальные ранены на сутки. Слабую армию в сильный лагерь не веди." },
    { icon: "⚔️", title: "В поход!", text: "Выбери расу, класс и режим — и жми «Выступить в поход». Эти подсказки снова откроются кнопкой «?» в шапке." },
  ];
}

/** Under a mode's card: its own runs left today. */
function RunsLine({ m }: { m: MagicMode }) {
  const free = m.free_left ?? 0;
  const bank = m.bank ?? 0;
  const tone = free + bank > 0 ? "text-emerald-300" : "text-ink-mist-dim";
  return (
    <p className={`mt-0.5 text-[10px] font-bold ${tone}`}>
      🎟 {free + bank > 0 ? `сегодня: ${free} бесплатно${bank ? ` + ${bank} куплено` : ""}` : m.price_coins != null ? `+1 за ${m.price_coins} монет` : m.price_stars != null ? `+1 за ${m.price_stars} ⭐` : "на сегодня всё"}
    </p>
  );
}

/** A step of the run setup: a number, the title and what the choice gives. */
function Label({ n, hint, children }: { n?: number; hint?: string; children: ReactNode }) {
  return (
    <div className="mb-1.5 flex items-center gap-2">
      {n && (
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-amber-300 to-amber-500 font-display text-[11px] font-black text-black shadow-[0_0_10px_rgba(251,191,36,0.35)]">{n}</span>
      )}
      <p className="font-display text-[13px] font-black uppercase tracking-wide text-ink-chalk">{children}</p>
      {hint && <p className="ml-auto truncate text-[10px] text-ink-mist">{hint}</p>}
      <span className="h-px min-w-4 flex-1 bg-gradient-to-r from-white/15 to-transparent" />
    </div>
  );
}

/** «Мяч и Магия»: four tabs — the run setup (start pinned at the bottom), the army,
 *  the creature collection and packs, the hero / castle looks. */
export default function MagicPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [faction, setFaction] = usePersistentState<MagicFactionCode>("magic.faction", "dawn");
  const [difficulty, setDifficulty] = usePersistentState<MagicDifficultyCode>("magic.difficulty", "normal");
  const [mode, setMode] = usePersistentState<MagicModeCode>("magic.mode", "quick");
  const [heroClass, setHeroClass] = usePersistentState<MagicHeroClassCode>("magic.heroClass", "knight");
  const [tab, setTab] = usePersistentState<Tab>("magic.tab", "run");
  const [rules, setRules] = useState(false);
  const intro = useCoach("magic_coach_hub_v1");
  const [error, setError] = useState<string | null>(null);
  const { data: hub } = useQuery({ queryKey: ["magic-hub"], queryFn: fetchMagicHub });

  const start = useMutation({
    mutationFn: (challenge: boolean = false) => startMagicRun(faction, difficulty, mode, challenge, heroClass),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["magic-hub"] });
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      queryClient.setQueryData(["magic-run", run.id], run);
      navigate(`/play/magic/runs/${run.id}`);
    },
    onError: (err) => setError(formatGameError(err, "Не получилось начать поход")),
  });

  if (!hub) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-24 w-full rounded-3xl" />
        <Skeleton className="h-10 w-full rounded-2xl" />
        <div className="grid grid-cols-2 gap-2"><Skeleton className="h-40 rounded-3xl" /><Skeleton className="h-40 rounded-3xl" /></div>
      </div>
    );
  }
  const f = hub.factions.find((x) => x.code === faction) ?? hub.factions[0];
  const hero = hub.hero;
  const xpPct = hero.next_level_xp ? Math.round(((hero.xp - hero.level_start) / (hero.next_level_xp - hero.level_start)) * 100) : 100;
  const diff = hub.difficulties.find((d) => d.code === difficulty) ?? hub.difficulties[1];
  const modes = hub.modes ?? [];
  const md = modes.find((m) => m.code === mode) ?? modes[0];
  const modePct = md?.reward_pct ?? 100;
  const lead = hub.leadership_by_class?.[heroClass] ?? hub.leadership ?? 0;
  const cls = (hub.hero_classes ?? []).find((c) => c.code === heroClass);
  let armyUsed = 0;
  const armyRows = hub.army.map((s) => {
    armyUsed += s.cost;
    return { s, unruly: armyUsed > lead };
  });
  const winCoins = Math.round((hub.reward_win * diff.reward_pct * modePct) / 10000);
  const lossCoins = Math.round((hub.reward_loss * diff.reward_pct * modePct) / 10000);
  // Every mode has its own runs of the day (free, then bought for that mode).
  const runsLeft = (m: typeof md) => (m ? (m.free_left ?? 0) + (m.bank ?? 0) : hub.free_left + hub.bonus_runs);
  const enoughRuns = runsLeft(md) > 0;
  const challengeLeft = hub.challenge_left ?? 1;
  const canStart = hub.enabled && hub.army.length > 0 && !start.isPending && !hub.active_run_id && enoughRuns;
  const hard = md?.code === "hardcore";
  const leadIcon = uiArt("icon_leadership");

  return (
    <div className="flex flex-col gap-3 pb-2">
      {/* Banner: the title, the hero's level and XP. */}
      <header className="relative min-h-[112px] overflow-hidden rounded-3xl p-3 ring-1 ring-indigo-300/20"
        style={{ background: "radial-gradient(circle at 80% 10%, rgba(250,204,21,0.25), transparent 40%), radial-gradient(circle at 10% 90%, rgba(239,68,68,0.25), transparent 45%), linear-gradient(160deg, #1e1b4b 0%, #0f172a 55%, #052e16 100%)" }}>
        <div className="pointer-events-none absolute -bottom-4 right-6 h-32 w-32 drop-shadow-[0_6px_14px_rgba(0,0,0,0.6)]">
          <div className="absolute inset-x-4 bottom-4 h-6 rounded-full bg-amber-300/25 blur-md" />
          <ArtIcon size={128} tight><HeroArt faction={faction} skin={SKIN_CLASS[hub.hero_skin] === heroClass ? hub.hero_skin : "default"} heroClass={heroClass} /></ArtIcon>
        </div>
        <button onClick={() => { hapticSelection(); intro.show(); }} aria-label="Как играть"
          className="absolute right-2 top-2 z-10 flex h-7 w-7 items-center justify-center rounded-full bg-black/40 text-sm font-black text-amber-200 ring-1 ring-amber-200/30 active:scale-90">?</button>
        <div className="relative flex items-center gap-3 pr-28">
          {artOf("magic") ? (
            <img src={artOf("magic")} alt="" className="h-12 w-12 shrink-0 rounded-xl object-cover ring-1 ring-amber-200/40" />
          ) : (
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-amber-300 via-fuchsia-500 to-indigo-700 text-3xl">⚽</div>
          )}
          <div className="min-w-0 flex-1">
            <h1 className="font-display text-xl font-black leading-none text-ink-chalk">Мяч и Магия</h1>
            <div className="mt-1.5 flex items-center gap-2">
              <span className="font-display text-[11px] font-black text-amber-200">ур. {hero.level}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-black/40">
                <motion.div className="h-full rounded-full bg-gradient-to-r from-amber-300 to-fuchsia-400" initial={{ width: 0 }} animate={{ width: `${xpPct}%` }} />
              </div>
              <span className="font-mono text-[9px] text-ink-mist">{hero.next_level_xp ? `${fmt(hero.xp)}/${fmt(hero.next_level_xp)}` : "макс."}</span>
            </div>
          </div>
        </div>
        <div className="relative mt-2 flex flex-wrap gap-1 pr-28 text-[10px]">
          <span className="rounded-full bg-black/35 px-2 py-0.5 text-ink-chalk">🏆 {hub.wins} побед</span>
          <span className="rounded-full bg-black/35 px-2 py-0.5 text-ink-chalk">📈 {hub.rating}{hub.rank ? ` · #${hub.rank}` : ""}</span>
          <button onClick={() => setTab("army")} className="rounded-full bg-cyan-400/15 px-2 py-0.5 text-cyan-100">💠 {hub.essence ?? 0} эссенции</button>
          {(hub.wounded ?? []).length > 0 && (
            <button onClick={() => setTab("army")} className="rounded-full bg-red-500/20 px-2 py-0.5 text-red-100">
              🩹 раненых: {(hub.wounded ?? []).reduce((n, w) => n + w.count, 0)}
            </button>
          )}
        </div>
      </header>

      {/* Tabs: a grid, every tab visible. */}
      <nav className="sticky top-0 z-30 -mx-1 grid grid-cols-4 gap-1 rounded-2xl bg-bg-base p-1">
        {TABS.map(([k, icon, label]) => (
          <button key={k} onClick={() => { hapticSelection(); setTab(k); }}
            className={`flex flex-col items-center rounded-xl py-1.5 text-[11px] font-bold active:scale-95 ${tab === k ? "bg-gradient-to-b from-amber-300 to-amber-500 text-black shadow-[0_0_14px_rgba(251,191,36,0.35)]" : "bg-white/5 text-ink-mist"}`}>
            <span className="text-base leading-none">{icon}</span>{label}
          </button>
        ))}
      </nav>

      {!hub.enabled && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">Режим сейчас выключен.</p>}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {hub.active_run_id && (
        <button onClick={() => navigate(`/play/magic/runs/${hub.active_run_id}`)}
          className="rounded-2xl bg-gradient-to-r from-amber-400 to-orange-500 px-4 py-3 text-left font-display text-base font-black text-black shadow-[0_0_24px_rgba(251,191,36,0.4)] active:scale-[0.98]">
          ▶ Продолжить поход
          <span className="block text-caption font-semibold text-black/70">Герой ждёт на карте</span>
        </button>
      )}

      {tab !== "cards" && (
        <MagicPackOffer hub={hub} look="strip"
          note={hub.army.length === 0 ? "Армии пока нет — открой пак, чтобы выступить" : undefined} />
      )}

      {tab === "run" && (
        <>
          {/* Faction */}
          <section>
            <Label n={1} hint="даёт заклинания">Раса героя</Label>
            <div className="grid grid-cols-2 gap-2">
              {hub.factions.map((x) => {
                const t = FACTION_THEME[x.code];
                const on = x.code === faction;
                const emblem = uiArt(`emblem_${x.code}`);
                return (
                  <button key={x.code} onClick={() => { hapticSelection(); setFaction(x.code); }}
                    className={`relative flex items-center gap-2 overflow-hidden rounded-2xl p-2.5 text-left ring-1 transition ${t.card} ${on ? `${t.ring} ring-2 ${t.glow}` : "ring-white/10 opacity-60"}`}>
                    {emblem ? <img src={emblem} alt="" className="h-10 w-10 shrink-0" /> : <span className="text-3xl">{x.emoji}</span>}
                    <span className="min-w-0">
                      <span className={`block font-display text-sm font-black leading-tight ${t.text}`}>{x.name}</span>
                      <span className="line-clamp-2 block text-[9px] leading-tight text-ink-mist">{x.tagline}</span>
                    </span>
                  </button>
                );
              })}
            </div>
            <div className="mt-1.5 grid grid-cols-3 gap-1">
              {f.spells.map((s) => (
                <div key={s.code} className={`rounded-xl bg-black/25 px-1.5 py-1 ${hero.level < s.level ? "opacity-45" : ""}`}>
                  <p className="truncate text-[10px] font-bold leading-tight text-ink-chalk">🪄 {s.name}</p>
                  <p className="font-mono text-[9px] text-indigo-200">{s.cost} маны{hero.level < s.level ? ` · ур. ${s.level}` : ""}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Hero class */}
          {(hub.hero_classes ?? []).length > 0 && (
            <section>
              <Label n={2} hint="мана, магия и шаги">Класс</Label>
              <div className="grid grid-cols-3 gap-2">
                {(hub.hero_classes ?? []).map((c) => {
                  const on = c.code === heroClass;
                  const skin = SKIN_CLASS[hub.hero_skin] === c.code ? hub.hero_skin : "default";
                  const icon = uiArt(`class_${c.code}`);
                  return (
                    <button key={c.code} onClick={() => { hapticSelection(); setHeroClass(c.code); }}
                      className={`relative flex flex-col items-center rounded-2xl bg-bg-surface p-1.5 text-center ring-1 transition ${on ? "ring-2 ring-amber-300 shadow-[0_0_18px_rgba(251,191,36,0.25)]" : "ring-white/10 opacity-60"}`}>
                      <ArtIcon size={64} tight><HeroArt faction={faction} skin={skin} heroClass={c.code} /></ArtIcon>
                      {icon && <img src={icon} alt="" className="absolute left-1 top-1 h-6 w-6 drop-shadow" />}
                      <p className="font-display text-xs font-black text-ink-chalk">{icon ? "" : `${c.emoji} `}{c.name}</p>
                      <p className="font-mono text-[9px] text-indigo-200">🔮{c.mana} ✨{c.spell_power} 👣{c.moves}</p>
                    </button>
                  );
                })}
              </div>
              {cls && <p className="mt-1 text-center text-[10px] text-ink-mist">{cls.tagline}</p>}
            </section>
          )}

          {/* Mode */}
          {modes.length > 1 && (
            <section>
              <Label n={3} hint="у каждого свои походы">Режим</Label>
              <div className="grid grid-cols-2 gap-1.5">
                {modes.map((m) => {
                  const on = m.code === md?.code;
                  const h = m.code === "hardcore";
                  if (m.code === "adventure") {
                    return (
                      <button key={m.code} onClick={() => { hapticSelection(); setMode(m.code); }}
                        className={`col-span-2 rounded-2xl px-2.5 py-2 text-left ring-1 ${on ? "bg-gradient-to-br from-violet-900/70 to-indigo-900/40 ring-violet-400" : "bg-bg-surface ring-white/5"}`}>
                        <p className="font-display text-sm font-black text-ink-chalk">🗺️ {m.label} <span className="text-[10px] font-bold text-violet-300">новое</span></p>
                        <p className="text-[10px] leading-snug text-ink-mist">
                          Огромная карта, {days(m.days)} без соперника: собирай силу, а в конце — босс Безликий
                        </p>
                        <p className="text-[10px] font-black text-violet-300">Награда ×{m.reward_pct / 100} · гибнет половина павших · армия отдыхает по ночам</p>
                        <RunsLine m={m} />
                      </button>
                    );
                  }
                  return (
                    <button key={m.code} onClick={() => { hapticSelection(); setMode(m.code); }}
                      className={`rounded-2xl px-2.5 py-2 text-left ring-1 ${on ? (h ? "bg-gradient-to-br from-red-900/70 to-orange-900/40 ring-orange-400" : "bg-white/10 ring-amber-300") : "bg-bg-surface ring-white/5"}`}>
                      <p className="font-display text-sm font-black text-ink-chalk">{h ? "🔥" : "⚡"} {m.label}</p>
                      <p className="text-[10px] leading-snug text-ink-mist">{h ? `Огромная карта, ${days(m.days)}` : `${days(m.days)}, ${m.moves ?? 13} шагов в день`}</p>
                      <p className={`text-[10px] font-black ${h ? "text-orange-300" : "text-amber-200"}`}>
                        {h ? `Награда ×${m.reward_pct / 100} · павшие гибнут все` : "Награда ×1 · гибнет половина павших"}
                      </p>
                      <RunsLine m={m} />
                    </button>
                  );
                })}
              </div>
            </section>
          )}

          {/* Difficulty */}
          <section>
            <Label n={4} hint="награда и рейтинг">Сложность</Label>
            <div className="grid grid-cols-3 gap-1.5">
              {hub.difficulties.map((d) => (
                <button key={d.code} onClick={() => { hapticSelection(); setDifficulty(d.code); }}
                  className={`rounded-2xl px-2 py-1.5 text-center ring-1 ${d.code === difficulty ? "bg-white/10 ring-amber-300" : "bg-bg-surface ring-white/5"}`}>
                  <p className={`font-display text-sm font-black ${DIFFICULTY_TONE[d.code]}`}>{d.label}</p>
                  <p className="flex items-center justify-center gap-0.5 text-micro text-ink-chalk">
                    {Math.round((hub.reward_win * d.reward_pct * modePct) / 10000)} <IconCoin size={10} />
                  </p>
                  <p className="text-[9px] text-ink-mist">+{d.rating_win} рейт.{d.pack_chance_pct ? ` · пак ${d.pack_chance_pct}%` : ""}</p>
                </button>
              ))}
            </div>
          </section>

          {!hub.active_run_id && <MagicRunsCard hub={hub} mode={md} />}

          {hub.challenge && (
            <section className="rounded-3xl bg-gradient-to-br from-amber-500/20 via-bg-surface to-fuchsia-600/15 p-3 ring-1 ring-amber-300/30">
              <div className="flex items-center justify-between">
                <p className="font-display text-sm font-black text-ink-chalk">🏆 Испытание недели</p>
                <span className="text-[10px] text-ink-mist">до {new Date(hub.challenge.ends_at).toLocaleDateString("ru-RU", { day: "numeric", month: "short" })}</span>
              </div>
              <p className="mt-0.5 text-[11px] text-ink-mist">Одна и та же карта у всех, средняя сложность. Лучший счёт — в таблицу. Потери армии — как в обычном походе.</p>
              {hub.challenge.top.length > 0 ? (
                <div className="mt-2 flex flex-col gap-0.5">
                  {hub.challenge.top.slice(0, 5).map((r) => (
                    <p key={r.rank} className={`flex justify-between rounded-lg px-2 py-0.5 text-xs ${r.me ? "bg-amber-300/20 font-bold text-amber-100" : "text-ink-chalk"}`}>
                      <span>{r.rank}. {r.name}</span><span className="font-mono">{r.score}</span>
                    </p>
                  ))}
                </div>
              ) : (
                <p className="mt-2 text-xs text-ink-mist">Пока никто не прошёл — будь первым!</p>
              )}
              <button disabled={!hub.enabled || !hub.army.length || start.isPending || !!hub.active_run_id || challengeLeft <= 0}
                onClick={() => { hapticSelection(); setError(null); start.mutate(true); }}
                className="mt-2 w-full rounded-2xl bg-amber-400 py-2.5 text-sm font-black text-black active:scale-[0.98] disabled:opacity-40">
                {challengeLeft <= 0 ? "Попытка на сегодня сыграна" : hub.challenge.best !== null ? `Улучшить рекорд (${hub.challenge.best})` : "Принять испытание"}
              </button>
            </section>
          )}

          <section className="rounded-3xl bg-bg-surface p-3">
            <button onClick={() => setRules(!rules)} className="flex w-full items-center justify-between text-xs font-bold text-ink-chalk">
              📜 Как играть <span className="text-ink-mist">{rules ? "▲" : "▼"}</span>
            </button>
            {rules && (
              <>
              <button onClick={() => { hapticSelection(); intro.show(); }}
                className="mt-2 w-full rounded-xl bg-amber-400/15 py-2 text-xs font-bold text-amber-200 ring-1 ring-amber-300/30 active:scale-[0.98]">
                ✨ Показать вступление ещё раз
              </button>
              <ul className="mt-2 flex list-disc flex-col gap-1 pl-4 text-caption text-ink-mist">
                <li>Поход длится {md?.days ?? hub.days} дней, в день у героя до {hub.moves_per_day} шагов. Карта каждый раз новая и скрыта туманом.</li>
                <li>Нажми место на карте — увидишь путь и что там, затем «Идти». Карту двигай пальцем.</li>
                <li>Сундук: золото или опыт. Золото — на рынок (наём отрядов), остаток в конце станет монетами.</li>
                <li>Источники маны, артефакты, трибуна (пополняет павших) и подкрепление — забирай раньше соперника.</li>
                <li>Лагеря монстров (★) — бой. В конце последнего дня — финальная битва с героем-соперником.</li>
                <li>Армия — существа из твоей коллекции. Павшие уходят из коллекции: в обычном походе половина навсегда (за них эссенция), остальные ранены на сутки; в хардкоре гибнут все павшие.</li>
                <li>Опыт героя = очки похода. С уровнем растут мана, сила магии и лидерство.</li>
                <li>У каждого режима свои походы на день: бесплатные, потом один за монеты и ещё за звёзды.</li>
              </ul>
              </>
            )}
          </section>

          {hub.top.length > 0 && (
            <section className="rounded-3xl bg-bg-surface p-3">
              <div className="mb-1.5 flex items-center justify-between">
                <p className="text-xs font-bold text-ink-chalk">🏆 Таблица недели</p>
                <button onClick={() => navigate("/ranking?metric=magic_rating")} className="text-micro text-ink-mist">Вся таблица →</button>
              </div>
              {hub.top.map((e) => (
                <div key={e.user_id} className="flex items-center gap-2 py-0.5 text-caption">
                  <span className="w-5 font-mono text-ink-mist">{e.rank}</span>
                  <span className="min-w-0 flex-1 truncate text-ink-chalk">{e.display_name}</span>
                  <span className="font-mono font-bold text-amber-200">{e.value}</span>
                </div>
              ))}
            </section>
          )}

          {/* The start, pinned above the bottom menu: always in reach. */}
          {!hub.active_run_id && (
            <div className="sticky bottom-24 z-20 -mx-1 flex flex-col gap-1.5 rounded-3xl bg-bg-base/95 p-2 shadow-[0_-8px_30px_rgba(0,0,0,0.5)] ring-1 ring-white/10">
              <LossWarning risk={hub.risk} mode={md?.code ?? "quick"} compact />
              <button disabled={!canStart} onClick={() => { hapticSelection(); setError(null); start.mutate(false); }}
                className={`rounded-2xl py-3 font-display text-lg font-black text-white active:scale-[0.98] disabled:opacity-40 ${hard ? "bg-gradient-to-r from-red-600 via-orange-500 to-amber-500 shadow-[0_0_24px_rgba(249,115,22,0.45)]" : "bg-gradient-to-r from-fuchsia-500 via-indigo-500 to-sky-500 shadow-[0_0_24px_rgba(129,140,248,0.45)]"}`}>
                <span className="flex items-center justify-center gap-2">
                  {start.isPending ? "Собираем армию…" : hard ? "🔥 Хардкор-поход" : "Выступить в поход"}
                  {!start.isPending && (uiArt(`emblem_${f.code}`) ? <img src={uiArt(`emblem_${f.code}`)!} alt="" className="h-7 w-7 object-contain" /> : f.emoji)}
                </span>
              </button>
              <p className="text-center text-[10px] text-ink-mist">
                {cls?.name ?? ""} · {diff.label.toLowerCase()} · победа {winCoins}, поражение {lossCoins} <IconCoin size={9} />
                {!hub.army.length ? " · нет существ в армии" : !enoughRuns ? ` · ${md?.label ?? "режим"}: походы на сегодня закончились` : ` · ${md?.label ?? "режим"}: ещё ${runsLeft(md)} сегодня`}
              </p>
            </div>
          )}
        </>
      )}

      {tab === "army" && (
        <>
          <section className="rounded-3xl bg-bg-surface p-3">
            <div className="mb-2 flex items-center justify-between">
              <p className="flex items-center gap-1 text-xs font-bold text-ink-chalk">
                {leadIcon ? <img src={leadIcon} alt="" className="h-5 w-5" /> : "👑"} Армия · лидерство {armyUsed}/{lead}
              </p>
              <button onClick={() => navigate("/play/magic/army")} className="rounded-full bg-amber-400 px-3 py-1 text-micro font-black text-black active:scale-95">Изменить</button>
            </div>
            {hub.army.length === 0 ? (
              <p className="text-caption text-ink-mist">Нужна хотя бы одна карта существа — открой магический пак.</p>
            ) : (
              <div className="grid grid-cols-5 gap-1">
                {armyRows.map(({ s, unruly }) => (
                  <div key={s.unit} className={`flex flex-col items-center gap-1.5 ${unruly ? "opacity-60" : ""}`}>
                    <StackToken unit={s.unit} tier={s.tier} count={unruly === s.unruly ? s.count : unruly ? Math.max(1, Math.floor(s.count / 2)) : Math.min(s.have, s.count * 2)} image={s.captain?.image_path} size={50} />
                    <span className="mt-0.5 w-full truncate text-center text-[9px] font-bold text-ink-chalk">{s.name}</span>
                    <span className={`-mt-1.5 w-full truncate text-center text-[8px] ${unruly ? "text-red-300" : "text-ink-mist-dim"}`}>
                      {unruly ? "не слушается" : s.captain ? `🎖 ${s.captain.name}` : "без капитана"}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <p className="mt-2 text-micro text-ink-mist-dim">Капитан-футболист даёт рейтинг → атаку и защиту, позиция → черту, редкость — до какого уровня существ он ведёт. Сверх лидерства отряд не слушается и идёт вполсилы.</p>
          </section>
          <LossWarning risk={hub.risk} mode={md?.code ?? "quick"} />
          <WoundedCard hub={hub} />
          <EssenceShop faction={faction} />
        </>
      )}

      {tab === "cards" && <MagicCollection hub={hub} />}

      {tab === "looks" && <MagicSkins faction={faction} heroClass={heroClass} />}

      <Coach fixed open={intro.open} steps={introSteps(hub)} onClose={intro.close} />
    </div>
  );
}
