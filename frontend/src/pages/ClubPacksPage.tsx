import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { IconChevronLeft } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchClubPacks, openClubPack } from "@/api/clubPacks";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import type { ClubPackOpenResult } from "@/types";

export default function ClubPacksPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: packs, isLoading } = useQuery({ queryKey: ["clubs", "packs"], queryFn: fetchClubPacks });
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ClubPackOpenResult | null>(null);

  const openMutation = useMutation({
    mutationFn: (packId: number) => openClubPack(packId),
    onSuccess: (data) => {
      setResult(data);
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["clubs"] });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось открыть пак")),
  });

  if (isLoading) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/clubs")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Клубные паки</h1>
      </div>

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {result && (
        <div className="rounded-2xl bg-bg-surface p-4">
          <p className="mb-2 font-display text-sm font-bold text-ink-chalk">Получено:</p>
          <div className="grid grid-cols-3 gap-2">
            {result.cards.map((oc) => (
              <div key={oc.card.id} className="flex flex-col items-center gap-1 rounded-xl bg-bg-base p-1.5">
                <img
                  src={staticUrl(oc.card.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                  alt="" className="aspect-square w-full rounded-lg object-cover"
                />
                <span className="font-mono text-[9px] text-ink-mist-dim">{oc.card.player.display_name}</span>
                {oc.is_new && <span className="text-[9px] text-accent-lime">Новый!</span>}
              </div>
            ))}
          </div>
          <p className="mt-2 text-xs text-ink-mist-dim">Новый бюджет: 🪙 {result.new_budget}</p>
        </div>
      )}

      <div className="flex flex-col gap-2">
        {(packs ?? []).map((pack) => (
          <div key={pack.id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
            <img
              src={staticUrl(pack.image_path ?? undefined) ?? staticUrl("packs/basic.webp")}
              alt="" className="h-14 w-14 rounded-xl object-cover"
            />
            <div className="flex-1">
              <p className="font-display text-sm font-bold text-ink-chalk">{pack.name}</p>
              <p className="text-xs text-ink-mist-dim">{pack.card_count} карточки · 🪙 {pack.price}</p>
            </div>
            <button
              onClick={() => openMutation.mutate(pack.id)}
              disabled={openMutation.isPending}
              className="rounded-xl bg-accent-green px-3 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
            >
              Открыть
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
