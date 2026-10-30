import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  claimMyPlayerSponsor,
  fetchMyPlayerSponsor,
  signMyPlayerSponsor,
  type MyPlayerSponsorBrand,
  type MyPlayerSponsorGoal,
  type MyPlayerSponsorView,
} from "@/api/myPlayer";
import { IconCoin } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { formatGameError } from "@/lib/errors";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

function daysLeft(iso: string): string {
  const hours = Math.max(0, Math.round((new Date(iso).getTime() - Date.now()) / 3_600_000));
  return hours >= 24 ? `${Math.floor(hours / 24)} дн. ${hours % 24} ч` : `${hours} ч`;
}

/** «Спонсор»: one brand a week. Its goals over the whole mode (trainings,
 * duels, the career, rewarded games) pay coins one by one plus a bonus for
 * all; the premium contract (Stars) adds a goal and multiplies the coins —
 * also for what was already paid. */
export default function MyPlayerSponsor() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data, isLoading } = useQuery({ queryKey: ["my-player", "sponsor"], queryFn: fetchMyPlayerSponsor });
  const [error, setError] = useState<string | null>(null);
  const [paying, setPaying] = useState(false);
  const onView = (view: MyPlayerSponsorView) => {
    setError(null);
    queryClient.setQueryData(["my-player", "sponsor"], view);
    if (view.balance != null) updateBalance(view.balance);
    void queryClient.invalidateQueries({ queryKey: ["my-player"], exact: true });
  };
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));
  const sign = useMutation({ mutationFn: signMyPlayerSponsor, onSuccess: (v) => { hapticNotify("success"); onView(v); }, onError });
  const claim = useMutation({ mutationFn: claimMyPlayerSponsor, onSuccess: (v) => { hapticNotify("success"); onView(v); }, onError });
  const premium = async () => {
    setPaying(true);
    try {
      if ((await payMyPlayerWithStars({ purchase: "sponsor" })) === "paid") {
        hapticNotify("success");
        await queryClient.invalidateQueries({ queryKey: ["my-player"] });
      }
    } catch (err) {
      onError(err);
    } finally {
      setPaying(false);
    }
  };

  if (isLoading || !data) return <ListSkeleton />;
  const contract = data.contract;
  return (
    <div className="flex flex-col gap-3" data-testid="sponsor">
      {!contract ? (
        <>
          <section className="rounded-2xl bg-gradient-to-br from-amber-400/20 to-bg-surface p-4">
            <p className="font-display text-base font-bold text-ink-chalk">Спонсор недели</p>
            <p className="mt-1 text-caption text-ink-mist">
              Выбери бренд: его логотип будет на форме твоего игрока, а за цели недели он платит монеты.
              Три цели бесплатно, четвёртая и ×{data.premium_pct / 100} монет — с премиум-контрактом. Контракт до понедельника.
            </p>
          </section>
          {data.offers.map((brand) => (
            <BrandCard key={brand.code} brand={brand}>
              <button disabled={sign.isPending} onClick={() => sign.mutate(brand.code)}
                className="mt-3 w-full rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-50">
                Подписать контракт
              </button>
            </BrandCard>
          ))}
        </>
      ) : (
        <>
          <BrandCard brand={contract} premium={contract.premium} ends={daysLeft(data.ends_at)}>
            <div className="mt-3 flex flex-col gap-2">
              {contract.goals.map((goal) => (
                <GoalRow key={goal.code} goal={goal} busy={claim.isPending} onClaim={() => claim.mutate(goal.code)} />
              ))}
            </div>
            <div className="mt-3 flex items-center justify-between rounded-xl bg-bg-raised p-3">
              <span className="text-xs text-ink-chalk">Бонус за все цели</span>
              {contract.bonus.claimed ? (
                <span className="text-xs font-bold text-accent-lime">получен</span>
              ) : (
                <button disabled={!contract.bonus.ready || claim.isPending} onClick={() => claim.mutate("bonus")}
                  className="flex items-center gap-1 rounded-lg bg-floodlight px-3 py-1.5 text-xs font-bold text-bg-base disabled:opacity-40">
                  <IconCoin size={12} /> {contract.bonus.coins}
                </button>
              )}
            </div>
          </BrandCard>
          {!contract.premium && data.stars > 0 && (
            <section className="rounded-2xl bg-gradient-to-br from-amber-400/25 to-bg-surface p-4 ring-1 ring-amber-400/40">
              <p className="font-display text-sm font-bold text-ink-chalk">⭐ Премиум-контракт</p>
              <p className="mt-1 text-caption text-ink-mist">
                Четвёртая цель и ×{data.premium_pct / 100} монет за каждую цель и бонус. За уже полученное доплатим сразу.
              </p>
              <button disabled={paying} onClick={() => void premium()}
                className="mt-3 w-full rounded-xl bg-amber-400 py-2.5 text-sm font-bold text-bg-base disabled:opacity-50">
                Улучшить за {data.stars} ⭐
              </button>
            </section>
          )}
        </>
      )}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
    </div>
  );
}

function BrandCard({ brand, premium, ends, children }: {
  brand: MyPlayerSponsorBrand; premium?: boolean; ends?: string; children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl bg-bg-surface p-4" style={{ boxShadow: `inset 4px 0 0 ${brand.color}` }}>
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 items-center justify-center rounded-xl text-2xl" style={{ background: `${brand.color}33` }}>{brand.emoji}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-display text-base font-bold text-ink-chalk">
            {brand.name}
            {premium && <span className="ml-1.5 rounded bg-amber-400 px-1.5 py-0.5 align-middle text-micro font-black text-bg-base">PREMIUM</span>}
          </span>
          {ends && <span className="block text-micro text-ink-mist">Контракт ещё {ends}</span>}
        </span>
      </div>
      {!ends && (
        <ul className="mt-2 flex flex-col gap-1 text-caption text-ink-mist">
          {brand.goals.map((g) => (
            <li key={g.code} className={g.premium_only ? "text-amber-300/80" : ""}>
              {g.premium_only ? "⭐ " : "• "}{g.label}: {g.target} — {g.coins} монет
            </li>
          ))}
        </ul>
      )}
      {children}
    </section>
  );
}

function GoalRow({ goal, busy, onClaim }: { goal: MyPlayerSponsorGoal; busy: boolean; onClaim: () => void }) {
  const value = goal.value ?? 0;
  const pct = Math.min(100, Math.round((value / goal.target) * 100));
  return (
    <div className={`rounded-xl bg-bg-raised p-3 ${goal.locked ? "opacity-50" : ""}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="min-w-0 flex-1 truncate text-xs font-semibold text-ink-chalk">
          {goal.locked && "⭐ "}{goal.label} <span className="font-normal text-ink-mist">{value}/{goal.target}</span>
        </span>
        {goal.claimed ? (
          <span className="text-xs font-bold text-accent-lime">✓ {goal.coins}</span>
        ) : goal.locked ? (
          <span className="text-micro text-amber-300">премиум</span>
        ) : (
          <button disabled={!goal.done || busy} onClick={onClaim}
            className="flex items-center gap-1 rounded-lg bg-floodlight px-2.5 py-1 text-micro font-bold text-bg-base disabled:opacity-40">
            <IconCoin size={11} /> {goal.coins}
          </button>
        )}
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-bg-surface">
        <div className="h-full rounded-full bg-gradient-to-r from-accent-cyan to-accent-lime" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
