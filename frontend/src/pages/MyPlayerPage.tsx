import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import {
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
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronRight, IconEdit, IconFlagCheckered, IconProfile, IconStar } from "@/components/icons";
import LifestyleTab from "@/components/myPlayer/LifestyleTab";
import MyPlayerCard from "@/components/myPlayer/MyPlayerCard";
import MyPlayerLeaderboard from "@/components/myPlayer/MyPlayerLeaderboard";
import MyPlayerSkillSection from "@/components/myPlayer/MyPlayerSkillSection";
import MyPlayerStyleShop from "@/components/myPlayer/MyPlayerStyleShop";
import PlayerAvatar from "@/components/myPlayer/PlayerAvatar";
import TrainingGame from "@/components/myPlayer/TrainingGame";
import TrainingSection from "@/components/myPlayer/TrainingSection";
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
  TIER_TEXT,
} from "@/lib/myPlayer";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

const LINES: { category: MyPlayer["category"]; label: string; positions: string[] }[] = [
  { category: "GK", label: "Вратарь", positions: ["GK"] },
  { category: "DEF", label: "Защитник", positions: ["LB", "CB", "RB"] },
  { category: "MID", label: "Полузащитник", positions: ["CDM", "CM", "CAM", "LM", "RM"] },
  { category: "FWD", label: "Нападающий", positions: ["LW", "ST", "RW"] },
];

const TIER_NAMES = ["Серебро", "Золото", "Легенда"];

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
  const [tab, setTab] = useState<"progress" | "style" | "property" | "rating">("progress");
  const [training, setTraining] = useState(false);
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

      <div className="mx-auto w-56">
        <MyPlayerCard player={player} level={view.level} />
      </div>

      <div className="grid grid-cols-4 gap-1 rounded-2xl bg-bg-surface p-1">
        {([["progress", "Прокачка"], ["style", "Стиль"], ["property", "Имущество"], ["rating", "Рейтинг"]] as const).map(([id, label]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`rounded-xl py-2 text-[11px] font-semibold ${tab === id ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "property" && <LifestyleTab />}
      {tab === "style" && <MyPlayerStyleShop view={view} player={player} onSaved={onSaved} />}
      {tab === "rating" && <MyPlayerLeaderboard />}

      {tab === "progress" && (
        <>
          <section className="rounded-2xl bg-bg-surface p-4">
            <div className="flex items-baseline justify-between">
              <span className="font-display text-base font-bold text-ink-chalk">Уровень {view.level}</span>
              <span className="font-mono text-xs text-ink-mist">{view.xp_into_level} / {view.xp_for_next} опыта</span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-bg-raised">
              <div className="h-full rounded-full bg-floodlight transition-all" style={{ width: `${xpPct}%` }} />
            </div>
            <p className="mt-2 text-xs text-ink-mist">
              Сегодня: <b className="text-ink-chalk">{view.xp_today}</b> / {view.xp_daily_cap} опыта. +{view.xp_per_reward} за каждую
              награду в мини-играх, Тактико и заданиях, +{view.xp_career_match} за матч в «Карьере тренера». Каждый уровень — {view.points_per_level} очка характеристик.
            </p>
            {nextTierIndex >= 0 && (
              <p className="mt-1 text-xs text-ink-mist">
                Следующая рамка — <b className="text-ink-chalk">{TIER_NAMES[nextTierIndex]}</b> на рейтинге {view.next_tier_at}.
              </p>
            )}
          </section>

          <TrainingSection view={view} onSaved={onSaved} onStart={() => setTraining(true)} />

          <section className="rounded-2xl bg-bg-surface p-4">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-base font-bold text-ink-chalk">Характеристики</h2>
              <span className={`rounded-full px-2 py-0.5 font-mono text-xs font-bold ${view.points_available ? "bg-accent-lime text-bg-base" : "bg-bg-raised text-ink-mist"}`}>
                очков: {view.points_available}
              </span>
            </div>
            <p className="mt-2 text-[11px] text-ink-mist">
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
                        <span className="block text-[10px] text-accent-lime">главная для {player.position}</span>
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
                  <span className="block text-[11px] text-ink-mist">Всегда в заявке — поставь его в старт</span>
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
                  <span className="block text-[11px] text-ink-mist">Контракт с клубом, сезоны, голы и трансферы</span>
                </span>
              </span>
              <IconChevronRight size={16} className="text-ink-mist-dim" />
            </button>
            <p className="mt-2 text-[11px] text-ink-mist-dim">Карточку нельзя продать или обменять — она только твоя. Её видят друзья в твоём профиле.</p>
          </section>
        </>
      )}

      {training && (
        <TrainingGame
          maxHits={view.training.max_hits}
          xpBase={view.training.xp_base}
          xpPerHit={view.training.xp_per_hit}
          onDone={onSaved}
          onClose={() => setTraining(false)}
        />
      )}

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
          Собери внешность, выбери позицию — и прокачивай его, играя в любые режимы. Он будет выходить за твою команду в «Карьере тренера».
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
                <p className="text-[11px] text-ink-mist-dim">Линию (вратарь / защита / полузащита / атака) потом сменить нельзя.</p>
              )}
            </div>
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
