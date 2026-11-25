import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { buyCosmeticWithCoins, createCosmeticStarsInvoice, fetchCosmetics } from "@/api/monetization";
import { setHallDecor, type HallDecor, type HallDecorItem, type HallSlot } from "@/api/profile";
import { formatGameError } from "@/lib/errors";
import { bannerArt, decorSrc, nicheSrc, pedestalSrc, plantArt, ropeArt } from "@/lib/hallArt";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { CosmeticCatalogItem, CosmeticKind } from "@/types";

interface Place {
  key: string;
  label: string;
  kind: CosmeticKind;
  /** Hall places the choice goes to (the two front places move together). */
  slots: HallSlot[];
  canEmpty: boolean;
  defaultName: string;
  defaultArt: string;
  art: (item: HallDecorItem) => string | null;
}

const PLACES: Place[] = [
  { key: "cabinet", label: "Ниша", kind: "hall_cabinet", slots: ["cabinet"], canEmpty: false, defaultName: "Орех", defaultArt: nicheSrc(null), art: nicheSrc },
  { key: "pedestal", label: "Постаменты", kind: "hall_pedestal", slots: ["pedestal"], canEmpty: false, defaultName: "Мрамор", defaultArt: pedestalSrc(null), art: pedestalSrc },
  { key: "corner", label: "Угол", kind: "hall_floor", slots: ["corner"], canEmpty: true, defaultName: "Пальма", defaultArt: plantArt, art: decorSrc },
  { key: "wall", label: "Стена", kind: "hall_wall", slots: ["wall"], canEmpty: true, defaultName: "Вымпел", defaultArt: bannerArt, art: decorSrc },
  { key: "front", label: "Вход", kind: "hall_front", slots: ["front_left", "front_right"], canEmpty: true, defaultName: "Канаты", defaultArt: ropeArt, art: decorSrc },
];

/** What a place shows: "default", "empty" or a cosmetic id. */
type Choice = "default" | "empty" | number;

const asItem = (c: CosmeticCatalogItem): HallDecorItem => ({ id: c.id, style_key: c.style_key, image_path: c.image_path ?? null });

/** «Обустроить зал»: the owner picks the look of each fixed place of the
 * hall — the niche and pedestal skins, and the decor in the corner, on the
 * wall and at the entrance. Tapping a tile tries it on in the room
 * («примерка»); buying goes through the usual cosmetics shop. */
