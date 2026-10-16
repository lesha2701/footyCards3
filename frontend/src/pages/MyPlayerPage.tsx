import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  ackMyPlayerLevelUp,
  changeMyPlayerRole,
  createMyPlayer,
  fetchMyPlayer,
  trainMyPlayer,
  updateMyPlayer,
  type MyPlayer,
  type MyPlayerAppearance,
  type MyPlayerAttr,
  type MyPlayerDraft,
  type MyPlayerView,
} from "@/api/myPlayer";
import EmptyState from "@/components/common/EmptyState";
import ShareButton from "@/components/common/ShareButton";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronRight, IconCoin, IconEdit, IconFlag, IconFlagCheckered, IconHelp, IconProfile, IconStar } from "@/components/icons";
import LevelUpModal from "@/components/myPlayer/LevelUpModal";
import LifestyleTab from "@/components/myPlayer/LifestyleTab";
import MyPlayerCard from "@/components/myPlayer/MyPlayerCard";
import MyPlayerDuels from "@/components/myPlayer/MyPlayerDuels";
import MyPlayerLeaderboard from "@/components/myPlayer/MyPlayerLeaderboard";
import MyPlayerSkillSection from "@/components/myPlayer/MyPlayerSkillSection";
import MyPlayerStyleShop, { type StylePreview } from "@/components/myPlayer/MyPlayerStyleShop";
import PlayerAvatar from "@/components/myPlayer/PlayerAvatar";
import TrainingGame from "@/components/myPlayer/TrainingGame";
import TrainingSection from "@/components/myPlayer/TrainingSection";
import TrophyShowcase from "@/components/myPlayer/TrophyShowcase";
import { formatGameError } from "@/lib/errors";
import {
  ATTR_ORDER,
  BEARD_LABELS,
  EYE_COLORS,
  EYE_LABELS,
  HAIR_COLORS,
  HAIR_LABELS,
  KIT_COLORS,
  KIT_PATTERN_LABELS,
  SKIN_TONES,
  TIER_NAMES,
  TIER_TEXT,
} from "@/lib/myPlayer";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

const LINES: { category: MyPlayer["category"]; label: string; positions: string[] }[] = [
  { category: "GK", label: "Вратарь", positions: ["GK"] },
  { category: "DEF", label: "Защитник", positions: ["LB", "CB", "RB", "LWB", "RWB"] },
  { category: "MID", label: "Полузащитник", positions: ["CDM", "CM", "CAM", "LM", "RM"] },
  { category: "FWD", label: "Нападающий", positions: ["LW", "ST", "RW"] },
];

// Genitive: «до Серебра +6».
const NEXT_TIER = ["Серебра", "Золота", "Легенды"];

type Tab = "progress" | "style" | "property" | "duels" | "rating";
const TABS: [Tab, string][] = [
  ["progress", "Прокачка"], ["style", "Раздевалка"], ["property", "Имущество"], ["duels", "Дуэли"], ["rating", "Рейтинг"],
];

const DEFAULT_LOOK: MyPlayerAppearance = { skin: 1, hair: 1, hair_color: 1, beard: 0, eye_color: 0, kit: 0, kit_pattern: 0 };

export default function MyPlayerPage() {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["my-player"], queryFn: fetchMyPlayer });
  const [editing, setEditing] = useState(false);
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const onSaved = (view: MyPlayerView) => {
    queryClient.setQueryData(["my-player"], view);
    updateBalance(view.balance);
    setEditing(false);
  };

  if (isLoading || !data) return <ListSkeleton />;
  if (!data.enabled) {
    return <EmptyState icon={IconProfile} title="«Мой игрок» скоро вернётся" description="Режим временно выключен." />;
  }
  if (!data.player || editing) {
    return <Constructor view={data} onSaved={onSaved} onCancel={data.player ? () => setEditing(false) : undefined} />;
  }
  return <Overview view={data} player={data.player} onEdit={() => setEditing(true)} onSaved={onSaved} />;
}

// --- overview & training -------------------------------------------------------

