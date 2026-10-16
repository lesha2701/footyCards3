import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { raisePrestige, reforgeTalent } from "@/api/path";
import { IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { prestigeMarks, prestigeStyle } from "@/lib/prestige";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { PathPrestige, PathState } from "@/types";

/** «Престиж» block of the «Путь» screen: the tier ladder, what the next tier
 * costs (duplicates of this player, or spare copies of other «Академия»
 * players at the server's rate) and gives, and — on the top tier — the
 * one-off talent reforge. Status and soft bonuses only, never rating. */
export default function PrestigeSection({ cardId, prestige, title }: { cardId: number; prestige: PathPrestige; title: string }) {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [error, setError] = useState<string | null>(null);
  const [granted, setGranted] = useState<string | null>(null);
  const [reforgeCode, setReforgeCode] = useState<string>("");

  const onState = (next: PathState) => {
    hapticNotify("success");
    setError(null);
    queryClient.setQueryData(["path", cardId], next);
    for (const key of [["collection"], ["album-overview"], ["album-detail"]]) queryClient.invalidateQueries({ queryKey: key });
  };
  const onFail = (err: unknown) => {
    hapticNotify("error");
    setError(formatGameError(err, "Не получилось"));
  };
  const up = useMutation({
    mutationFn: () => raisePrestige(cardId, { idempotency_key: crypto.randomUUID() }),
    onSuccess: (data) => {
      if (data.new_balance != null) updateBalance(data.new_balance);
      const g = (data.granted ?? {}) as { coins?: number; attempts?: number; skill_tokens?: { quantity: number } };
      const parts = [
        g.coins ? `+${g.coins} монет` : null,
        g.attempts ? `+${g.attempts} попыт.` : null,
        g.skill_tokens ? `+${g.skill_tokens.quantity} жетон(а) навыка` : null,
      ].filter(Boolean);
      setGranted(parts.length ? `Награда: ${parts.join(", ")}` : null);
      onState(data);
    },
    onError: onFail,
  });
  const reforge = useMutation({
    mutationFn: () => reforgeTalent(cardId, reforgeCode, crypto.randomUUID()),
    onSuccess: onState,
    onError: onFail,
  });

  const p = prestige;
  const needUnits = p.next_dupes != null ? p.next_dupes * p.ratio : 0;
  const enough = p.next_dupes != null && p.free_units >= needUnits;
  const reward = p.next_reward;
  return (
    <section className="rounded-2xl border border-white/10 bg-white/5 p-3" aria-label="Престиж">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Престиж</h3>
        {p.tier > 0 && (
          <span className={`rounded-full px-2 py-0.5 text-caption font-bold ${prestigeStyle(p.tier).chip}`}>
            {prestigeMarks(p.tier)} {p.tier_name}
          </span>
        )}
      </div>
      <ol className="mt-2 grid grid-cols-4 gap-1 text-center" aria-label="Ступени престижа">
        {p.names.map((name, i) => {
          const tier = i + 1;
          const reached = p.tier >= tier;
          return (
            <li key={name} className={`rounded-lg py-1.5 text-micro ${reached ? prestigeStyle(tier).chip : "bg-black/20 text-ink-mist-dim"}`}>
              <span className="block text-sm leading-none">{prestigeMarks(tier)}</span>
              {name}
            </li>
          );
        })}
      </ol>
      {p.icon_number != null && (
        <p className="mt-2 text-center font-display text-sm font-bold text-prestige">
          Икона {title === "Академия" ? "Академии" : `«${title}»`} №{p.icon_number}
        </p>
      )}
      <ul className="mt-2 space-y-0.5 text-caption text-ink-mist">
        <li>Опыт: +{p.xp_bonus_pct}%{p.next_xp_bonus_pct != null && p.next_xp_bonus_pct > p.xp_bonus_pct ? ` (дальше +${p.next_xp_bonus_pct}%)` : ""}</li>
        <li>Бесплатных попыток Арены в день: +{p.extra_free_attempts}</li>
        <li className="flex items-center gap-1">Быстрая продажа: <IconCoin size={11} /> {p.sell_price}</li>
      </ul>

      {p.next_dupes != null ? (
        <div className="mt-3 rounded-xl bg-black/20 p-2.5 text-xs">
          <p className="text-ink-chalk">
            Ступень «{p.names[p.tier]}»: {p.next_dupes} дубл. этого игрока или {needUnits} лишних карт других игроков
            «{title}» (1 дубль = {p.ratio})
          </p>
          <p className="mt-1 text-ink-mist">
            Есть: <b className="font-mono text-ink-chalk">{p.free_units}</b> из {needUnits}
            {p.next_coins ? <> · <IconCoin size={11} className="inline" /> {p.next_coins}</> : null}
          </p>
          {reward && (
            <p className="mt-1 text-path">
              Награда: {[reward.coins ? `${reward.coins} монет` : null, reward.attempts ? `${reward.attempts} попыт.` : null,
                reward.skill_tokens ? `${reward.skill_tokens} жетон(а) навыка` : null].filter(Boolean).join(", ") || "—"}
            </p>
          )}
          <button
            type="button"
            disabled={!enough || up.isPending}
            onClick={() => up.mutate()}
            className="mt-2 w-full rounded-xl bg-floodlight py-2 text-xs font-bold text-bg-base disabled:opacity-40"
          >
            Повысить престиж
          </button>
          <p className="mt-1 text-micro text-ink-mist-dim">
            Берутся свободные дубли без своего прогресса; у каждого другого игрока остаётся хотя бы одна копия, копии с
            навыком не берутся.
          </p>
        </div>
      ) : (
        <p className="mt-2 text-center text-xs font-semibold text-legend">Высшая ступень престижа</p>
      )}

      {p.can_reforge && (
        <div className="mt-3 rounded-xl border border-fuchsia-400/30 bg-fuchsia-400/5 p-2.5 text-xs">
          <p className="font-semibold text-ink-chalk">Перековка таланта — один раз</p>
          <p className="text-ink-mist">Новый талант только у этой копии; уровень остаётся по этапу пути.</p>
          <select
            value={reforgeCode}
            onChange={(e) => setReforgeCode(e.target.value)}
            className="mt-2 w-full rounded-lg bg-bg-surface px-2 py-1.5 text-ink-chalk"
            aria-label="Новый талант"
          >
            <option value="">Выбери талант…</option>
            {p.reforge_options.map((o) => (
              <option key={o.code} value={o.code}>{o.emoji} {o.name}</option>
            ))}
          </select>
          <button
            type="button"
            disabled={!reforgeCode || reforge.isPending}
            onClick={() => reforge.mutate()}
            className="mt-2 w-full rounded-xl bg-fuchsia-400 py-2 text-xs font-bold text-black disabled:opacity-40"
          >
            Перековать
          </button>
        </div>
      )}
      {p.reforged && <p className="mt-2 text-caption text-ink-mist">Талант этой копии уже перекован.</p>}
      {granted && <p className="mt-2 rounded-lg bg-emerald-400/10 px-2 py-1 text-xs text-path">{granted}</p>}
      {error && <p className="mt-2 rounded-lg bg-red-500/10 px-2 py-1 text-xs text-red-400">{error}</p>}
    </section>
  );
}