export default function HallDecorPanel({ decor, onPreview }: { decor: HallDecor; onPreview: (d: HallDecor) => void }) {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const me = useAuthStore((s) => s.user);
  const [placeKey, setPlaceKey] = useState("pedestal");
  const [tried, setTried] = useState<Choice | null>(null);
  const [busy, setBusy] = useState<Choice | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { data } = useQuery({ queryKey: ["cosmetics"], queryFn: fetchCosmetics });
  const place = PLACES.find((p) => p.key === placeKey)!;
  const items = (data?.items ?? []).filter((i) => i.kind === place.kind && (i.is_active || i.owned));
  const current = decor[place.slots[0]];
  const now: Choice = current === undefined ? "default" : current === null ? "empty" : current.id;

  const show = (choice: Choice) => {
    const value = choice === "default" ? undefined : choice === "empty" ? null : asItem(items.find((i) => i.id === choice)!);
    const d: HallDecor = {};
    for (const slot of place.slots) d[slot] = value;
    return d;
  };
  const tryOn = (choice: Choice) => {
    setTried(choice);
    setError(null);
    // A place back to its default is shown by leaving it out of the preview.
    onPreview(choice === "default" ? Object.fromEntries(place.slots.map((s) => [s, undefined])) : show(choice));
  };
  const pickPlace = (key: string) => {
    setPlaceKey(key);
    setTried(null);
    setError(null);
    onPreview({});
  };

  const apply = async (choice: Choice, pay?: () => Promise<unknown>) => {
    setBusy(choice);
    setError(null);
    try {
      if (pay && (await pay()) === "cancelled") return;
      const id = choice === "default" ? null : choice === "empty" ? 0 : choice;
      for (const slot of place.slots) await setHallDecor(slot, id);
      hapticNotify("success");
      if (pay) {
        const cat = await fetchCosmetics();
        queryClient.setQueryData(["cosmetics"], cat);
        updateBalance(cat.balance);
      }
      await queryClient.invalidateQueries({ queryKey: ["hall", me?.id] });
      setTried(null);
      onPreview({});
    } catch (e) {
      setError(formatGameError(e, "Не получилось"));
    } finally {
      setBusy(null);
    }
  };

  const action = (choice: Choice, item?: CosmeticCatalogItem) => {
    if (choice === now) return <span className="block rounded-xl bg-white/10 py-1.5 text-micro font-black text-lime-300">Стоит</span>;
    const cls = "w-full rounded-xl py-1.5 text-micro font-black active:scale-95 disabled:opacity-50";
    if (!item || item.owned) {
      return (
        <button type="button" disabled={busy !== null} onClick={() => void apply(choice)} className={`${cls} bg-lime-400 text-black`}>
          Поставить
        </button>
      );
    }
    return (
      <div className="flex flex-col gap-1">
        {item.coins_price > 0 && (
          <button type="button" disabled={busy !== null} onClick={() => void apply(choice, () => buyCosmeticWithCoins(item.id))} className={`${cls} bg-amber-300 text-black`}>
            🪙 {item.coins_price.toLocaleString("ru-RU")}
          </button>
        )}
        {item.stars_price > 0 && (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void apply(choice, () => payShopWithStars(() => createCosmeticStarsInvoice(item.id)))}
            className={`${cls} bg-gradient-to-r from-sky-400 to-indigo-500 text-white`}
          >
            {item.stars_price} ⭐
          </button>
        )}
      </div>
    );
  };

  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-3 ring-1 ring-amber-300/20" data-testid="hall-decor">
      <div className="grid grid-cols-5 gap-1">
        {PLACES.map((p) => (
          <button
            key={p.key}
            type="button"
            onClick={() => pickPlace(p.key)}
            className={`rounded-xl px-0.5 py-2 text-[10px] font-bold ${p.key === placeKey ? "bg-amber-300 text-black" : "bg-white/5 text-ink-mist"}`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <p className="text-micro text-ink-mist">Нажми на предмет — он встанет в зале на примерку. Только внешний вид.</p>
      <div className="grid grid-cols-3 gap-2">
        <Tile title={place.defaultName} img={place.defaultArt} active={(tried ?? now) === "default"} onTry={() => tryOn("default")}>
          {action("default")}
        </Tile>
        {place.canEmpty && (
          <Tile title="Пусто" active={(tried ?? now) === "empty"} onTry={() => tryOn("empty")}>
            {action("empty")}
          </Tile>
        )}
        {items.map((it) => (
          <Tile key={it.id} title={it.name} hint={it.description} img={place.art(asItem(it))} active={(tried ?? now) === it.id} onTry={() => tryOn(it.id)}>
            {action(it.id, it)}
          </Tile>
        ))}
      </div>
      {!items.length && <p className="text-center text-micro text-ink-mist-dim">Новые предметы для этого места скоро появятся</p>}
      {error && <p className="text-center text-caption text-red-300">{error}</p>}
    </section>
  );
}

function Tile({ title, img, hint, active, onTry, children }: {
  title: string; img?: string | null; hint?: string | null; active: boolean; onTry: () => void; children: React.ReactNode;
}) {
  return (
    <div className={`flex flex-col items-center gap-1.5 rounded-2xl p-2 text-center ${active ? "bg-amber-300/15 ring-2 ring-amber-300" : "bg-white/5 ring-1 ring-white/10"}`}>
      <button type="button" onClick={onTry} className="flex h-16 w-full items-end justify-center" data-testid="hall-decor-try">
        {img ? <img src={img} alt="" className="max-h-full max-w-full object-contain drop-shadow-[0_4px_6px_rgba(0,0,0,0.5)]" /> : <span className="text-2xl text-ink-mist-dim">∅</span>}
      </button>
      <p className="text-micro font-bold leading-tight text-ink-chalk" title={hint ?? undefined}>{title}</p>
      <div className="mt-auto w-full">{children}</div>
    </div>
  );
}
