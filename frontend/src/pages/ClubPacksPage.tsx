import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { IconChevronLeft, IconCoin } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchClubPacks } from "@/api/clubPacks";
import { fetchMyClub } from "@/api/clubs";
import QuantitySheet from "@/components/shop/QuantitySheet";
import type { ClubPack } from "@/types";
import { staticUrl } from "@/lib/api";

export default function ClubPacksPage() {
  const navigate = useNavigate();
  const { data: packs, isLoading } = useQuery({ queryKey: ["clubs", "packs"], queryFn: fetchClubPacks });
  const { data: club } = useQuery({ queryKey: ["clubs", "me"], queryFn: fetchMyClub, retry: false });
  const [choosing, setChoosing] = useState<ClubPack | null>(null);
  const budget = club?.budget ?? 0;

  if (isLoading) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Клубные паки</h1>
      </div>

      <div className="flex flex-col gap-2">
        {(packs ?? []).map((pack) => (
          <div key={pack.id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
            <img decoding="async" loading="lazy"
              src={staticUrl(pack.image_path ?? undefined) ?? staticUrl("packs/basic.webp")}
              alt="" className="h-14 w-14 rounded-xl object-cover"
            />
            <div className="flex-1">
              <p className="font-display text-sm font-bold text-ink-chalk">{pack.name}</p>
              <p className="flex items-center gap-1 text-xs text-ink-mist-dim">
                {pack.card_count} карточки · <IconCoin size={11} /> {pack.price}
              </p>
            </div>
            <button
              onClick={() => setChoosing(pack)}
              className="rounded-xl bg-accent-green px-3 py-2 text-xs font-bold text-bg-base active:scale-95"
            >
              Открыть
            </button>
          </div>
        ))}
      </div>

      {choosing && (
        <QuantitySheet
          name={choosing.name}
          unitPrice={choosing.price}
          balance={budget}
          balanceLabel="в бюджете клуба"
          maxQuantity={20}
          note={`До 20 за раз · бюджет клуба: ${budget.toLocaleString("ru-RU")}`}
          onClose={() => setChoosing(null)}
          onConfirm={(quantity) => {
            const pack = choosing;
            setChoosing(null);
            navigate(`/clubs/packs/${pack.id}/open`, quantity > 1 ? { state: { quantity } } : undefined);
          }}
        />
      )}
    </div>
  );
}
