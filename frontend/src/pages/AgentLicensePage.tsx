import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ListSkeleton } from "@/components/common/Skeleton";
import { AgentIcon } from "@/components/market/AgentBadge";
import { createAgentLicenseInvoice, fetchAgentLicense, fetchAuctionInfo } from "@/api/auction";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString("ru-RU", { day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
}

/** «Агентская лицензия»: what it gives, its price and term, pay with Stars. */
export default function AgentLicensePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [paid, setPaid] = useState(false);
  const { data: license, isLoading } = useQuery({ queryKey: ["auction", "license"], queryFn: fetchAgentLicense });
  const { data: info } = useQuery({ queryKey: ["auction", "info"], queryFn: fetchAuctionInfo });

  const buy = useMutation({
    mutationFn: () => payShopWithStars(createAgentLicenseInvoice),
    onSuccess: (status) => {
      setError(null);
      if (status === "paid") {
        hapticNotify("success");
        setPaid(true);
      }
      queryClient.invalidateQueries({ queryKey: ["auction"] });
    },
    onError: (err) => {
      hapticNotify("error");
      setError(formatGameError(err, err instanceof Error ? err.message : "Не удалось оплатить"));
    },
  });

  if (isLoading || !license) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-3xl bg-gradient-to-br from-amber-400/25 via-bg-surface to-bg-surface p-5">
        <AgentIcon size={56} />
        <h1 className="mt-2 font-display text-xl font-bold text-ink-chalk">Агентская лицензия</h1>
        <p className="mt-1 text-sm text-ink-mist">
          Право выставлять свои карточки на «Трансферный рынок». Ставить и покупать лоты можно и без лицензии.
        </p>
        {license.active && license.expires_at && (
          <p className="mt-3 rounded-xl bg-accent-green/15 px-3 py-2 text-sm font-semibold text-accent-green">
            Ты агент до {formatDate(license.expires_at)}
          </p>
        )}
        {license.revoked && (
          <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-300">Лицензия отозвана администрацией</p>
        )}
      </div>

      <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4 text-sm text-ink-mist">
        <p className="font-semibold text-ink-chalk">Что даёт</p>
        <p>• Выставлять карточки на рынок{info ? ` — до ${info.max_active_lots} лотов одновременно` : ""}</p>
        <p>• Значок «Агент» рядом с твоим именем в каждом лоте</p>
        <p>• Срок — {license.days} дн. Покупка до окончания продлевает лицензию, дни складываются</p>
        {info && <p>• С каждой продажи сгорает комиссия рынка {info.fee_pct}%</p>}
      </section>

      <section className="flex flex-col gap-1 rounded-2xl bg-white/5 p-4 text-caption text-ink-mist">
        <p className="font-semibold text-ink-chalk">Кто может купить</p>
        <p>Аккаунты старше {license.min_account_age_days} дн.{license.requires_verified ? " со статусом «Проверенный аккаунт»" : ""}.</p>
        <p>Если аккаунт заблокирован или ему запрещена торговля, выставлять лоты нельзя даже с лицензией.</p>
      </section>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
      {paid && (
        <p className="rounded-xl bg-accent-green/10 px-3 py-2 text-sm text-accent-green">
          Оплата прошла — лицензия активна.
        </p>
      )}

      {license.buy_block_reason ? (
        <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-sm text-amber-300">{license.buy_block_reason}</p>
      ) : (
        <button
          disabled={buy.isPending}
          onClick={() => buy.mutate()}
          className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-40"
        >
          {buy.isPending ? "Оплата…" : `${license.active ? "Продлить" : "Купить"} на ${license.days} дн. за ${license.stars} ⭐`}
        </button>
      )}

      {license.active && (
        <button
          onClick={() => navigate("/market/new")}
          className="rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-chalk active:scale-95"
        >
          Выставить карточку
        </button>
      )}
    </div>
  );
}
