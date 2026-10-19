import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { fetchArtifacts, fetchCosmetics } from "@/api/monetization";
import { fetchDailyOffer, fetchPacks } from "@/api/packs";
import { IconCoin } from "@/components/icons";
import CosmeticPreview from "@/components/shop/CosmeticPreview";
import { staticUrl } from "@/lib/api";
import { useAuthStore } from "@/store/authStore";

type ShowcaseItem = {
  key: string;
  visual: ReactNode;
  name: string;
  badge?: string;
  oldPrice?: number;
  coins?: number;
  stars?: number;
  to: string;
};

/** Today's date (local) as a seed: the same pick all day, a new one tomorrow. */
function todaySeed(): number {
  const d = new Date();
  const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
  let h = 2166136261;
  for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 16777619);
  return h >>> 0;
}

function pickSeeded<T>(items: T[], count: number, seed: number): T[] {
  const pool = [...items];
  const out: T[] = [];
  let s = seed || 1;
  while (pool.length && out.length < count) {
    s = (Math.imul(s, 1103515245) + 12345) >>> 0;
    out.push(pool.splice(s % pool.length, 1)[0]);
  }
  return out;
}

function hoursToMidnight(): number {
  const now = new Date();
  const midnight = new Date(now);
  midnight.setHours(24, 0, 0, 0);
  return Math.max(1, Math.ceil((midnight.getTime() - now.getTime()) / 3_600_000));
}

/** «Витрина дня»: the discounted pack of the day plus two shop items
 * (artifacts, cosmetics) that rotate daily. Prices are informative — every
 * tile opens the shop page where the server charges. */
export default function ShowcaseCard() {
  const navigate = useNavigate();
  const avatarUrl = useAuthStore((s) => s.user?.avatar_url ?? undefined);
  // Same keys as the shop pages, so the caches are shared.
  const { data: offer } = useQuery({ queryKey: ["packs", "daily-offer"], queryFn: fetchDailyOffer });
  const { data: packs } = useQuery({ queryKey: ["packs"], queryFn: fetchPacks });
  const { data: artifacts } = useQuery({ queryKey: ["artifacts"], queryFn: fetchArtifacts });
  const { data: cosmetics } = useQuery({ queryKey: ["cosmetics"], queryFn: fetchCosmetics });

  const seed = todaySeed();
  const items: ShowcaseItem[] = [];

  const packImg = (path: string | null | undefined) => (
    <img decoding="async" loading="lazy" src={staticUrl(path ?? undefined)} alt="" className="h-full w-full object-cover" />
  );
  if (offer && !offer.claimed_today) {
    items.push({
      key: "offer",
      visual: packImg(offer.pack.image_path),
      name: offer.pack.name,
      badge: `−${offer.discount_pct}%`,
      oldPrice: offer.pack.price,
      coins: offer.price,
      to: "/packs",
    });
  } else {
    const coinPacks = (packs ?? []).filter((p) => p.stars_price == null);
    const [pack] = pickSeeded(coinPacks, 1, seed);
    if (pack) items.push({ key: `pack-${pack.id}`, visual: packImg(pack.image_path), name: pack.name, coins: pack.price, to: "/packs" });
  }

  const pool: ShowcaseItem[] = [
    ...(artifacts?.enabled
      ? artifacts.shop
          .filter((a) => a.owned_count === 0 && a.left !== 0 && (a.coins_price > 0 || a.stars_price > 0))
          .map((a) => ({
            key: `art-${a.id}`,
            visual: a.image_path ? packImg(a.image_path) : <span className="text-2xl">{a.icon}</span>,
            name: a.name,
            badge: a.left != null ? `ост. ${a.left}` : undefined,
            coins: a.coins_price || undefined,
            stars: a.coins_price ? undefined : a.stars_price,
            to: "/artifacts",
          }))
      : []),
    ...(cosmetics?.items ?? [])
      .filter((c) => !c.owned && c.is_active && (c.coins_price > 0 || c.stars_price > 0))
      .map((c) => ({
        key: `cos-${c.id}`,
        visual: <span className="origin-center scale-90"><CosmeticPreview item={c} avatarUrl={avatarUrl} /></span>,
        name: c.name,
        badge: c.is_exclusive ? "эксклюзив" : undefined,
        coins: c.coins_price || undefined,
        stars: c.coins_price ? undefined : c.stars_price,
        to: "/style",
      })),
  ];
  items.push(...pickSeeded(pool, 3 - items.length, seed ^ 0x9e3779b9));

  if (!items.length) return null;

  return (
    <section>
      <div className="mb-2 flex items-end justify-between">
        <div>
          <h2 className="font-display text-base font-bold text-ink-chalk">Витрина дня</h2>
          <p className="text-caption text-ink-mist">Обновится через {hoursToMidnight()} ч</p>
        </div>
        <button onClick={() => navigate("/packs")} className="font-mono text-xs text-accent-lime">Магазин →</button>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {items.map((item) => (
          <button
            key={item.key}
            onClick={() => navigate(item.to)}
            className="flex min-w-0 flex-col overflow-hidden rounded-2xl bg-bg-surface text-left active:scale-[0.97]"
          >
            <span className="relative flex h-[86px] w-full items-center justify-center overflow-hidden bg-bg-raised">
              {item.visual}
              {item.badge && (
                <span className="absolute left-1.5 top-1.5 rounded-full bg-accent-lime px-1.5 py-px text-micro font-bold text-bg-base">
                  {item.badge}
                </span>
              )}
            </span>
            <span className="flex min-w-0 flex-col px-2 py-1.5">
              <span className="truncate text-xs font-semibold text-ink-chalk">{item.name}</span>
              <span className="flex items-center gap-1 font-mono text-caption">
                {item.oldPrice != null && <span className="text-ink-mist-dim line-through">{item.oldPrice}</span>}
                {item.coins != null ? (
                  <span className="flex items-center gap-0.5 font-bold text-accent-lime">
                    <IconCoin size={11} />
                    {item.coins.toLocaleString("ru-RU")}
                  </span>
                ) : (
                  <span className="font-bold text-amber-300">{item.stars} ⭐</span>
                )}
              </span>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
