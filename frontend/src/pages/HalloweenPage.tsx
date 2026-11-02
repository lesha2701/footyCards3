import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { buyHalloweenItem, openHalloweenDoor } from "@/api/halloween";
import RewardModal, { RewardCard, RewardCoins, RewardPack } from "@/components/common/RewardModal";
import { UserBadge } from "@/components/common/UserBadge";
import { HalloweenDecor } from "@/components/halloween/HalloweenBanner";
import { IconChevronLeft, IconClock } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { HALLOWEEN_QUERY_KEY, halloweenArt, pumpkinsWord, timeLeft, useHalloween, useMinuteTick } from "@/lib/halloween";
import { skillByCode, useSkillCatalog } from "@/lib/cardSkills";
import type { HalloweenDoorResult, HalloweenShopItem } from "@/types";

const fmt = (n: number) => n.toLocaleString("ru-RU");

function newKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID().replace(/-/g, "");
  return `${Date.now()}${Math.random().toString(36).slice(2)}`;
}

const SHOP_EMOJI: Record<HalloweenShopItem["kind"], string> = { pack: "🧟", coins: "💰", skill_tokens: "🔮", badge: "🎃" };
const DOOR_LOOK = [
  { emoji: "💀", tint: "from-violet-700 to-violet-950", knob: "bg-orange-400" },
  { emoji: "🕯️", tint: "from-orange-700 to-amber-950", knob: "bg-violet-300" },
  { emoji: "🕸️", tint: "from-emerald-800 to-slate-950", knob: "bg-lime-300" },
];

interface Reward {
  title: string;
  subtitle?: string;
  hero?: ReactNode;
  items: ReactNode[];
}

