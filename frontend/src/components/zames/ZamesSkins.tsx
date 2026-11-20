import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { createCosmeticStarsInvoice, equipCosmetic, fetchCosmetics } from "@/api/monetization";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { CosmeticCatalogItem } from "@/types";

const THUMBS = import.meta.glob<string>("@/assets/zames/skins/*.webp", { eager: true, import: "default" });
const thumb = (key: string) => THUMBS[`/src/assets/zames/skins/${key}.webp`];

/** «Облик героя»: hero skins of «Замес» (cosmetics kind "zames_hero") for Stars — the look only. */
export default function ZamesSkins() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [busy, setBusy] = useState<number | "plain" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["cosmetics"], queryFn: fetchCosmetics });
  const skins = (data?.items ?? []).filter((i) => i.kind === "zames_hero" && (i.is_active || i.owned));
  if (!skins.length) return null;
  const worn = skins.find((i) => i.equipped) ?? null;

  const run = async (id: number | "plain", fn: () => Promise<unknown>) => {
    setBusy(id);
    setError(null);
    try {
      if ((await fn()) === "cancelled") return;
      hapticNotify("success");
      const cat = await fetchCosmetics();
      queryClient.setQueryData(["cosmetics"], cat);
      updateBalance(cat.balance);
      void queryClient.invalidateQueries({ queryKey: ["zames-info"] });
    } catch (e) {
      setError(formatGameError(e, "Не получилось"));
    } finally {
      setBusy(null);
    }
  };

  const action = (it: CosmeticCatalogItem) => {
    if (it.equipped) return <span className="block rounded-xl bg-white/10 py-1.5 text-micro font-black text-lime-300">Надет</span>;
    if (it.owned) {
      return (
        <button type="button" disabled={busy === it.id} onClick={() => void run(it.id, () => equipCosmetic("zames_hero", it.id))}
          className="w-full rounded-xl bg-lime-400 py-1.5 text-micro font-black text-black active:scale-95 disabled:opacity-50">
          Надеть
        </button>
      );
    }
    return (
      <button type="button" disabled={busy === it.id} onClick={() => void run(it.id, () => payShopWithStars(() => createCosmeticStarsInvoice(it.id)))}
        className="w-full rounded-xl bg-gradient-to-r from-sky-400 to-indigo-500 py-1.5 text-micro font-black text-white active:scale-95 disabled:opacity-50">
        {it.stars_price} ⭐
      </button>
    );
  };

  return (
    <section className="rounded-3xl bg-bg-surface p-4 ring-1 ring-white/10">
      <h2 className="font-display text-base font-bold text-ink-chalk">Облик героя</h2>
      <p className="mt-0.5 text-micro text-ink-mist">Только внешний вид — на силу ударов не влияет.</p>
      <div className="mt-3 grid grid-cols-3 gap-2">
        <Tile title="Свой парень" img={thumb("hero")} active={!worn}>
          {worn ? (
            <button type="button" disabled={busy === "plain"} onClick={() => void run("plain", () => equipCosmetic("zames_hero", null))}
              className="w-full rounded-xl bg-white/10 py-1.5 text-micro font-black text-ink-chalk active:scale-95 disabled:opacity-50">
              Надеть
            </button>
          ) : (
            <span className="block rounded-xl bg-white/10 py-1.5 text-micro font-black text-lime-300">Надет</span>
          )}
        </Tile>
        {skins.map((it) => (
          <Tile key={it.id} title={it.name} img={thumb(it.style_key)} active={it.equipped} hint={it.description}>
            {action(it)}
          </Tile>
        ))}
      </div>
      {error ? <p className="mt-2 text-center text-caption text-red-300">{error}</p> : null}
    </section>
  );
}

function Tile({ title, img, active, hint, children }: {
  title: string; img?: string; active: boolean; hint?: string | null; children: React.ReactNode;
}) {
  return (
    <div className={`flex flex-col items-center gap-1.5 rounded-2xl p-2 text-center ${active ? "bg-lime-400/15 ring-2 ring-lime-400" : "bg-white/5 ring-1 ring-white/10"}`}>
      <div className="flex h-24 w-full items-end justify-center">
        {img ? <img src={img} alt="" className="max-h-full max-w-full object-contain drop-shadow-[0_4px_6px_rgba(0,0,0,0.5)]" /> : null}
      </div>
      <p className="text-micro font-bold leading-tight text-ink-chalk" title={hint ?? undefined}>{title}</p>
      <div className="mt-auto w-full">{children}</div>
    </div>
  );
}
