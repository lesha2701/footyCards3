import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Backdrop } from "@/components/magic/Backdrop";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import { buyMagicExtraRun, magicExtraRunInvoice } from "@/api/magic";
import { buyCosmeticWithCoins, createCosmeticStarsInvoice, equipCosmetic, fetchCosmetics } from "@/api/monetization";
import { IconCoin } from "@/components/icons";
import { ArtIcon, CastleArt, HeroArt } from "@/components/magic/art/mapObjects";
import { CLASS_LABEL, SKIN_CLASS } from "@/components/magic/magicMeta";
import { formatGameError } from "@/lib/errors";
import { payShopWithStars } from "@/lib/shopStars";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { CosmeticCatalogItem, MagicFactionCode, MagicHub, MagicMode } from "@/types";

/** The picked mode's runs today and one more for coins (the first) or Stars. */
export function MagicRunsCard({ hub, mode }: { hub: MagicHub; mode?: MagicMode }) {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [error, setError] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["magic-hub"] });
  const coins = useMutation({
    mutationFn: () => buyMagicExtraRun(mode?.code ?? "quick"),
    onSuccess: (r) => { updateBalance(r.balance); hapticNotify("success"); refresh(); },
    onError: (e) => setError(formatGameError(e, "Не получилось купить поход")),
  });
  const stars = async () => {
    setPaying(true);
    setError(null);
    try {
      if ((await payShopWithStars(() => magicExtraRunInvoice(mode?.code ?? "quick"))) === "paid") { hapticNotify("success"); refresh(); }
    } catch (e) {
      setError(formatGameError(e, "Покупка не прошла"));
    } finally {
      setPaying(false);
    }
  };
  const total = mode?.free_total ?? hub.daily_limit;
  const freeLeft = mode?.free_left ?? hub.free_left;
  const bank = mode?.bank ?? hub.bonus_runs;
  const priceCoins = mode ? mode.price_coins ?? null : hub.extra_price_coins;
  const priceStars = mode ? mode.price_stars ?? null : hub.extra_price_stars;
  return (
    <section className="rounded-3xl bg-bg-surface p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-bold text-ink-chalk">🎟 {mode ? `${mode.label}: походы сегодня` : "Походы на сегодня"}</p>
        <span className="flex gap-1">
          {Array.from({ length: total }, (_, i) => (
            <span key={i} className={`h-2.5 w-2.5 rounded-full ${i < freeLeft ? "bg-amber-300" : "bg-white/15"}`} />
          ))}
        </span>
      </div>
      <p className="mt-1 text-caption text-ink-mist">
        Бесплатных: {freeLeft} из {total}{bank > 0 ? ` · купленных: ${bank}` : ""}. У каждого режима свои походы, новые — завтра.
      </p>
      {freeLeft === 0 && bank === 0 && (priceCoins !== null || priceStars !== null) && (
        <div className="mt-2 grid grid-cols-1 gap-2">
          {priceCoins !== null && (
            <button disabled={coins.isPending} onClick={() => { setError(null); coins.mutate(); }}
              className="flex items-center justify-center gap-1 rounded-2xl bg-amber-400 py-2.5 text-sm font-black text-black active:scale-95 disabled:opacity-40">
              +1 поход · {priceCoins} <IconCoin size={13} />
            </button>
          )}
          {priceCoins === null && priceStars !== null && (
            <button disabled={paying} onClick={stars}
              className="rounded-2xl bg-gradient-to-r from-sky-400 to-indigo-500 py-2.5 text-sm font-black text-white active:scale-95 disabled:opacity-40">
              +1 поход · {priceStars} ⭐
            </button>
          )}
        </div>
      )}
      {freeLeft === 0 && bank === 0 && priceCoins !== null && priceStars !== null && (
        <p className="mt-1 text-micro text-ink-mist-dim">Следующий после него — за {priceStars} ⭐</p>
      )}
      {freeLeft === 0 && bank === 0 && priceCoins === null && priceStars === null && (
        <p className="mt-1 text-micro text-ink-mist-dim">Докупки на сегодня закончились — приходи завтра.</p>
      )}
      {error && <p className="mt-2 text-micro text-red-400">{error}</p>}
    </section>
  );
}

