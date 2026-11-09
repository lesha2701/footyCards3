import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { claimAnniversary } from "@/api/anniversary";
import { fetchCardOffers } from "@/api/cardOffers";
import RewardModal, { RewardCard, RewardCoins, RewardPack } from "@/components/common/RewardModal";
import ShareButton from "@/components/common/ShareButton";
import { UserBadge } from "@/components/common/UserBadge";
import { IconChevronLeft, IconClock } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import {
  ANNIVERSARY_QUERY_KEY,
  anniversaryArt,
  bundleEmoji,
  bundleLabel,
  communityPct,
  daysWord,
  useAnniversary,
  useAnniversaryRecap,
} from "@/lib/anniversary";
import { formatGameError } from "@/lib/errors";
import { timeLeft, useMinuteTick } from "@/lib/halloween";
import type { AnniversaryCalendarDay, AnniversaryClaimResult, AnniversaryRecap, AnniversaryState } from "@/types";

const fmt = (n: number) => n.toLocaleString("ru-RU");

interface Reward {
  title: string;
  subtitle?: string;
  items: ReactNode[];
}

function rewardOf(result: AnniversaryClaimResult, subtitle?: string): Reward {
  const r = result.rewards;
  const items: ReactNode[] = [];
  if (r.coins) items.push(<RewardCoins key="c" amount={r.coins} />);
  if (r.pack_name) items.push(<RewardPack key="p" name={r.pack_name} />);
  r.cards.forEach((card) => items.push(<RewardCard key={`card-${card.id}`} card={card} />));
  if (r.badge) items.push(<UserBadge key="b" badge={r.badge} />);
  return { title: result.title, subtitle, items };
}

/** «💯 Нам 100 дней!»: the recap «Мои 100 дней», the gift calendar, the
 *  community goal «Сотня» and the collection «Первые 100». */
