import { useQuery } from "@tanstack/react-query";

import { fetchAdminBadges, fetchAdminCosmetics, fetchAdminPacks } from "@/admin/api";
import type { RewardBundleInput } from "@/admin/types";
import { RARITY_LABELS } from "@/lib/rarity";
import type { Rarity } from "@/types";

const RARITIES: Rarity[] = ["common", "rare", "epic", "legendary", "diamond"];
const input = "w-full rounded-lg bg-bg-surface px-2 py-1.5 text-sm outline-none";

/** Admin editor for one reward slot: coins + optional pack, random card of
 * a rarity, badge and cosmetic (shared by the calendar and the seasons). */
export default function RewardBundleEditor({
  value, onChange,
}: {
  value: RewardBundleInput;
  onChange: (next: RewardBundleInput) => void;
}) {
  const { data: packs } = useQuery({ queryKey: ["admin-packs"], queryFn: fetchAdminPacks });
  const { data: badges } = useQuery({ queryKey: ["admin-badges"], queryFn: fetchAdminBadges });
  const { data: cosmetics } = useQuery({ queryKey: ["admin-cosmetics"], queryFn: fetchAdminCosmetics });
  const set = (patch: Partial<RewardBundleInput>) => onChange({ ...value, ...patch });
  const num = (v: string) => (v ? Number(v) : null);

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      <label className="flex flex-col gap-0.5">
        <span className="text-micro text-slate-500">Монеты</span>
        <input type="number" min={0} value={value.coins} onChange={(e) => set({ coins: Number(e.target.value) || 0 })} className={input} />
      </label>
      <label className="flex flex-col gap-0.5">
        <span className="text-micro text-slate-500">Пак</span>
        <select value={value.pack_id ?? ""} onChange={(e) => set({ pack_id: num(e.target.value) })} className={input}>
          <option value="">—</option>
          {packs?.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-0.5">
        <span className="text-micro text-slate-500">Карточка</span>
        <select
          value={value.card_rarity ?? ""}
          onChange={(e) => set({ card_rarity: (e.target.value || null) as Rarity | null })}
          className={input}
        >
          <option value="">—</option>
          {RARITIES.map((r) => <option key={r} value={r}>{RARITY_LABELS[r]}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-0.5">
        <span className="text-micro text-slate-500">Значок</span>
        <select value={value.badge_id ?? ""} onChange={(e) => set({ badge_id: num(e.target.value) })} className={input}>
          <option value="">—</option>
          {badges?.map((b) => <option key={b.id} value={b.id}>{b.icon} {b.name}</option>)}
        </select>
      </label>
      <label className="flex flex-col gap-0.5">
        <span className="text-micro text-slate-500">Косметика</span>
        <select value={value.cosmetic_id ?? ""} onChange={(e) => set({ cosmetic_id: num(e.target.value) })} className={input}>
          <option value="">—</option>
          {cosmetics?.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </label>
    </div>
  );
}
