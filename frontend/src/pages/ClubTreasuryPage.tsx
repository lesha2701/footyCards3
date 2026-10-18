import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createClubDonationInvoice, fetchClubTreasury } from "@/api/clubFeatures";
import { SponsorBadge } from "@/components/clubs/SponsorBadge";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconCheck, IconChevronLeft, IconCoin, IconStar, IconTrophy } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";

const name = (p: { username: string | null; first_name: string | null; user_id: number }) =>
  p.username ?? p.first_name ?? `#${p.user_id}`;

/** «Казна за Stars»: пополнить бюджет клуба звёздами, «Доска меценатов». */
export default function ClubTreasuryPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: treasury, isLoading } = useQuery({ queryKey: ["clubs", "treasury"], queryFn: fetchClubTreasury });
  const [error, setError] = useState<string | null>(null);
  const [thanks, setThanks] = useState<string | null>(null);
  const [target, setTarget] = useState<"stars" | "coins">("stars");

  const donate = useMutation({
    mutationFn: (stars: number) => payShopWithStars(() => createClubDonationInvoice(stars, target)),
    onSuccess: (status, stars) => {
      if (status !== "paid") return;
      hapticNotify("success");
      setError(null);
      setThanks(
        target === "stars"
          ? `Спасибо! На звёздный баланс клуба +${stars} ⭐`
          : `Спасибо! Казна пополнена на ${stars * (treasury?.coins_per_star ?? 0)} монет`,
      );
      queryClient.invalidateQueries({ queryKey: ["clubs"] });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось пополнить казну")),
  });

  if (isLoading || !treasury) return <ListSkeleton />;
  const next =
    treasury.my_stars < treasury.silver_stars
      ? { label: "серебряного", left: treasury.silver_stars - treasury.my_stars }
      : treasury.my_stars < treasury.gold_stars
        ? { label: "золотого", left: treasury.gold_stars - treasury.my_stars }
        : null;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Казна клуба</h1>
      </div>

      <div className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-amber-400/20 via-accent-lime/10 to-bg-surface p-5">
        <div className="pointer-events-none absolute -right-8 -top-10 h-32 w-32 rounded-full bg-amber-300/20 blur-2xl" />
        <div className="flex items-end gap-6">
          <div>
            <p className="text-xs text-ink-mist">Звёзды клуба</p>
            <p className="flex items-center gap-1.5 font-mono text-3xl font-bold text-amber-300">
              <IconStar size={24} /> {treasury.star_balance}
            </p>
          </div>
          <div>
            <p className="text-xs text-ink-mist">Бюджет</p>
            <p className="flex items-center gap-1 font-mono text-xl font-bold text-accent-lime">
              <IconCoin size={18} /> {treasury.budget}
            </p>
          </div>
        </div>
        <p className="mt-2 text-xs leading-snug text-ink-mist">
          Звёзды клуба тратят капитан, вице-капитан и казначей — на символы, обводки и анимации эмблемы. Или пополни бюджет
          монетами: 1 <IconStar size={11} className="inline align-[-1px] text-amber-300" /> = {treasury.coins_per_star} монет.
          Любое пополнение — место на «Доске меценатов».
        </p>
        <div className="mt-3 flex items-center gap-2 text-xs text-ink-chalk">
          {treasury.my_tier ? (
            <>
              <SponsorBadge tier={treasury.my_tier} /> ты вложил {treasury.my_stars} ⭐
            </>
          ) : (
            <span className="text-ink-mist-dim">Ты ещё не пополнял казну этого клуба</span>
          )}
        </div>
        {next && treasury.my_stars > 0 && (
          <p className="mt-1 text-caption text-ink-mist-dim">До {next.label} мецената: {next.left} ⭐</p>
        )}
      </div>

      {treasury.enabled && (
        <div className="flex gap-1 rounded-xl bg-bg-surface p-1">
          {([["stars", "⭐ Звёзды клуба"], ["coins", "Монеты в казну"]] as ["stars" | "coins", string][]).map(([id, label]) => (
            <button
              key={id}
              onClick={() => setTarget(id)}
              className={`flex-1 rounded-lg py-2 text-xs font-semibold ${target === id ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {treasury.enabled ? (
        <div className="grid grid-cols-3 gap-2">
          {treasury.star_options.map((stars) => (
            <button
              key={stars}
              onClick={() => donate.mutate(stars)}
              disabled={donate.isPending}
              className="flex flex-col items-center gap-0.5 rounded-2xl bg-bg-surface p-3 active:scale-95 disabled:opacity-40"
            >
              <span className="flex items-center gap-1 font-display text-base font-bold text-amber-300">
                <IconStar size={14} /> {stars}
              </span>
              <span className={`flex items-center gap-1 text-caption ${target === "stars" ? "text-amber-200" : "text-accent-lime"}`}>
                {target === "stars" ? <>+{stars} клубу</> : <>+{stars * treasury.coins_per_star} <IconCoin size={11} /></>}
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">Пополнение казны звёздами скоро откроется.</p>
      )}

      {thanks && (
        <p className="flex items-center gap-1.5 rounded-lg bg-accent-green/10 px-3 py-2 text-xs text-accent-green">
          <IconCheck size={13} /> {thanks}
        </p>
      )}
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <section className="flex flex-col gap-2">
        <p className="flex items-center gap-1.5 font-display text-sm font-bold text-ink-chalk">
          <IconTrophy size={15} className="text-amber-300" /> Доска меценатов
        </p>
        {treasury.patrons.length === 0 && (
          <p className="rounded-xl bg-bg-surface p-3 text-xs text-ink-mist-dim">Стань первым меценатом клуба!</p>
        )}
        {treasury.patrons.map((p, index) => (
          <div key={p.user_id} className="flex items-center gap-3 rounded-xl bg-bg-surface p-3">
            <span className={`w-6 text-center font-mono text-sm font-bold ${index < 3 ? "text-amber-300" : "text-ink-mist-dim"}`}>
              {index + 1}
            </span>
            <SponsorBadge tier={p.tier} />
            <span className="min-w-0 flex-1 truncate text-sm text-ink-chalk">
              {name(p)}
              {!p.is_member && <span className="ml-1 text-caption text-ink-mist-dim">(бывший участник)</span>}
            </span>
            <span className="font-mono text-xs font-bold text-amber-300">{p.stars} ⭐</span>
          </div>
        ))}
      </section>

      {treasury.recent.length > 0 && (
        <section className="flex flex-col gap-1.5">
          <p className="font-display text-sm font-bold text-ink-chalk">Последние пополнения</p>
          {treasury.recent.map((d, i) => (
            <div key={i} className="flex items-center justify-between rounded-lg bg-bg-surface px-3 py-2 text-xs">
              <span className="text-ink-mist">{name(d)}</span>
              <span className="text-ink-mist-dim">
                {new Date(d.created_at).toLocaleDateString("ru-RU")} ·{" "}
                {d.coins > 0 ? <span className="text-accent-lime">+{d.coins}</span> : <span className="text-amber-300">+{d.stars} ⭐</span>}
              </span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