export default function AnniversaryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const now = useMinuteTick();
  const bannerArt = anniversaryArt("banner");
  const { data, isLoading } = useAnniversary({ poll: true });
  const { data: recap } = useAnniversaryRecap(!!data?.enabled);
  const [error, setError] = useState<string | null>(null);
  const [reward, setReward] = useState<Reward | null>(null);
  const [story, setStory] = useState(false);
  const collectionId = data?.collection?.id;
  const { data: offers } = useQuery({ queryKey: ["card-offers"], queryFn: fetchCardOffers, enabled: collectionId != null });
  const edition = offers?.find((o) => o.player?.collection_id === collectionId && o.player?.edition_size != null);

  const claim = useMutation({
    mutationFn: (what: "calendar" | "community" | "recap") => claimAnniversary(what),
    onMutate: () => setError(null),
    onSuccess: (result, what) => {
      setReward(rewardOf(result, what === "calendar" ? "Следующий подарок — завтра" : undefined));
      queryClient.invalidateQueries({ queryKey: ANNIVERSARY_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: ["profile", "me"] });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось забрать подарок")),
  });

  if (isLoading) return null;
  if (!data?.enabled) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <span className="text-5xl">💯</span>
        <p className="font-display text-base font-bold text-ink-chalk">Праздник ещё не начался</p>
        <button onClick={() => navigate("/")} className="text-sm text-accent-lime">На главную</button>
      </div>
    );
  }
  const before = !data.active && !data.finished;

  return (
    <div className="flex flex-col gap-4 pb-24">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 self-start text-xs text-ink-mist">
        <IconChevronLeft size={16} /> Назад
      </button>

      {bannerArt ? (
        // The art carries its own golden «100»: only the caption goes on top.
        <section className="relative aspect-[15/7] overflow-hidden rounded-3xl ring-1 ring-amber-300/30">
          <img src={bannerArt} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover" />
          <div className="absolute inset-x-0 bottom-0 flex items-end justify-between gap-2 bg-gradient-to-t from-black/85 via-black/45 to-transparent px-4 pb-3 pt-8">
            <h1 className="font-display text-lg font-black uppercase leading-tight tracking-wide text-white drop-shadow">
              Нам 100 дней!
            </h1>
            <p className="flex shrink-0 items-center gap-1 font-mono text-caption text-white/80">
              <IconClock size={12} />
              {before ? `старт через ${timeLeft(data.starts_at, now)}` : data.active ? `праздник ещё ${timeLeft(data.ends_at, now)}` : "праздник окончен"}
            </p>
          </div>
        </section>
      ) : (
        <section className="anni-sky relative overflow-hidden rounded-3xl p-5 text-center ring-1 ring-amber-300/30">
          <div className="relative flex flex-col items-center gap-1">
            <span className="anni-glow font-display text-6xl font-black leading-none text-amber-200">100</span>
            <h1 className="font-display text-xl font-black uppercase tracking-wide text-white drop-shadow">дней Victor FC</h1>
            <p className="flex items-center gap-1 font-mono text-caption text-white/75">
              <IconClock size={12} />
              {before ? `старт через ${timeLeft(data.starts_at, now)}` : data.active ? `праздник ещё ${timeLeft(data.ends_at, now)}` : "праздник окончен"}
            </p>
          </div>
        </section>
      )}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>}

      {recap && <RecapCard recap={recap} data={data} onOpen={() => setStory(true)} onClaim={() => claim.mutate("recap")} busy={claim.isPending} />}

      <CalendarBlock data={data} busy={claim.isPending} onClaim={() => claim.mutate("calendar")} />

      <CommunityBlock data={data} busy={claim.isPending} onClaim={() => claim.mutate("community")} />

      {data.collection && data.collection.total > 0 && (
        <section className="flex items-center gap-3 rounded-3xl bg-bg-surface p-4 ring-1 ring-white/10">
          <span className="gold100-frame flex h-16 w-12 shrink-0 items-center justify-center rounded-xl text-2xl">⭐</span>
          <div className="min-w-0 flex-1">
            <p className="font-display text-sm font-bold text-ink-chalk">«{data.collection.name}»</p>
            <p className="text-xs text-ink-mist">
              {data.collection.completed
                ? "Коллекция собрана — награда твоя!"
                : `Собрано ${data.collection.owned} из ${data.collection.total} · золотая юбилейная рамка`}
            </p>
          </div>
          <button onClick={() => navigate("/collection")} className="rounded-xl bg-white/10 px-3 py-2 text-xs font-semibold text-ink-chalk">
            Альбом
          </button>
        </section>
      )}

      {edition?.player && (
        <button
          onClick={() => navigate("/packs?tab=cards")}
          className="anni-sky flex items-center gap-3 rounded-3xl p-4 text-left ring-1 ring-amber-300/40 active:scale-[0.98]"
        >
          <span className="gold100-frame flex h-16 w-12 shrink-0 items-center justify-center rounded-xl font-display text-sm font-black text-black">
            {edition.player.rating}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-display text-sm font-bold text-amber-100">Золотая карта: {edition.player.display_name}</span>
            <span className="block text-xs text-white/75">
              Всего {edition.player.edition_size} номерных копий · {edition.left ? `осталось ${edition.left}` : "раскупили"}
            </span>
          </span>
          <span className="whitespace-nowrap rounded-xl bg-amber-300 px-3 py-2 text-xs font-bold text-black">{edition.stars_price} ⭐</span>
        </button>
      )}

      <AnimatePresence>{story && recap && <RecapStory recap={recap} onClose={() => setStory(false)} />}</AnimatePresence>

      {reward && (
        <RewardModal title={reward.title} subtitle={reward.subtitle} items={reward.items} buttonLabel="Ура!" onClose={() => setReward(null)} />
      )}
    </div>
  );
}