/** «🎃 Ночь тыкв»: pumpkins, the daily doors and the pumpkin shop. */
export default function HalloweenPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const now = useMinuteTick();
  const { data, isLoading } = useHalloween();
  const [error, setError] = useState<string | null>(null);
  const [reward, setReward] = useState<Reward | null>(null);
  const [picked, setPicked] = useState<number | null>(null);
  const { data: skills } = useSkillCatalog();

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: HALLOWEEN_QUERY_KEY });
    queryClient.invalidateQueries({ queryKey: ["profile", "me"] });
  };

  const door = useMutation({
    mutationFn: (index: number) => openHalloweenDoor(index),
    onMutate: (index) => {
      setError(null);
      setPicked(index);
    },
    onSuccess: (result) => {
      // Let the door swing open first.
      window.setTimeout(() => {
        setReward(doorReward(result));
        refresh();
      }, 650);
    },
    onError: (err) => {
      setPicked(null);
      setError(formatGameError(err, "Дверь не открылась"));
    },
  });

  const buy = useMutation({
    mutationFn: (item: HalloweenShopItem) => buyHalloweenItem(item.code, newKey()),
    onMutate: () => setError(null),
    onSuccess: (result, item) => {
      const items: ReactNode[] = [];
      if (result.coins) items.push(<RewardCoins key="c" amount={result.coins} />);
      if (result.pack_name) items.push(<RewardPack key="p" name={result.pack_name} />);
      result.cards.forEach((c) => items.push(<RewardCard key={`card-${c.id}`} card={c} />));
      if (result.skill_code)
        items.push(
          <p key="t" className="text-sm font-semibold text-violet-200">
            🔮 Жетоны «{skillByCode(skills?.skills, result.skill_code)?.name ?? result.skill_code}» × {result.skill_tokens}
          </p>,
        );
      if (result.badge)
        items.push(
          <p key="b" className="flex items-center gap-1.5 text-sm font-semibold text-orange-200">
            <UserBadge badge={result.badge} /> Значок «{result.badge.name}» — теперь он у твоего имени
          </p>,
        );
      setReward({ title: "Обмен в лавке!", subtitle: `${item.title} — твоё. Осталось ${fmt(result.pumpkins)} 🎃`, items });
      refresh();
    },
    onError: (err) => setError(formatGameError(err, "Не удалось обменять тыквы")),
  });

  if (isLoading) return null;
  if (!data?.enabled) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <span className="text-5xl">🎃</span>
        <p className="font-display text-base font-bold text-ink-chalk">Ночь тыкв ещё не наступила</p>
        <button onClick={() => navigate("/")} className="text-sm text-accent-lime">На главную</button>
      </div>
    );
  }
  const live = data.active;
  const today = data.door_today;
  const pack = data.shop.find((s) => s.kind === "pack" && s.available);

  return (
    <div className="flex flex-col gap-4 pb-6">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 self-start text-xs text-ink-mist">
        <IconChevronLeft size={16} /> Назад
      </button>

      {/* Header */}
      <section className="hw-sky hw-glow relative overflow-hidden rounded-3xl p-4">
        {halloweenArt("banner") && (
          <img src={halloweenArt("banner")} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover opacity-60" />
        )}
        <HalloweenDecor dense />
        <div className="relative">
          <h1 className="font-display text-2xl font-black uppercase leading-none tracking-wide text-orange-300 drop-shadow">
            🎃 Ночь тыкв
          </h1>
          <p className="mt-1 flex items-center gap-1 font-mono text-caption text-violet-200">
            <IconClock size={12} /> {live ? `до конца ${timeLeft(data.ends_at, now)}` : "ивент закончился"}
          </p>
          <div className="mt-4 flex items-end gap-2">
            <span className="hw-float text-5xl leading-none">🎃</span>
            <span>
              <span className="block font-display text-4xl font-black leading-none text-white">{fmt(data.pumpkins)}</span>
              <span className="text-xs text-orange-200">{pumpkinsWord(data.pumpkins)} в мешке · всего собрано {fmt(data.earned_total)}</span>
            </span>
          </div>
        </div>
      </section>

      {/* How to earn */}
      <section className="grid grid-cols-2 gap-2">
        <EarnChip
          emoji="🎮"
          title={`+${data.pumpkins_per_game} за игру`}
          text={data.games_daily_cap > 0 ? `сегодня ${data.games_pumpkins_today}/${data.games_daily_cap}` : "в любом режиме"}
          onClick={() => navigate("/play")}
        />
        <EarnChip emoji="📜" title={`+${data.pumpkins_per_task} за задание`} text="и ещё за сундуки" onClick={() => navigate("/tasks")} />
        {data.boss_name && (
          <EarnChip
            emoji="👻"
            wide
            title={`${data.boss_name}: тыквы ×${data.boss_multiplier}`}
            text="Выстой до свистка в «Контратаке» — получишь двойные тыквы"
            onClick={() => navigate("/play/kontra/boss")}
          />
        )}
      </section>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>}

      {/* Trick or treat */}
      <section className="rounded-3xl bg-violet-950/60 p-4 ring-1 ring-violet-500/30">
        <div className="flex items-baseline justify-between gap-2">
          <h2 className="font-display text-base font-bold text-orange-200">Кошелёк или жизнь?</h2>
          {today && <span className="font-mono text-micro text-violet-300">новые через {timeLeft(data.door_resets_at, now)}</span>}
        </div>
        <p className="mt-0.5 text-xs text-violet-200/80">
          {today ? "Сегодня ты уже стучался. Вот что было за дверью:" : "Раз в день постучи в одну из трёх дверей: сладость или гадость?"}
        </p>
        <div className="mt-3 grid grid-cols-3 gap-2">
          {DOOR_LOOK.map((look, i) => {
            const opened = today ? today.door === i : picked === i && door.isSuccess;
            const disabled = !live || !!today || door.isPending;
            return (
              <Door
                key={i}
                index={i}
                look={look}
                opened={opened}
                dimmed={!!today && today.door !== i}
                shaking={door.isPending && picked === i}
                result={today?.door === i ? today : null}
                disabled={disabled}
                onClick={() => door.mutate(i)}
              />
            );
          })}
        </div>
      </section>

      {/* Pumpkin shop */}
      <section className="flex flex-col gap-2">
        <h2 className="px-1 font-display text-base font-bold text-ink-chalk">Лавка тыкв</h2>
        <div className="grid grid-cols-2 gap-2">
          {data.shop.map((item) => (
            <ShopTile
              key={item.code}
              item={item}
              canAfford={data.pumpkins >= item.price}
              busy={buy.isPending && buy.variables?.code === item.code}
              onBuy={() => buy.mutate(item)}
            />
          ))}
        </div>
      </section>

      {/* Collection + pack */}
      {data.collection && (
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-lime-900/50 via-violet-950/70 to-black p-4 ring-1 ring-lime-500/30">
          <div className="flex items-center gap-3">
            {halloweenArt("pack") ? (
              <img src={halloweenArt("pack")} alt="" className="h-20 w-16 rounded-xl object-cover" />
            ) : (
              <span className="flex h-20 w-16 items-center justify-center rounded-xl bg-gradient-to-b from-lime-500 to-violet-800 text-3xl shadow-[0_0_18px_rgba(132,204,22,0.45)]">
                🧟
              </span>
            )}
            <div className="min-w-0 flex-1">
              <p className="font-display text-sm font-bold text-lime-200">«{data.collection.name}»</p>
              <p className="text-xs text-ink-mist">
                {data.collection.completed
                  ? "Коллекция собрана — награда твоя!"
                  : `Собрано ${data.collection.owned} из ${data.collection.total}${
                      data.collection.reward_coins ? ` · награда ${fmt(data.collection.reward_coins)} монет` : ""
                    }`}
              </p>
              {data.collection.total > 0 && (
                <span className="mt-2 block h-1.5 overflow-hidden rounded-full bg-white/10">
                  <span
                    className="block h-full rounded-full bg-gradient-to-r from-lime-400 to-violet-400"
                    style={{ width: `${Math.min(100, (data.collection.owned * 100) / data.collection.total)}%` }}
                  />
                </span>
              )}
            </div>
          </div>
          <div className="mt-3 flex gap-2">
            <button onClick={() => navigate("/collection")} className="flex-1 rounded-xl bg-white/10 py-2 text-xs font-semibold text-ink-chalk">
              Альбом
            </button>
            {pack && (
              <button onClick={() => navigate("/packs")} className="flex-1 rounded-xl bg-lime-500 py-2 text-xs font-bold text-black">
                Пак в магазине
              </button>
            )}
          </div>
        </section>
      )}

      {reward && (
        <RewardModal
          title={reward.title}
          subtitle={reward.subtitle}
          hero={reward.hero}
          items={reward.items}
          buttonLabel="Жуть!"
          onClose={() => {
            setReward(null);
            setPicked(null);
          }}
        />
      )}
    </div>
  );
}

