import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { claimSeasonReward, createSeasonPassInvoice, fetchSeasonPass } from "@/api/monetization";
import EmptyState from "@/components/common/EmptyState";
import { IconCheck, IconLock, IconTrophy } from "@/components/icons";
import { GrantedRewardModal, RewardBundleChips } from "@/components/rewards/RewardBundleView";
import { formatGameError } from "@/lib/errors";
import { isEmptyBundle } from "@/lib/rewards";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { GrantedRewards, RewardBundle, SeasonLevel } from "@/types";

function daysLeft(iso: string | null): number {
  if (!iso) return 0;
  return Math.max(0, Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000));
}

/** «Сезонный пропуск»: XP from playing unlocks levels; each level has a free
 * reward and a premium one (premium track bought for ⭐). */
export default function SeasonPassPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: season } = useQuery({ queryKey: ["season-pass"], queryFn: fetchSeasonPass });
  const [error, setError] = useState<string | null>(null);
  const [granted, setGranted] = useState<{ level: number; rewards: GrantedRewards } | null>(null);

  const claim = useMutation({
    mutationFn: ({ level, track }: { level: number; track: "free" | "premium" }) => claimSeasonReward(level, track),
    onSuccess: (data, vars) => {
      updateBalance(data.new_balance);
      setGranted({ level: vars.level, rewards: data });
      setError(null);
      for (const key of [["season-pass"], ["collection"], ["cosmetics"], ["profile", "me"]]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
    },
    onError: (err) => setError(formatGameError(err, "Не удалось получить награду")),
  });
  const buy = useMutation({
    mutationFn: () => payShopWithStars(createSeasonPassInvoice),
    onSuccess: (status) => {
      if (status === "paid") hapticNotify("success");
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["season-pass"] });
    },
    onError: (err) => setError(formatGameError(err, "Оплата не прошла")),
  });

  if (!season) return null;
  if (!season.enabled) {
    return (
      <div className="flex flex-col gap-5">
        <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
          <IconTrophy size={20} className="text-purple-300" /> Сезонный пропуск
        </h1>
        <EmptyState icon={IconTrophy} title="Сезон ещё не начался" description="Новый сезон скоро — следи за новостями" />
      </div>
    );
  }

  const prevXp = [...season.levels].reverse().find((l) => l.xp_required <= season.xp)?.xp_required ?? 0;
  const nextXp = season.next_level_xp;
  const progress = nextXp ? Math.min(100, Math.round(((season.xp - prevXp) / Math.max(1, nextXp - prevXp)) * 100)) : 100;

  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-3xl bg-gradient-to-br from-purple-500/30 via-bg-surface to-bg-surface p-5">
        <p className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
          <IconTrophy size={20} className="text-purple-300" /> {season.name}
        </p>
        <p className="mt-0.5 text-xs text-ink-mist">Осталось дней: {daysLeft(season.ends_at)}</p>
        <div className="mt-4 flex items-end justify-between">
          <span className="font-display text-3xl font-bold text-ink-chalk">Ур. {season.level}</span>
          <span className="font-mono text-xs text-ink-mist">
            {season.xp}{nextXp ? ` / ${nextXp}` : ""} XP
          </span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full bg-gradient-to-r from-purple-400 to-fuchsia-400" style={{ width: `${progress}%` }} />
        </div>
        <p className="mt-2 text-caption text-ink-mist-dim">
          +{season.xp_per_game} XP за каждую игру с наградой, +{season.xp_per_daily_claim} XP за награду календаря
        </p>
      </section>

      {!season.is_premium && (
        <section className="rounded-2xl border border-amber-400/40 bg-amber-400/10 p-4">
          <p className="font-display text-sm font-bold text-amber-300">Премиум-дорожка</p>
          <p className="mt-1 text-xs text-ink-mist">
            {season.locked_premium > 0
              ? `Уже заработано премиум-наград: ${season.locked_premium} — открой пропуск и забери их сразу.`
              : "Вторая награда на каждом уровне сезона."}
            {season.premium_status > 0 && ` И +${season.premium_status} статуса «Моему игроку» на весь сезон.`}
          </p>
          <button
            onClick={() => buy.mutate()}
            disabled={buy.isPending}
            className="mt-3 w-full rounded-2xl bg-amber-400 py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            {buy.isPending ? "Оплата..." : `Открыть за ${season.premium_stars} ⭐`}
          </button>
          <p className="mt-2 text-center text-caption text-ink-mist-dim">
            Только этот сезон. Все премиум-награды видны ниже до оплаты.
          </p>
        </section>
      )}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="grid grid-cols-[2.5rem_1fr_1fr] gap-x-2 px-1 text-caption text-ink-mist-dim">
        <span />
        <span>Бесплатно</span>
        <span className="text-amber-300">Премиум</span>
      </div>
      <div className="flex flex-col gap-2">
        {season.levels.map((lv) => (
          <LevelRow
            key={lv.level}
            level={lv}
            isPremium={season.is_premium}
            busy={claim.isPending}
            onClaim={(track) => claim.mutate({ level: lv.level, track })}
          />
        ))}
      </div>

      {granted && (
        <GrantedRewardModal
          title="Награда сезона"
          subtitle={`Уровень ${granted.level}`}
          granted={granted.rewards}
          onClose={() => setGranted(null)}
        />
      )}
    </div>
  );
}

function LevelRow({
  level, isPremium, busy, onClaim,
}: {
  level: SeasonLevel;
  isPremium: boolean;
  busy: boolean;
  onClaim: (track: "free" | "premium") => void;
}) {
  return (
    <div
      className={`grid grid-cols-[2.5rem_1fr_1fr] items-stretch gap-2 rounded-2xl p-2 ${
        level.reached ? "bg-bg-surface" : "bg-bg-surface/50"
      }`}
    >
      <div className="flex flex-col items-center justify-center">
        <span className={`font-display text-base font-bold ${level.reached ? "text-purple-300" : "text-ink-mist-dim"}`}>
          {level.level}
        </span>
        <span className="font-mono text-micro text-ink-mist-dim">{level.xp_required}</span>
      </div>
      <TrackCell
        bundle={level.free}
        claimed={level.free_claimed}
        claimable={level.reached}
        busy={busy}
        onClaim={() => onClaim("free")}
      />
      <TrackCell
        bundle={level.premium}
        claimed={level.premium_claimed}
        claimable={level.reached && isPremium}
        locked={!isPremium}
        premium
        busy={busy}
        onClaim={() => onClaim("premium")}
      />
    </div>
  );
}

function TrackCell({
  bundle, claimed, claimable, locked = false, premium = false, busy, onClaim,
}: {
  bundle: RewardBundle;
  claimed: boolean;
  claimable: boolean;
  locked?: boolean;
  premium?: boolean;
  busy: boolean;
  onClaim: () => void;
}) {
  if (isEmptyBundle(bundle)) return <div className="rounded-xl bg-white/[0.02]" />;
  return (
    <div className={`flex flex-col gap-1.5 rounded-xl p-2 ${premium ? "bg-amber-400/5" : "bg-white/[0.03]"}`}>
      <RewardBundleChips bundle={bundle} />
      {claimed ? (
        <span className="flex items-center gap-1 text-caption text-accent-green"><IconCheck size={12} /> Получено</span>
      ) : locked ? (
        <span className="flex items-center gap-1 text-caption text-ink-mist-dim"><IconLock size={12} /> Пропуск</span>
      ) : claimable ? (
        <button
          onClick={onClaim}
          disabled={busy}
          className="rounded-lg bg-accent-lime py-1 text-caption font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          Забрать
        </button>
      ) : null}
    </div>
  );
}
