import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import EmptyState from "@/components/common/EmptyState";
import { CardGridSkeleton } from "@/components/common/Skeleton";
import { fetchPacks } from "@/api/packs";
import { staticUrl } from "@/lib/api";
import { RARITY_LABELS } from "@/lib/rarity";
import { useAuthStore } from "@/store/authStore";
import type { Pack } from "@/types";

export default function PacksPage() {
  const { data: packs, isLoading } = useQuery({ queryKey: ["packs"], queryFn: fetchPacks });
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const navigate = useNavigate();

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-2xl font-bold text-slate-100">Паки</h1>
      {isLoading && <CardGridSkeleton count={3} />}
      {!isLoading && !packs?.length && <EmptyState icon="📦" title="Паков пока нет" description="Загляни позже" />}
      <div className="grid grid-cols-1 gap-4">
        {packs?.map((pack) => (
          <PackCard key={pack.id} pack={pack} canAfford={balance >= pack.price} onOpen={() => navigate(`/packs/${pack.id}/open`)} />
        ))}
      </div>
    </div>
  );
}

function PackCard({ pack, canAfford, onOpen }: { pack: Pack; canAfford: boolean; onOpen: () => void }) {
  const disabled = !pack.is_available_now || (pack.purchase_limit_per_user !== null && pack.user_purchase_count >= pack.purchase_limit_per_user);

  return (
    <div className="overflow-hidden rounded-3xl border border-white/10 bg-bg-surface">
      <div className="flex">
        <img src={staticUrl(pack.image_path ?? undefined)} alt={pack.name} className="h-36 w-32 object-cover" />
        <div className="flex flex-1 flex-col justify-between p-3">
          <div>
            <p className="font-display text-base font-bold text-slate-100">{pack.name}</p>
            <p className="mt-1 text-xs text-slate-400">{pack.description}</p>
            <div className="mt-2 flex flex-wrap gap-1">
              {pack.rarity_probabilities.map((rp) => (
                <span key={rp.rarity} className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] text-slate-300">
                  {RARITY_LABELS[rp.rarity]} {Math.round(rp.probability * 100)}%
                </span>
              ))}
            </div>
          </div>
          <div className="mt-2 flex items-center justify-between">
            <span className="font-display text-sm font-bold text-amber-300">🪙 {pack.price}</span>
            <button
              onClick={onOpen}
              disabled={disabled || !canAfford}
              className="rounded-full bg-accent px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40 active:scale-95"
            >
              {disabled ? "Недоступно" : canAfford ? "Открыть" : "Не хватает монет"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