function doorReward(result: HalloweenDoorResult): Reward {
  const items: ReactNode[] = [<p key="t" className="text-sm text-ink-chalk">{result.text}</p>];
  if (result.kind === "coins") items.push(<RewardCoins key="c" amount={result.amount} />);
  if (result.kind === "pumpkins")
    items.push(
      <p key="p" className="font-display text-lg font-bold text-orange-300">
        +{result.amount} 🎃
      </p>,
    );
  if (result.pack_name) items.push(<RewardPack key="pk" name={result.pack_name} />);
  result.cards.forEach((c) => items.push(<RewardCard key={`card-${c.id}`} card={c} />));
  return {
    title: result.title,
    subtitle: result.outcome === "trick" ? "Это шутка — ничего не пропало 😈" : undefined,
    hero: <span className="text-6xl">{result.outcome === "trick" ? (result.kind === "zombie_frame" ? "🧟" : "👻") : "🍬"}</span>,
    items,
  };
}

function EarnChip({ emoji, title, text, onClick, wide }: { emoji: string; title: string; text: string; onClick: () => void; wide?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 rounded-2xl bg-bg-surface px-3 py-2.5 text-left ring-1 ring-orange-500/20 active:scale-[0.98] ${wide ? "col-span-2" : ""}`}
    >
      <span className="text-xl">{emoji}</span>
      <span className="min-w-0">
        <span className="block font-display text-xs font-bold leading-tight text-orange-200">{title}</span>
        <span className="block text-micro text-ink-mist">{text}</span>
      </span>
    </button>
  );
}

function Door({
  index, look, opened, dimmed, shaking, result, disabled, onClick,
}: {
  index: number;
  look: (typeof DOOR_LOOK)[number];
  opened: boolean;
  dimmed: boolean;
  shaking: boolean;
  result: HalloweenDoorResult | null;
  disabled: boolean;
  onClick: () => void;
}) {
  const art = halloweenArt(`door-${index + 1}`);
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={`Дверь ${index + 1}`}
      className={`relative aspect-[3/5] overflow-hidden rounded-t-[999px] rounded-b-xl bg-black ring-2 ${
        opened ? "ring-orange-400" : "ring-violet-500/40"
      } ${dimmed ? "opacity-40" : ""} transition-opacity`}
    >
      {/* What's behind */}
      <span className="absolute inset-0 flex flex-col items-center justify-center gap-1 bg-gradient-to-b from-orange-500/40 to-black px-1 text-center">
        <span className="text-3xl">{result ? (result.outcome === "trick" ? (result.kind === "zombie_frame" ? "🧟" : "👻") : "🍬") : "✨"}</span>
        {result && <span className="text-micro font-bold leading-tight text-orange-100">{result.title}</span>}
      </span>
      {/* The door leaf swings open around its left hinge */}
      <motion.span
        className="absolute inset-0 origin-left"
        style={{ transformPerspective: 600 }}
        animate={opened ? { rotateY: -105 } : shaking ? { rotate: [0, -2, 2, -2, 0] } : { rotateY: 0 }}
        transition={opened ? { duration: 0.6, ease: "easeIn" } : { duration: 0.4, repeat: shaking ? Infinity : 0 }}
      >
        {art ? (
          <img src={art} alt="" className="h-full w-full object-cover" />
        ) : (
          <span className={`flex h-full w-full flex-col items-center justify-center gap-2 bg-gradient-to-b ${look.tint}`}>
            <span className="text-3xl drop-shadow">{look.emoji}</span>
            <span className="font-display text-lg font-black text-white/80">{index + 1}</span>
            <span className={`absolute right-2 top-1/2 h-2.5 w-2.5 rounded-full ${look.knob}`} />
          </span>
        )}
      </motion.span>
    </button>
  );
}

function ShopTile({ item, canAfford, busy, onBuy }: { item: HalloweenShopItem; canAfford: boolean; busy: boolean; onBuy: () => void }) {
  const soldOut = item.limit > 0 && item.bought >= item.limit;
  const label = item.kind === "badge" && !item.available && item.badge ? "Уже твой" : soldOut ? "Разобрали" : !item.available ? "Скоро" : null;
  const sub =
    item.kind === "coins"
      ? `${fmt(item.amount)} монет`
      : item.kind === "skill_tokens"
        ? `${item.amount} жет. случайного навыка`
        : item.kind === "pack"
          ? "3 карточки в зомби-рамке"
          : "Лимитированный, только на Хеллоуин";
  const art = item.kind === "pack" ? halloweenArt("pack") : item.kind === "badge" ? halloweenArt("badge") : undefined;
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3 ring-1 ring-orange-500/15">
      <div className="flex items-center gap-2">
        {art ? (
          <img src={art} alt="" className="h-11 w-11 rounded-xl object-cover" />
        ) : (
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-orange-500/30 to-violet-700/40 text-2xl">
            {item.kind === "badge" && item.badge ? item.badge.icon : SHOP_EMOJI[item.kind]}
          </span>
        )}
        <span className="min-w-0">
          <span className="block font-display text-xs font-bold leading-tight text-ink-chalk">{item.title}</span>
          <span className="block text-micro text-ink-mist">{sub}</span>
        </span>
      </div>
      {item.limit > 0 && <span className="text-micro text-ink-mist-dim">куплено {item.bought}/{item.limit}</span>}
      <button
        onClick={onBuy}
        disabled={!!label || !canAfford || busy}
        className="mt-auto rounded-xl bg-gradient-to-r from-orange-500 to-amber-400 py-2 font-display text-xs font-bold text-black disabled:from-white/10 disabled:to-white/10 disabled:text-ink-mist"
      >
        {busy ? "…" : label ?? `${fmt(item.price)} 🎃`}
      </button>
    </div>
  );
}