const MAGIC_KINDS = new Set(["magic_hero", "magic_castle"]);
const GLOW = "radial-gradient(circle at 50% 45%, rgba(251,191,36,0.22), transparent 60%), linear-gradient(180deg, rgba(30,27,75,0.9), rgba(15,23,42,0.9))";

const skinOf = (i: CosmeticCatalogItem) => i.style_key.replace(/^magic_(hero|castle)_/, "");

function Look({ kind, skin, faction, size }: { kind: string; skin: string; faction: MagicFactionCode; size: number }) {
  return (
    <ArtIcon size={size} tight={kind === "magic_hero"}>
      {kind === "magic_hero" ? <HeroArt faction={faction} skin={skin} heroClass={SKIN_CLASS[skin]} /> : <CastleArt faction={faction} skin={skin} />}
    </ArtIcon>
  );
}

/** Hero and castle skins for the run map — style only: a big showcase; a tap compares with the plain look. */
export function MagicSkins({ faction, heroClass }: { faction: MagicFactionCode; heroClass?: string }) {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [tab, setTab] = useState<"magic_hero" | "magic_castle">("magic_hero");
  const [openId, setOpenId] = useState<number | null>(null);
  const { data } = useQuery({ queryKey: ["cosmetics"], queryFn: fetchCosmetics });
  const classOf = (i: CosmeticCatalogItem) => SKIN_CLASS[skinOf(i)];
  const all = (data?.items ?? []).filter((i) => MAGIC_KINDS.has(i.kind) && i.is_active);
  // The chosen class's skins first.
  const items = all.filter((i) => i.kind === tab)
    .sort((a, b) => Number(classOf(b) === heroClass) - Number(classOf(a) === heroClass));
  const open = all.find((i) => i.id === openId) ?? null;
  if (!all.length) return null;

  const run = async (id: number, fn: () => Promise<unknown>) => {
    setBusy(id);
    setError(null);
    try {
      await fn();
      hapticNotify("success");
      const cat = await fetchCosmetics();
      queryClient.setQueryData(["cosmetics"], cat);
      updateBalance(cat.balance);
      queryClient.invalidateQueries({ queryKey: ["magic-hub"] });
    } catch (e) {
      setError(formatGameError(e, "Не получилось"));
    } finally {
      setBusy(null);
    }
  };

  const actions = (it: CosmeticCatalogItem, big = false) => {
    const size = big ? "py-3 text-sm" : "py-1.5 text-micro";
    if (it.owned) {
      return (
        <button disabled={busy === it.id} onClick={(e) => { e.stopPropagation(); run(it.id, () => equipCosmetic(it.kind, it.equipped ? null : it.id)); }}
          className={`w-full rounded-xl font-black active:scale-95 ${size} ${it.equipped ? "bg-white/10 text-ink-mist" : "bg-amber-400 text-black"}`}>
          {it.equipped ? "Снять" : "Надеть"}
        </button>
      );
    }
    return (
      <div className={`grid w-full gap-1 ${it.coins_price > 0 && it.stars_price > 0 ? "grid-cols-2" : "grid-cols-1"}`}>
        {it.coins_price > 0 && (
          <button disabled={busy === it.id} onClick={(e) => { e.stopPropagation(); run(it.id, () => buyCosmeticWithCoins(it.id)); }}
            className={`flex items-center justify-center gap-1 rounded-xl bg-amber-400 font-black text-black active:scale-95 disabled:opacity-40 ${size}`}>
            {it.coins_price} <IconCoin size={big ? 14 : 10} />
          </button>
        )}
        {it.stars_price > 0 && (
          <button disabled={busy === it.id} onClick={(e) => { e.stopPropagation(); run(it.id, () => payShopWithStars(() => createCosmeticStarsInvoice(it.id))); }}
            className={`rounded-xl bg-gradient-to-r from-sky-400 to-indigo-500 font-black text-white active:scale-95 disabled:opacity-40 ${size}`}>
            {it.stars_price} ⭐
          </button>
        )}
      </div>
    );
  };

  return (
    <section className="rounded-3xl bg-bg-surface p-3">
      <p className="text-sm font-black text-ink-chalk">🎨 Облик героя и замка</p>
      <p className="mb-2 text-micro text-ink-mist">Так твой герой и замок выглядят на карте похода. Только стиль — на силу не влияет. Нажми, чтобы сравнить.</p>
      <div className="mb-2 grid grid-cols-2 gap-1">
        {([["magic_hero", "🧙 Герои"], ["magic_castle", "🏰 Замки"]] as const).map(([k, label]) => (
          <button key={k} onClick={() => setTab(k)}
            className={`rounded-full py-1.5 text-xs font-bold active:scale-95 ${tab === k ? "bg-amber-400 text-black" : "bg-white/10 text-ink-mist"}`}>
            {label}
          </button>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-2">
        {items.map((it) => (
          <div key={it.id} role="button" tabIndex={0} onClick={() => setOpenId(it.id)}
            className={`relative flex flex-col items-center overflow-hidden rounded-2xl p-2 text-center ring-1 active:scale-[0.98] ${it.equipped ? "ring-2 ring-amber-300" : "ring-white/10"}`}
            style={{ background: GLOW }}>
            {it.equipped && <span className="absolute left-2 top-2 rounded-full bg-amber-300 px-1.5 text-[9px] font-black text-black">надет</span>}
            {it.owned && !it.equipped && <span className="absolute left-2 top-2 rounded-full bg-white/20 px-1.5 text-[9px] font-bold text-white">твой</span>}
            <Look kind={it.kind} skin={skinOf(it)} faction={faction} size={124} />
            <p className="w-full truncate text-xs font-black text-ink-chalk">{it.name}</p>
            <p className="text-[9px] font-bold text-amber-200/80">{it.kind === "magic_hero" ? CLASS_LABEL[classOf(it)] ?? "любой класс" : "замок"}</p>
            <p className="mt-0.5 line-clamp-2 min-h-[24px] text-[10px] leading-tight text-ink-mist">{it.description}</p>
            <div className="mt-1.5 w-full">{actions(it)}</div>
          </div>
        ))}
      </div>
      {error && <p className="mt-1 text-micro text-red-400">{error}</p>}

      <AnimatePresence>
        {open && (
          <Backdrop onClick={() => setOpenId(null)} className="fixed inset-0 z-[70] flex items-end justify-center bg-black/80 p-3">
            <motion.div initial={{ y: 60 }} animate={{ y: 0 }} exit={{ y: 60 }} onClick={(e) => e.stopPropagation()}
              className="safe-bottom w-full max-w-sm rounded-3xl bg-bg-surface p-4 ring-1 ring-white/10">
              <p className="text-center font-display text-xl font-black text-ink-chalk">{open.name}</p>
              <p className="text-center text-caption text-amber-200">
                {open.kind === "magic_hero" ? `Облик героя · ${CLASS_LABEL[classOf(open)] ?? "любой класс"}` : "Облик замка"}
              </p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <div className="flex flex-col items-center rounded-2xl bg-black/30 p-2">
                  <Look kind={open.kind} skin="default" faction={faction} size={130} />
                  <p className="text-micro text-ink-mist">Обычный</p>
                </div>
                <div className="flex flex-col items-center rounded-2xl p-2 ring-1 ring-amber-300/50" style={{ background: GLOW }}>
                  <Look kind={open.kind} skin={skinOf(open)} faction={faction} size={130} />
                  <p className="text-micro font-bold text-amber-200">✨ Этот облик</p>
                </div>
              </div>
              {open.description && <p className="mt-3 text-center text-caption text-ink-chalk">{open.description}</p>}
              <p className="mt-1 text-center text-micro text-ink-mist-dim">Виден на карте похода. На силу армии не влияет.</p>
              <div className="mt-3">{actions(open, true)}</div>
            </motion.div>
          </Backdrop>
        )}
      </AnimatePresence>
    </section>
  );
}