function RecapCard({
  recap,
  data,
  onOpen,
  onClaim,
  busy,
}: {
  recap: AnniversaryRecap;
  data: AnniversaryState;
  onOpen: () => void;
  onClaim: () => void;
  busy: boolean;
}) {
  const canClaim = data.active && !data.recap_claimed && data.recap_coins > 0;
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-gradient-to-br from-purple-500/25 via-bg-surface to-bg-surface p-4 ring-1 ring-purple-400/30">
      <div>
        <h2 className="font-display text-base font-bold text-ink-chalk">🎬 Мои 100 дней</h2>
        <p className="text-xs text-ink-mist">
          Ты с нами {fmt(recap.days_with_us)} {daysWord(recap.days_with_us)} · игрок №{fmt(recap.player_number)}
        </p>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <Mini value={fmt(recap.games)} label="игр" />
        <Mini value={fmt(recap.cards)} label="карт" />
        <Mini value={fmt(recap.packs_opened)} label="паков" />
      </div>
      <button onClick={onOpen} className="rounded-2xl bg-purple-400 py-3 font-display text-sm font-black uppercase text-black">
        ▶ Смотреть историю
      </button>
      <div className="flex items-center justify-between gap-2">
        <ShareButton kind="anniversary_recap" id={0} label="Поделиться в Telegram" compact />
        {canClaim && (
          <button onClick={onClaim} disabled={busy} className="fans-pulse rounded-xl bg-amber-300 px-3 py-2 text-xs font-bold text-black disabled:opacity-60">
            🎁 +{fmt(data.recap_coins)} за просмотр
          </button>
        )}
      </div>
    </section>
  );
}

function Mini({ value, label }: { value: string; label: string }) {
  return (
    <div className="rounded-2xl bg-white/5 py-2">
      <p className="font-mono text-lg font-bold text-ink-chalk">{value}</p>
      <p className="text-micro text-ink-mist">{label}</p>
    </div>
  );
}

/** Full-screen slides, Wrapped-style: tap right to go on, left to go back. */
function RecapStory({ recap, onClose }: { recap: AnniversaryRecap; onClose: () => void }) {
  const [i, setI] = useState(0);
  const slides = recapSlides(recap);
  const slide = slides[i];
  const bg = anniversaryArt("recap-bg");
  const go = (d: number) => {
    if (i + d >= slides.length) onClose();
    else setI((prev) => Math.min(slides.length - 1, Math.max(0, prev + d)));
  };
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="anni-sky fixed inset-0 z-50 flex flex-col px-5 pb-10 pt-6"
      role="dialog"
      aria-label="Мои 100 дней"
    >
      {bg && <img src={bg} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover opacity-40" />}
      <div className="relative flex gap-1">
        {slides.map((_, n) => (
          <span key={n} className={`h-1 flex-1 rounded-full ${n <= i ? "bg-amber-200" : "bg-white/20"}`} />
        ))}
      </div>
      <button onClick={onClose} className="relative mt-3 self-end text-sm text-white/70" aria-label="Закрыть">
        ✕
      </button>
      <div className="relative flex flex-1">
        <button className="absolute inset-y-0 left-0 z-10 w-1/3" onClick={() => go(-1)} aria-label="Назад" />
        <button className="absolute inset-y-0 right-0 z-10 w-2/3" onClick={() => go(1)} aria-label="Дальше" />
        <AnimatePresence mode="wait">
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -24 }}
            transition={{ duration: 0.35 }}
            className="flex flex-1 flex-col items-center justify-center gap-3 text-center"
          >
            {slide.visual}
            <p className="text-sm uppercase tracking-widest text-amber-200/90">{slide.kicker}</p>
            <p className="anni-glow font-display text-6xl font-black leading-none text-white">{slide.big}</p>
            <p className="max-w-xs text-base text-white/85">{slide.text}</p>
          </motion.div>
        </AnimatePresence>
      </div>
      {i === slides.length - 1 && (
        <div className="relative z-20 flex justify-center">
          <ShareButton kind="anniversary_recap" id={0} label="Поделиться в Telegram" />
        </div>
      )}
    </motion.div>
  );
}

interface Slide {
  kicker: string;
  big: string;
  text: string;
  visual?: ReactNode;
}

