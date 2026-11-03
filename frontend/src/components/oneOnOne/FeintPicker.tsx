import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { equipMyPlayerCosmetic, fetchMyPlayer } from "@/api/myPlayer";
import { formatGameError } from "@/lib/errors";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { FEINTS } from "@/lib/oneOnOne/feints";

/** Which feint he does: the plain sidestep, or a «Мой игрок» style item
 * (Stars; the same move in the engine — only how it looks). */
export default function FeintPicker({ value, onChange }: { value: string | null; onChange: (code: string | null) => void }) {
  const queryClient = useQueryClient();
  const { data: player, isError: noPlayer } = useQuery({ queryKey: ["my-player"], queryFn: fetchMyPlayer, retry: false });
  const [error, setError] = useState<string | null>(null);
  const catalog = player?.cosmetics.catalog ?? [];

  const choose = useMutation({
    mutationFn: async (code: string | null) => {
      const item = code ? catalog.find((i) => i.code === code) : null;
      if (code && item && !item.owned) {
        // Bought for Stars, it is put on by the delivery.
        if ((await payMyPlayerWithStars({ purchase: "cosmetic", code })) === "cancelled") return { done: false, code };
      } else {
        await equipMyPlayerCosmetic("feint", code);
      }
      return { done: true, code };
    },
    onSuccess: ({ done, code }) => {
      if (done) onChange(code);
      void queryClient.invalidateQueries({ queryKey: ["my-player"] });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось сменить финт")),
  });

  const pick = (code: string | null) => {
    if (choose.isPending || code === value) return;
    setError(null);
    if (code && noPlayer) {
      setError("Финты — стиль «Моего игрока»: сначала создай его");
      return;
    }
    choose.mutate(code);
  };

  return (
    <div className="pointer-events-auto flex flex-col items-center gap-1.5">
      <div className="flex items-center gap-1.5 rounded-2xl bg-black/55 p-1 text-xs font-semibold backdrop-blur">
        <span className="px-2 text-white/70">Финт</span>
        <button
          type="button"
          onClick={() => pick(null)}
          className={`rounded-xl px-3 py-1.5 ${value === null ? "bg-accent text-black" : "text-white"}`}
        >
          ↔ Шаг в сторону
        </button>
        {Object.entries(FEINTS).map(([code, f]) => {
          const item = catalog.find((i) => i.code === code);
          const locked = !item?.owned;
          return (
            <button
              key={code}
              type="button"
              onClick={() => pick(code)}
              disabled={choose.isPending}
              className={`flex items-center gap-1 rounded-xl px-3 py-1.5 ${value === code ? "bg-accent text-black" : "text-white"}`}
            >
              {f.emoji} {f.label}
              {locked && item && item.stars_price > 0 && <span className="text-[10px] text-amber-300">⭐{item.stars_price}</span>}
            </button>
          );
        })}
      </div>
      {error && <p className="rounded-lg bg-red-500/20 px-2 py-1 text-xs text-red-200">{error}</p>}
    </div>
  );
}
