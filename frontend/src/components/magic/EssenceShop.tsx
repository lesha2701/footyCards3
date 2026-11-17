import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence } from "framer-motion";
import { useState } from "react";

import { buyMagicShopItem, fetchMagicShop } from "@/api/magic";
import { ArtIcon, CastleArt, HeroArt } from "@/components/magic/art/mapObjects";
import { pngArt, uiArt } from "@/components/magic/art/pngArt";
import { PackReveal } from "@/components/magic/MagicPack";
import { EssenceIcon } from "@/components/magic/MagicLosses";
import { SKIN_CLASS } from "@/components/magic/magicMeta";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import type { MagicCreature, MagicFactionCode, MagicShopItem } from "@/types";

function ItemArt({ it, faction }: { it: MagicShopItem; faction: MagicFactionCode }) {
  if (it.kind === "skin" && it.style_key) {
    const skin = it.style_key.replace(/^magic_(hero|castle)_/, "");
    return (
      <ArtIcon size={64} tight={it.skin_kind === "magic_hero"}>
        {it.skin_kind === "magic_hero" ? <HeroArt faction={faction} skin={skin} heroClass={SKIN_CLASS[skin]} /> : <CastleArt faction={faction} skin={skin} />}
      </ArtIcon>
    );
  }
  const img = it.kind === "pack" ? uiArt("magic_pack") : it.kind === "leadership" ? uiArt("icon_leadership") : null;
  if (img) return <img src={img} alt="" className="h-14 w-14 object-contain" />;
  return <span className="text-4xl">{it.kind === "mana" ? "🔮" : "✨"}</span>;
}

/** «Лавка эссенции»: what the essence of the fallen buys — packs, permanent leadership / mana, looks. */
export function EssenceShop({ faction }: { faction: MagicFactionCode }) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [opened, setOpened] = useState<MagicCreature[] | null>(null);
  const { data } = useQuery({ queryKey: ["magic-shop"], queryFn: fetchMagicShop });
  const buy = useMutation({
    mutationFn: buyMagicShopItem,
    onSuccess: (r) => {
      hapticNotify("success");
      if (r.cards.length) setOpened(r.cards);
      queryClient.invalidateQueries({ queryKey: ["magic-shop"] });
      queryClient.invalidateQueries({ queryKey: ["magic-hub"] });
      queryClient.invalidateQueries({ queryKey: ["cosmetics"] });
    },
    onError: (e) => setError(formatGameError(e, "Не получилось купить")),
  });
  if (!data || !data.items.length) return null;
  const shopImg = pngArt("objects/essence_shop");
  const groups: [string, MagicShopItem[]][] = [
    ["Усиления героя", data.items.filter((i) => i.kind === "leadership" || i.kind === "mana")],
    ["Паки", data.items.filter((i) => i.kind === "pack")],
    ["Облики", data.items.filter((i) => i.kind === "skin")],
  ];
  return (
    <section className="rounded-3xl bg-gradient-to-b from-cyan-950/60 to-bg-surface p-3 ring-1 ring-cyan-300/20">
      <div className="flex items-center gap-3">
        {shopImg && <img src={shopImg} alt="" className="h-16 w-16 shrink-0 object-contain drop-shadow-[0_0_12px_rgba(34,211,238,0.45)]" />}
        <div className="min-w-0 flex-1">
          <p className="font-display text-base font-black text-ink-chalk">Лавка эссенции</p>
          <p className="text-[10px] leading-snug text-ink-mist">Эссенцию дают существа, павшие навсегда. Здесь она превращается в силу героя, новые карты и облики.</p>
        </div>
      </div>
      <p className="mt-2 flex items-center justify-center gap-1 rounded-xl bg-black/30 py-1.5 font-mono text-sm font-black text-cyan-100">
        <EssenceIcon size={16} /> {data.essence}
      </p>
      {groups.filter(([, items]) => items.length).map(([title, items]) => (
        <div key={title} className="mt-3">
          <p className="mb-1.5 text-[11px] font-bold uppercase tracking-wide text-ink-mist">{title}</p>
          <div className="grid grid-cols-2 gap-2">
            {items.map((it) => {
              const short = data.essence < it.price;
              return (
                <div key={it.code} className={`flex flex-col items-center rounded-2xl bg-black/30 p-2 text-center ring-1 ring-white/5 ${it.available ? "" : "opacity-60"}`}>
                  <ItemArt it={it} faction={faction} />
                  <p className="mt-1 w-full truncate text-xs font-black text-ink-chalk">{it.title}</p>
                  <p className="line-clamp-2 min-h-[24px] text-[10px] leading-tight text-ink-mist">{it.text}</p>
                  {it.max !== null && <p className="text-[9px] font-bold text-amber-200">куплено {it.owned} / {it.max}</p>}
                  <button disabled={!it.available || short || buy.isPending} onClick={() => { setError(null); buy.mutate(it.code); }}
                    className="mt-1.5 flex w-full items-center justify-center gap-1 rounded-xl bg-cyan-400 py-1.5 text-micro font-black text-black active:scale-95 disabled:bg-white/10 disabled:text-ink-mist">
                    {!it.available ? (it.kind === "skin" ? "Уже твой" : "Максимум") : <>{it.price} <EssenceIcon size={11} /></>}
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      ))}
      {error && <p className="mt-2 text-micro text-red-400">{error}</p>}
      <AnimatePresence>{opened && <PackReveal cards={opened} onClose={() => setOpened(null)} />}</AnimatePresence>
    </section>
  );
}