function Overview({
  view, player, onEdit, onSaved,
}: { view: MyPlayerView; player: MyPlayer; onEdit: () => void; onSaved: (v: MyPlayerView) => void }) {
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const [evolved, setEvolved] = useState<MyPlayer | null>(null);
  const [tab, setTab] = useState<Tab>("progress");
  const [training, setTraining] = useState(false);
  const [preview, setPreview] = useState<StylePreview>({});
  const [levelInfo, setLevelInfo] = useState(false);
  const [levelUpClosed, setLevelUpClosed] = useState(false);
  const statsRef = useRef<HTMLElement>(null);
  const ackLevel = useMutation({ mutationFn: ackMyPlayerLevelUp, onSuccess: onSaved });
  const closeLevelUp = (spend: boolean) => {
    setLevelUpClosed(true);
    ackLevel.mutate();
    if (spend) {
      setTab("progress");
      setTimeout(() => statsRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }), 150);
    }
  };
  // The hero card wears what is being tried on in «Раздевалка».
  const shown = useMemo(
    () => (tab === "style" ? { ...player, ...preview } : player),
    [player, preview, tab],
  );
  const train = useMutation({
    mutationFn: ({ attr, points }: { attr: MyPlayerAttr; points: number }) => trainMyPlayer(attr, points),
    onSuccess: (next) => {
      setError(null);
      haptic("light");
      if (next.player && next.player.tier !== player.tier) {
        hapticNotify("success");
        setEvolved(next.player);
      }
      onSaved(next);
    },
    onError: (err) => setError(formatGameError(err, "Не получилось")),
  });
  const xpPct = Math.min(100, Math.round((view.xp_into_level / view.xp_for_next) * 100));
  const nextTierIndex = view.next_tier_at != null ? view.tier_thresholds.indexOf(view.next_tier_at) : -1;
  const tierFrom = nextTierIndex > 0 ? view.tier_thresholds[nextTierIndex - 1] : nextTierIndex === 0 ? 40 : player.rating;
  const tierPct = view.next_tier_at != null
    ? Math.max(4, Math.min(100, Math.round(((player.rating - tierFrom) / (view.next_tier_at - tierFrom)) * 100)))
    : 100;
  const fresh = view.freshness;
  const tabDot: Partial<Record<Tab, boolean>> = {
    progress: view.attention.points || view.attention.training,
    property: view.attention.income,
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
          <IconProfile size={20} className="text-accent-lime" />
          Мой игрок
        </h1>
        <button onClick={onEdit} className="flex items-center gap-1 rounded-full bg-bg-surface px-3 py-1.5 text-xs font-semibold text-ink-mist active:scale-95">
          <IconEdit size={14} /> Изменить
        </button>
      </div>

      <div className="mx-auto w-full max-w-[300px]">
        <MyPlayerCard player={shown} level={view.level} size="lg" />
      </div>

      <div className="-mt-1 flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-ink-mist">
            Рамка: <b className={TIER_TEXT[player.tier]}>{TIER_NAMES[player.tier]}</b>
          </span>
          <span className="font-semibold text-ink-chalk">
            {view.next_tier_at != null
              ? `до ${NEXT_TIER[nextTierIndex]} +${view.next_tier_at - player.rating}`
              : view.at_rating_cap ? "максимальная рамка" : "Легенда!"}
          </span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-bg-surface" data-testid="tier-progress">
          <div className="h-full rounded-full bg-gradient-to-r from-accent-cyan to-accent-lime" style={{ width: `${tierPct}%` }} />
        </div>
        <ShareButton kind="my_player" id={0} label="Поделиться карточкой" />
      </div>

      <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1">
        {TABS.map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`relative shrink-0 rounded-full px-3.5 py-2 text-xs font-semibold ${tab === id ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"}`}
          >
            {label}
            {tabDot[id] && tab !== id && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-accent-lime" />}
          </button>
        ))}
      </div>

      {tab === "property" && <LifestyleTab />}
      {tab === "style" && (
        <MyPlayerStyleShop view={view} player={player} preview={preview} onPreview={setPreview} onSaved={onSaved} />
      )}
      {tab === "duels" && <MyPlayerDuels />}
      {tab === "rating" && <MyPlayerLeaderboard />}

      {tab === "progress" && (
        <>
          <section className="rounded-2xl bg-bg-surface p-4">
            <div className="flex items-center justify-between">
              <span className="font-display text-base font-bold text-ink-chalk">Уровень {view.level}</span>
              <span className="flex items-center gap-2">
                <span className="font-mono text-xs text-ink-mist">{view.xp_into_level} / {view.xp_for_next}</span>
                <button
                  aria-label="Как получать опыт"
                  onClick={() => setLevelInfo((v) => !v)}
                  className={`flex h-6 w-6 items-center justify-center rounded-full ${levelInfo ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-mist"}`}
                >
                  <IconHelp size={13} />
                </button>
              </span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-bg-raised">
              <div className="h-full rounded-full bg-floodlight transition-all" style={{ width: `${xpPct}%` }} />
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-1.5 text-caption">
              <span className="rounded-full bg-bg-raised px-2 py-0.5 text-ink-mist">
                Сегодня <b className="text-ink-chalk">{view.xp_today}</b>/{view.xp_daily_cap}
              </span>
              <span className="rounded-full bg-bg-raised px-2 py-0.5 text-ink-mist">+{view.xp_per_reward} за награду</span>
              <span className="rounded-full bg-bg-raised px-2 py-0.5 text-ink-mist">+{view.xp_career_match} за матч</span>
              {view.xp_bonus_pct > 0 && (
                <span className="rounded-full bg-accent-lime/15 px-2 py-0.5 font-semibold text-accent-lime">+{view.xp_bonus_pct}% от имущества</span>
              )}
            </div>
            {levelInfo && (
              <p className="mt-2 rounded-xl bg-bg-raised p-3 text-xs text-ink-mist" data-testid="level-info">
                Опыт идёт за каждую награду в мини-играх, Тактико, Стратего и заданиях (+{view.xp_per_reward}, до {view.xp_daily_cap} в день),
                за матч в «Карьере тренера» (+{view.xp_career_match}), «Футбольном Стратего» (+{view.xp_stratego_match}) и «Карьере игрока»
                (+{view.xp_player_career_match}), если он в составе. Тренировка дня даёт опыт сверх лимита. Каждый уровень — {view.points_per_level}{" "}
                очка характеристик.
              </p>
            )}
          </section>

          {fresh && (
            <section className="rounded-2xl bg-bg-surface p-4" data-testid="freshness">
              <div className="flex items-center justify-between">
                <span className="font-display text-base font-bold text-ink-chalk">Свежесть</span>
                <span className={`font-mono text-sm font-bold ${fresh.value >= 70 ? "text-accent-lime" : fresh.value >= 40 ? "text-amber-300" : "text-red-400"}`}>
                  {fresh.value}%
                </span>
              </div>
              <div className="mt-2 h-2 overflow-hidden rounded-full bg-bg-raised">
                <div
                  className={`h-full rounded-full transition-all ${fresh.value >= 70 ? "bg-accent-lime" : fresh.value >= 40 ? "bg-amber-400" : "bg-red-500"}`}
                  style={{ width: `${fresh.value}%` }}
                />
              </div>
              <p className="mt-2 text-caption text-ink-mist">
                {fresh.penalty > 0 ? `Устал: −${fresh.penalty} к рейтингу в матчах. ` : "Полон сил. "}
                Матч «Карьеры игрока» −{fresh.per_match}, восстановление +{fresh.regen_per_hour} в час
                {fresh.regen_bonus > 0 ? ` (+${fresh.regen_bonus} от имущества)` : ""}, тренировка +{fresh.training}.
              </p>
            </section>
          )}

          <TrainingSection view={view} onSaved={onSaved} onStart={() => setTraining(true)} />

          <section ref={statsRef} className="rounded-2xl bg-bg-surface p-4">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-base font-bold text-ink-chalk">Характеристики</h2>
              <span className={`rounded-full px-2 py-0.5 font-mono text-xs font-bold ${view.points_available ? "bg-accent-lime text-bg-base" : "bg-bg-raised text-ink-mist"}`}>
                очков: {view.points_available}
              </span>
            </div>
            <p className="mt-2 text-caption text-ink-mist">
              Как у всех карточек: атака решает в атакующих эпизодах, защита — в обороне. Рейтинг — среднее двух, 2 очка = +1 к рейтингу.
            </p>
            {view.at_rating_cap && (
              <p className="mt-2 text-xs text-ink-mist">Достигнут потолок рейтинга {view.rating_cap}.</p>
            )}
            <div className="mt-3 flex flex-col gap-2">
              {ATTR_ORDER.map((attr) => {
                const value = player.attributes[attr];
                const canAdd = view.points_available > 0 && !view.at_rating_cap && value < 99 && !train.isPending;
                return (
                  <div key={attr} className="flex items-center gap-3">
                    <span className="w-20 shrink-0">
                      <span className="block text-sm text-ink-chalk">{view.attr_labels[attr]}</span>
                      {player.key_attr === attr && (
                        <span className="block text-micro text-accent-lime">главная для {player.position}</span>
                      )}
                    </span>
                    <span className="h-2 flex-1 overflow-hidden rounded-full bg-bg-raised">
                      <span className="block h-full rounded-full bg-accent-cyan" style={{ width: `${value}%` }} />
                    </span>
                    <span className="w-7 text-right font-mono text-sm font-bold text-ink-chalk">{value}</span>
                    <button
                      aria-label={`+1 ${view.attr_labels[attr]}`}
                      disabled={!canAdd}
                      onClick={() => train.mutate({ attr, points: 1 })}
                      className="h-8 w-8 rounded-lg bg-floodlight font-bold text-bg-base disabled:opacity-30 active:scale-95"
                    >
                      +
                    </button>
                    <button
                      aria-label={`+5 ${view.attr_labels[attr]}`}
                      disabled={!canAdd || view.points_available < 5 || value > 94}
                      onClick={() => train.mutate({ attr, points: 5 })}
                      className="h-8 rounded-lg bg-bg-raised px-2 font-mono text-xs font-bold text-ink-chalk disabled:opacity-30 active:scale-95"
                    >
                      +5
                    </button>
                  </div>
                );
              })}
            </div>
            {error && <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
          </section>

          {view.skill && <MyPlayerSkillSection view={view} skill={view.skill} onSaved={onSaved} />}

          <TrophyShowcase
            trophies={view.trophies}
            emptyHint="Выиграй лигу, стань лучшим бомбардиром или игроком сезона в «Карьере игрока» — кубки появятся здесь."
          />

          <section className="rounded-2xl bg-bg-surface p-4">
            <h2 className="font-display text-base font-bold text-ink-chalk">Где играет</h2>
            <button
              onClick={() => navigate("/play/career")}
              className="mt-3 flex w-full items-center justify-between rounded-xl bg-bg-raised p-3 text-left active:scale-[0.99]"
            >
              <span className="flex items-center gap-2">
                <IconFlagCheckered size={18} className="text-accent-lime" />
                <span>
                  <span className="block text-sm font-semibold text-ink-chalk">Карьера тренера</span>
                  <span className="block text-caption text-ink-mist">Всегда в заявке — поставь его в старт</span>
                </span>
              </span>
              <IconChevronRight size={16} className="text-ink-mist-dim" />
            </button>
            <button
              onClick={() => navigate("/play/player-career")}
              className="mt-2 flex w-full items-center justify-between rounded-xl bg-bg-raised p-3 text-left active:scale-[0.99]"
            >
              <span className="flex items-center gap-2">
                <IconStar size={18} className="text-accent-lime" />
                <span>
                  <span className="block text-sm font-semibold text-ink-chalk">Карьера игрока</span>
                  <span className="block text-caption text-ink-mist">Контракт с клубом, сезоны, голы и трансферы</span>
                </span>
              </span>
              <IconChevronRight size={16} className="text-ink-mist-dim" />
            </button>
            <button
              onClick={() => navigate("/play/stratego/squad")}
              className="mt-2 flex w-full items-center justify-between rounded-xl bg-bg-raised p-3 text-left active:scale-[0.99]"
            >
              <span className="flex items-center gap-2">
                <IconFlag size={18} className="text-accent-lime" />
                <span>
                  <span className="block text-sm font-semibold text-ink-chalk">Футбольное Стратего</span>
                  <span className="block text-caption text-ink-mist">
                    Поставь его на любую роль в «Подготовке» — редкость по рамке «{player.tier_label}»
                  </span>
                </span>
              </span>
              <IconChevronRight size={16} className="text-ink-mist-dim" />
            </button>
            <p className="mt-2 text-caption text-ink-mist-dim">Карточку нельзя продать или обменять — она только твоя. Её видят друзья в твоём профиле.</p>
          </section>
        </>
      )}

      {training && (
        <TrainingGame
          drill={view.training.drill.code}
          name={view.training.drill.name}
          hint={view.training.drill.hint}
          maxHits={view.training.max_hits}
          xpBase={view.training.xp_base}
          xpPerHit={view.training.xp_per_hit}
          onDone={onSaved}
          onClose={() => setTraining(false)}
        />
      )}

      <AnimatePresence>
        {view.level_up && !levelUpClosed && !evolved && !training && (
          <LevelUpModal
            fromLevel={view.level_up.from_level}
            toLevel={view.level_up.to_level}
            points={view.level_up.points}
            onSpend={() => closeLevelUp(true)}
            onClose={() => closeLevelUp(false)}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {evolved && (
          <motion.div
            className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-4 bg-black/80 px-8"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setEvolved(null)}
          >
            <motion.p
              className="flex items-center gap-2 font-display text-lg font-bold text-ink-chalk"
              initial={{ y: -20, opacity: 0 }}
              animate={{ y: 0, opacity: 1 }}
              transition={{ delay: 0.3 }}
            >
              <IconStar size={20} className={TIER_TEXT[evolved.tier]} />
              Новая рамка: <span className={TIER_TEXT[evolved.tier]}>{evolved.tier_label}</span>
            </motion.p>
            <motion.div
              className="w-60"
              initial={{ rotateY: 180, scale: 0.6 }}
              animate={{ rotateY: 0, scale: 1 }}
              transition={{ type: "spring", stiffness: 120, damping: 14 }}
            >
              <MyPlayerCard player={evolved} level={view.level} />
            </motion.div>
            <p className="text-xs text-ink-mist">Нажми, чтобы продолжить</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// --- constructor ------------------------------------------------------------------

type Step = "look" | "kit" | "info";

function Constructor({
  view, onSaved, onCancel,
}: { view: MyPlayerView; onSaved: (v: MyPlayerView) => void; onCancel?: () => void }) {
  const existing = view.player;
  const [step, setStep] = useState<Step>("look");
  const [draft, setDraft] = useState<MyPlayerDraft>(() =>
    existing
      ? { name: existing.name, number: existing.number, position: existing.position, appearance: existing.appearance }
      : { name: "", number: 10, position: "ST", appearance: DEFAULT_LOOK },
  );
  const [error, setError] = useState<string | null>(null);
  const setLook = (patch: Partial<MyPlayerAppearance>) => setDraft((d) => ({ ...d, appearance: { ...d.appearance, ...patch } }));
  const save = useMutation({
    mutationFn: () => (existing ? updateMyPlayer(draft) : createMyPlayer(draft)),
    onSuccess: (next) => {
      hapticNotify("success");
      onSaved(next);
    },
    onError: (err) => setError(formatGameError(err, "Не получилось сохранить")),
  });
  const lines = existing ? LINES.filter((l) => l.category === existing.category) : LINES;
  const canSave = draft.name.trim().length >= 2 && draft.number >= 1 && draft.number <= 99;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">{existing ? "Изменить игрока" : "Создай своего игрока"}</h1>
      {!existing && (
        <p className="-mt-2 text-sm text-ink-mist">
          Собери внешность, выбери позицию — и прокачивай его, играя в любые режимы. Он будет выходить за твою команду в «Карьере тренера» и в «Футбольном Стратего».
        </p>
      )}

      <div className="mx-auto flex h-48 w-40 items-end justify-center overflow-hidden rounded-2xl bg-gradient-to-b from-bg-raised to-bg-surface">
        <PlayerAvatar appearance={draft.appearance} number={draft.number} className="h-full w-full" />
      </div>
      <p className="-mt-2 text-center font-display text-sm font-bold text-ink-chalk">
        {draft.name.trim() || "Без имени"} <span className="text-ink-mist">#{draft.number} · {draft.position}</span>
      </p>

      <div className="grid grid-cols-3 gap-1 rounded-2xl bg-bg-surface p-1">
        {([["look", "Внешность"], ["kit", "Форма"], ["info", "Данные"]] as [Step, string][]).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setStep(id)}
            className={`rounded-xl py-2 text-xs font-semibold ${step === id ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
      </div>

      <section className="flex flex-col gap-4 rounded-2xl bg-bg-surface p-4">
        {step === "look" && (
          <>
            <Swatches label="Кожа" colors={SKIN_TONES} value={draft.appearance.skin} onChange={(skin) => setLook({ skin })} />
            <Chips label="Причёска" options={HAIR_LABELS} value={draft.appearance.hair} onChange={(hair) => setLook({ hair })} />
            <Swatches label="Цвет волос" colors={HAIR_COLORS} value={draft.appearance.hair_color} onChange={(hair_color) => setLook({ hair_color })} />
            <Chips label="Борода" options={BEARD_LABELS} value={draft.appearance.beard} onChange={(beard) => setLook({ beard })} />
            <Swatches
              label="Глаза" colors={EYE_COLORS} names={EYE_LABELS}
              value={draft.appearance.eye_color ?? 0} onChange={(eye_color) => setLook({ eye_color })}
            />
          </>
        )}
        {step === "kit" && (
          <>
            <Swatches label="Цвет формы" colors={KIT_COLORS} value={draft.appearance.kit} onChange={(kit) => setLook({ kit })} />
            <Chips label="Рисунок" options={KIT_PATTERN_LABELS} value={draft.appearance.kit_pattern} onChange={(kit_pattern) => setLook({ kit_pattern })} />
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-ink-mist">Номер</span>
              <input
                type="number" min={1} max={99} inputMode="numeric"
                value={draft.number}
                onChange={(e) => setDraft((d) => ({ ...d, number: Math.max(0, Math.min(99, Number(e.target.value) || 0)) }))}
                className="w-24 rounded-xl bg-bg-raised px-3 py-2 text-sm text-ink-chalk outline-none"
              />
            </label>
          </>
        )}
        {step === "info" && (
          <>
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-ink-mist">Имя на карточке</span>
              <input
                value={draft.name}
                maxLength={20}
                placeholder="Например, А. Иванов"
                onChange={(e) => setDraft((d) => ({ ...d, name: e.target.value }))}
                className="rounded-xl bg-bg-raised px-3 py-2 text-sm text-ink-chalk outline-none"
              />
            </label>
            <div className="flex flex-col gap-2">
              <span className="text-xs font-semibold text-ink-mist">
                Позиция{existing ? " (только в пределах своей линии)" : ""}
              </span>
              {lines.map((line) => (
                <div key={line.category} className="flex flex-wrap items-center gap-1.5">
                  <span className="w-28 text-xs text-ink-mist">{line.label}</span>
                  {line.positions.map((pos) => (
                    <button
                      key={pos}
                      onClick={() => setDraft((d) => ({ ...d, position: pos }))}
                      className={`rounded-lg px-2.5 py-1 font-mono text-xs font-bold ${draft.position === pos ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk"}`}
                    >
                      {pos}
                    </button>
                  ))}
                </div>
              ))}
              {!existing && (
                <p className="text-caption text-ink-mist-dim">
                  Линию (вратарь / защита / полузащита / атака) потом можно сменить только платно — «Смена амплуа».
                </p>
              )}
            </div>
            {existing && view.role_change && <RoleChange view={view} player={existing} onSaved={onSaved} />}
          </>
        )}
      </section>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
      <div className="flex gap-2">
        {onCancel && (
          <button onClick={onCancel} className="flex-1 rounded-2xl bg-bg-surface py-3 text-sm font-semibold text-ink-mist active:scale-[0.99]">
            Отмена
          </button>
        )}
        {step !== "info" && !existing ? (
          <button
            onClick={() => setStep(step === "look" ? "kit" : "info")}
            className="flex-1 rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-[0.99]"
          >
            Дальше
          </button>
        ) : (
          <button
            disabled={!canSave || save.isPending}
            onClick={() => save.mutate()}
            className="flex-1 rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base disabled:opacity-40 active:scale-[0.99]"
          >
            {existing ? "Сохранить" : "Создать игрока"}
          </button>
        )}
      </div>
    </div>
  );
}

