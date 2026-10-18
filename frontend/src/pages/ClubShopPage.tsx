import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { buyClubShopItem, claimClubReward, fetchClubShop } from "@/api/clubFeatures";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconCoin, IconGift, IconShop } from "@/components/icons";
import { GrantedRewardModal, RewardBundleChips } from "@/components/rewards/RewardBundleView";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { ClubShop, GrantedRewards } from "@/types";

const SOURCE_LABELS: Record<string, string> = { shop: "Магазин", quest: "Задание недели", war: "Клубная война" };

/** «Клубный магазин»: клуб тратит бюджет — каждый участник забирает награду себе.
 * Здесь же — все невостребованные награды клуба (магазин, задания, войны). */
export default function ClubShopPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: shop, isLoading } = useQuery({ queryKey: ["clubs", "shop"], queryFn: fetchClubShop });
  const [error, setError] = useState<string | null>(null);
  const [confirmItem, setConfirmItem] = useState<ClubShop["items"][number] | null>(null);
  const [granted, setGranted] = useState<{ title: string; data: GrantedRewards } | null>(null);

  const onError = (err: unknown) => setError(formatGameError(err, "Не удалось выполнить действие"));
  const buy = useMutation({
    mutationFn: (id: number) => buyClubShopItem(id),
    onSuccess: (data) => {
      queryClient.setQueryData(["clubs", "shop"], data);
      queryClient.invalidateQueries({ queryKey: ["clubs", "me"] });
      hapticNotify("success");
      setError(null);
    },
    onError,
  });
  const claim = useMutation({
    mutationFn: ({ id }: { id: number; title: string }) => claimClubReward(id),
    onSuccess: (data, vars) => {
      updateBalance(data.new_balance);
      setGranted({ title: vars.title, data });
      setError(null);
      for (const key of [["clubs"], ["profile", "me"], ["collection"]]) queryClient.invalidateQueries({ queryKey: key });
    },
    onError,
  });

  if (isLoading || !shop) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Клубный магазин</h1>
        <span className="ml-auto flex items-center gap-1 font-mono text-sm font-bold text-accent-lime">
          <IconCoin size={14} /> {shop.budget}
        </span>
      </div>

      {shop.rewards.length > 0 && (
        <section className="flex flex-col gap-2">
          <p className="flex items-center gap-1.5 font-display text-sm font-bold text-ink-chalk">
            <IconGift size={15} className="text-accent-lime" /> Твои награды от клуба
          </p>
          {shop.rewards.map((r) => (
            <div key={r.id} className="flex items-center gap-3 rounded-2xl bg-gradient-to-r from-accent-lime/15 to-bg-surface p-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-semibold text-ink-chalk">{r.title}</p>
                <p className="text-micro text-ink-mist-dim">
                  {SOURCE_LABELS[r.source] ?? "Клуб"} · до {new Date(r.expires_at).toLocaleDateString("ru-RU")}
                </p>
                <div className="mt-1"><RewardBundleChips bundle={r.reward} compact /></div>
              </div>
              <button
                onClick={() => claim.mutate({ id: r.id, title: r.title })}
                disabled={claim.isPending}
                className="rounded-xl bg-floodlight px-3 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
              >
                Забрать
              </button>
            </div>
          ))}
        </section>
      )}

      <p className="rounded-xl bg-white/5 px-3 py-2 text-xs leading-snug text-ink-mist">
        Клуб покупает за бюджет — награду получает каждый участник ({shop.member_count} чел.), кто был в клубе на момент покупки.
        {!shop.can_buy && " Покупают капитан, вице-капитан, казначей или ассистенты."}
      </p>
      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {shop.items.map((item) => {
        const soldOut = item.bought_this_week >= item.weekly_limit;
        return (
          <div key={item.id} className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-accent-lime/10 text-accent-lime">
                <IconShop size={18} />
              </span>
              <div className="min-w-0 flex-1">
                <p className="font-display text-sm font-bold text-ink-chalk">{item.name}</p>
                {item.description && <p className="text-caption text-ink-mist">{item.description}</p>}
                <div className="mt-1.5"><RewardBundleChips bundle={item.reward} compact /></div>
                <p className="mt-1 text-micro text-ink-mist-dim">
                  каждому участнику · на этой неделе {item.bought_this_week}/{item.weekly_limit}
                </p>
              </div>
            </div>
            {shop.can_buy && (
              <button
                onClick={() => setConfirmItem(item)}
                disabled={soldOut || buy.isPending || shop.budget < item.price}
                className="flex items-center justify-center gap-1 rounded-xl bg-floodlight py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
              >
                {soldOut ? "Лимит недели исчерпан" : <>Купить за {item.price} <IconCoin size={12} /></>}
              </button>
            )}
          </div>
        );
      })}

      <ConfirmDialog
        open={!!confirmItem}
        title={`Купить «${confirmItem?.name ?? ""}»?`}
        description={`С бюджета клуба спишется ${confirmItem?.price ?? 0} монет, а каждый участник сможет забрать награду.`}
        confirmLabel="Купить"
        onConfirm={() => { if (confirmItem) buy.mutate(confirmItem.id); setConfirmItem(null); }}
        onCancel={() => setConfirmItem(null)}
      />
      {granted && (
        <GrantedRewardModal title={granted.title} subtitle="Награда от клуба" granted={granted.data} onClose={() => setGranted(null)} />
      )}
    </div>
  );
}