function recapSlides(r: AnniversaryRecap): Slide[] {
  const slides: Slide[] = [
    { kicker: "Victor FC исполнилось 100 дней", big: fmt(r.days_with_us), text: `${daysWord(r.days_with_us)} ты с нами — и ты игрок №${fmt(r.player_number)}`, visual: <span className="text-6xl">💯</span> },
    { kicker: "Ты заходил", big: fmt(r.active_days), text: `${daysWord(r.active_days)} в игре`, visual: <span className="text-6xl">📅</span> },
  ];
  if (r.games > 0)
    slides.push({
      kicker: "Сыграно",
      big: fmt(r.games),
      text: r.favourite_mode ? `игр, а любимый режим — «${r.favourite_mode}» (${fmt(r.favourite_mode_games)})` : "игр",
      visual: <span className="text-6xl">🎮</span>,
    });
  slides.push({
    kicker: "Твой клуб",
    big: fmt(r.cards),
    text: `карт, ${fmt(r.unique_players)} разных футболистов, ${fmt(r.packs_opened)} открытых паков${r.cards_better_than_pct > 0 ? ` — больше, чем у ${r.cards_better_than_pct}% игроков` : ""}`,
    visual: <span className="text-6xl">🃏</span>,
  });
  if (r.best_card_name)
    slides.push({
      kicker: "Звезда твоей коллекции",
      big: String(r.best_card_rating ?? ""),
      text: `${r.best_card_name}${r.best_card_position ? ` · ${r.best_card_position}` : ""}`,
      visual: r.best_card_image ? (
        <img src={staticUrl(r.best_card_image)} alt="" className="gold100-frame h-40 w-32 rounded-2xl object-cover p-[3px]" />
      ) : (
        <span className="text-6xl">⭐</span>
      ),
    });
  slides.push({
    kicker: "Заработано",
    big: fmt(r.coins_earned),
    text: `монет${r.trades > 0 ? `, ${fmt(r.trades)} обменов` : ""}${r.badges > 0 ? `, ${fmt(r.badges)} значков` : ""}`,
    visual: <span className="text-6xl">💰</span>,
  });
  slides.push({ kicker: "Спасибо, что ты с нами!", big: "100", text: "А впереди — следующие сто. Поделись своими цифрами с друзьями 👇", visual: <span className="text-6xl">🎉</span> });
  return slides;
}

function CalendarBlock({ data, busy, onClaim }: { data: AnniversaryState; busy: boolean; onClaim: () => void }) {
  if (data.calendar.length === 0) return null;
  const now = Date.now();
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4 ring-1 ring-white/10">
      <div>
        <h2 className="font-display text-base font-bold text-ink-chalk">🎁 Юбилейный календарь</h2>
        <p className="text-xs text-ink-mist">
          Один подарок в день, по порядку. Последний — значок «100 дней» и юбилейный пак. Забрано {data.calendar_claimed} из {data.calendar.length}.
        </p>
      </div>
      <div className="grid grid-cols-4 gap-2">
        {data.calendar.map((d) => (
          <GiftTile key={d.n} d={d} last={d.n === data.calendar.length} />
        ))}
      </div>
      {data.active && (
        <button
          onClick={onClaim}
          disabled={!data.calendar_ready || busy}
          className={`rounded-2xl py-3 font-display text-sm font-black uppercase disabled:bg-white/10 disabled:text-ink-mist ${data.calendar_ready ? "fans-pulse bg-amber-300 text-black" : ""}`}
        >
          {busy
            ? "…"
            : data.calendar_ready
              ? "🎁 Открыть подарок дня"
              : data.calendar_claimed >= data.calendar.length
                ? "Все подарки твои ✓"
                : `Следующий через ${timeLeft(data.day_resets_at, now)}`}
        </button>
      )}
    </section>
  );
}