function Swatches({
  label, colors, value, onChange, names,
}: { label: string; colors: string[]; value: number; onChange: (i: number) => void; names?: string[] }) {
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs font-semibold text-ink-mist">{label}</span>
      <div className="flex flex-wrap gap-2">
        {colors.map((color, i) => (
          <button
            key={color}
            aria-label={names?.[i] ?? `${label} ${i + 1}`}
            title={names?.[i]}
            onClick={() => onChange(i)}
            className={`h-8 w-8 rounded-full border-2 ${value === i ? "border-accent-lime" : "border-white/10"}`}
            style={{ backgroundColor: color }}
          />
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
          <button
            key={option}
            onClick={() => onChange(i)}
            className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${value === i ? "bg-floodlight text-bg-base" : "bg-bg-raised text-ink-chalk"}`}
          >
            {option}
          </button>
        ))}
      </div>
    </div>
  );
}

/** «Смена амплуа»: move the player to another line for coins or Stars.
 * If the main attribute changes (forward ↔ defender), attack and defense swap. */
function RoleChange({ view, player, onSaved }: { view: MyPlayerView; player: MyPlayer; onSaved: (v: MyPlayerView) => void }) {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starsBusy, setStarsBusy] = useState(false);
  const prices = view.role_change!;
  const coins = useMutation({
    mutationFn: (position: string) => changeMyPlayerRole(position),
    onSuccess: (next) => { hapticNotify("success"); setError(null); onSaved(next); },
    onError: (err) => setError(formatGameError(err, "Не получилось сменить амплуа")),
  });
  const stars = async (position: string) => {
    setError(null);
    setStarsBusy(true);
    try {
      if ((await payMyPlayerWithStars({ purchase: "role", position })) === "paid") {
        hapticNotify("success");
        const next = await queryClient.fetchQuery({ queryKey: ["my-player"], queryFn: fetchMyPlayer });
        onSaved(next);
      }
    } catch (err) {
      setError(formatGameError(err, "Не получилось оплатить"));
    } finally {
      setStarsBusy(false);
    }
  };
  const other = LINES.filter((l) => l.category !== player.category);

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="flex items-center justify-between rounded-xl bg-bg-raised p-3 text-left text-sm font-semibold text-ink-chalk"
      >
        Сменить амплуа (другая линия)
        <IconChevronRight size={16} className="text-ink-mist-dim" />
      </button>
    );
  }
  return (
    <div className="flex flex-col gap-2 rounded-xl bg-bg-raised p-3" data-testid="role-change">
      <p className="text-xs font-semibold text-ink-chalk">Смена амплуа</p>
      <p className="text-caption text-ink-mist">
        Новая линия навсегда (до следующей смены). Если главная характеристика меняется, атака и защита поменяются местами.
      </p>
      {other.map((line) => (
        <div key={line.category} className="flex flex-wrap items-center gap-1.5">
          <span className="w-28 text-xs text-ink-mist">{line.label}</span>
          {line.positions.map((pos) => (
            <button
              key={pos}
              onClick={() => setTarget(pos)}
              className={`rounded-lg px-2.5 py-1 font-mono text-xs font-bold ${target === pos ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-chalk"}`}
            >
              {pos}
            </button>
          ))}
        </div>
      ))}
      {target && (
        <div className="grid grid-cols-2 gap-2">
          {prices.coins_price > 0 && (
            <button
              disabled={coins.isPending || starsBusy}
              onClick={() => coins.mutate(target)}
              className="flex items-center justify-center gap-1 rounded-lg bg-floodlight py-2 text-xs font-bold text-bg-base disabled:opacity-40"
            >
              <IconCoin size={12} /> {prices.coins_price}
            </button>
          )}
          {prices.stars_price > 0 && (
            <button
              disabled={coins.isPending || starsBusy}
              onClick={() => stars(target)}
              className="rounded-lg bg-amber-400 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
            >
              ⭐ {prices.stars_price}
            </button>
          )}
        </div>
      )}
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      <button onClick={() => setOpen(false)} className="text-xs text-ink-mist">Отмена</button>
    </div>
  );
}
