import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import EmptyState from "@/components/common/EmptyState";
import { IconChevronUp, IconCoin, IconPack } from "@/components/icons";
import { CardGridSkeleton } from "@/components/common/Skeleton";
import { fetchPacks } from "@/api/packs";
import { staticUrl } from "@/lib/api";
import { sortPacksByPrice, type PackSortDirection } from "@/lib/packs";
import { RARITY_LABELS } from "@/lib/rarity";
import { useAuthStore } from "@/store/authStore";
import type { Pack } from "@/types";

export default function PacksPage() {
  const { data: packs, isLoading } = useQuery({ queryKey: ["packs"], queryFn: fetchPacks });
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const navigate = useNavigate();
  const [sortDirection, setSortDirection] = useState<PackSortDirection>("asc");

  const sortedPacks = packs ? sortPacksByPrice(packs, sortDirection) : undefined;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Паки</h1>
        <button
          onClick={() => setSortDirection((d) => (d === "asc" ? "desc" : "asc"))}
          className="flex items-center gap-1.5 rounded-full bg-bg-surface px-3 py-1.5 font-mono text-xs text-ink-mist active:scale-95"
        >
          <IconChevronUp size={12} className={`transition-transform ${sortDirection === "asc" ? "" : "rotate-180"}`} />
          {sortDirection === "asc" ? "Дешевле → дороже" : "Дороже → дешевле"}
        </button>
      </div>
      {isLoading && <CardGridSkeleton count={3} />}
      {!isLoading && !packs?.length && <EmptyState icon={IconPack} title="Паков пока нет" description="Загляни позже" />}
      <div className="grid grid-cols-1 gap-4">
        {sortedPacks?.map((pack) => (
          <PackCard key={pack.id} pack={pack} canAfford={balance >= pack.price} onOpen={() => navigate(`/packs/${pack.id}/open`)} />
        ))}
      </div>
    </div>
  );
}

function PackCard({ pack, canAfford, onOpen }: { pack: Pack; canAfford: boolean; onOpen: () => void }) {
  const disabled = !pack.is_available_now || (pack.purchase_limit_per_user !== null && pack.user_purchase_count >= pack.purchase_limit_per_user);

  return (
    <div className="overflow-hidden rounded-3xl bg-bg-surface">
      <div className="flex">
        <img src={staticUrl(pack.image_path ?? undefined)} alt={pack.name} className="h-36 w-32 object-cover" />
        <div className="flex flex-1 flex-col justify-between p-3">
          <div>
            <p className="font-display text-base font-bold text-ink-chalk">{pack.name}</p>
            <p className="mt-1 text-xs text-ink-mist">{pack.description}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {pack.rarity_probabilities.map((rp) => (
                <span key={rp.rarity} className="rounded-full bg-bg-raised px-2 py-0.5 font-mono text-[10px] text-ink-mist">
                  {RARITY_LABELS[rp.rarity]} {Math.round(rp.probability * 100)}%
                </span>
              ))}
            </div>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span className="flex items-center gap-1.5 font-mono text-sm font-semibold text-accent-lime">
              <IconCoin size={15} />
              {pack.price}
            </span>
            <button
              onClick={onOpen}
              disabled={disabled || !canAfford}
              className="rounded-full bg-floodlight px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40 disabled:grayscale active:scale-95"
            >
              {disabled ? "Недоступно" : canAfford ? "Открыть" : "Не хватает монет"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