function GiftTile({ d, last }: { d: AnniversaryCalendarDay; last: boolean }) {
  const art = anniversaryArt(last ? "gift-final" : "gift");
  const ring = d.status === "today" ? "ring-2 ring-amber-300" : d.status === "claimed" ? "ring-1 ring-white/10" : "ring-1 ring-white/5";
  return (
    <div
      className={`relative flex aspect-square flex-col items-center justify-center gap-0.5 rounded-2xl text-center ${ring} ${
        last ? "col-span-2 aspect-auto bg-gradient-to-br from-amber-400/30 to-purple-500/20" : d.status === "claimed" ? "bg-white/5" : "bg-white/[0.08]"
      } ${d.status === "locked" ? "opacity-70" : ""}`}
      title={bundleLabel(d.reward)}
    >
      <span className="absolute left-1.5 top-1 font-mono text-[10px] text-ink-mist">{d.n}</span>
      {art && d.status !== "claimed" ? (
        <img src={art} alt="" className="h-9 w-9 object-contain" />
      ) : (
        <span className={last ? "text-3xl" : "text-xl"}>{d.status === "claimed" ? "✓" : last ? "💯" : bundleEmoji(d.reward)}</span>
      )}
      <span className="line-clamp-2 px-1 text-[10px] leading-tight text-ink-chalk">{bundleLabel(d.reward)}</span>
    </div>
  );
}

function CommunityBlock({ data, busy, onClaim }: { data: AnniversaryState; busy: boolean; onClaim: () => void }) {
  const c = data.community;
  if (!c) return null;
  const pct = communityPct(c);
  const ready = c.my_games >= c.min_games;
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-gradient-to-br from-amber-500/15 via-bg-surface to-bg-surface p-4 ring-1 ring-amber-400/30">
      <div>
        <h2 className="font-display text-base font-bold text-amber-100">🏟 Общая цель «Сотня»</h2>
        <p className="text-xs text-ink-mist">
          Все вместе играем {fmt(c.goal)} наградных игр. Каждая ступень — подарок всем, кто сыграл хотя бы {c.min_games}.
        </p>
      </div>
      <div>
        <div className="flex justify-between font-mono text-micro text-ink-mist">
          <span>{fmt(c.total)} / {fmt(c.goal)}</span>
          <span className="font-bold text-amber-200">{pct}%</span>
        </div>
        <div className="relative mt-1 h-3 overflow-hidden rounded-full bg-white/10">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${pct}%` }}
            transition={{ duration: 0.9 }}
            className="h-full rounded-full bg-gradient-to-r from-amber-200 via-amber-400 to-orange-500"
          />
          {c.tiers.map((t) => (
            <span key={t.pct} className="absolute inset-y-0 w-px bg-black/50" style={{ left: `${t.pct}%` }} />
          ))}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2">
        {c.tiers.map((t) => (
          <div
            key={t.pct}
            className={`flex items-center gap-2 rounded-2xl px-3 py-2 ${t.reached ? "bg-amber-400/15 ring-1 ring-amber-300/40" : "bg-white/5"}`}
          >
            <span className="font-display text-sm font-black text-amber-200">{t.pct}%</span>
            <span className="min-w-0 flex-1 truncate text-[11px] text-ink-chalk">{bundleLabel(t.reward)}</span>
            <span className="text-xs">{t.claimed ? "✓" : t.reached ? "🎁" : "🔒"}</span>
          </div>
        ))}
      </div>
      <p className="text-xs text-ink-mist">
        Твой вклад: <b className="text-ink-chalk">{fmt(c.my_games)}</b> {c.my_games === 1 ? "игра" : "игр"}
        {!ready && ` · ещё ${c.min_games - c.my_games}, чтобы получать подарки`}
      </p>
      {c.claimable && (
        <button onClick={onClaim} disabled={busy} className="fans-pulse rounded-2xl bg-amber-300 py-3 font-display text-sm font-black uppercase text-black disabled:opacity-60">
          {busy ? "…" : "🎁 Забрать подарки ступеней"}
        </button>
      )}
    </section>
  );
}
