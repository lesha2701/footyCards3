import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { setMyPlayerSkill, upgradeMyPlayerSkill, type MyPlayerSkill, type MyPlayerView } from "@/api/myPlayer";
import { IconCoin } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";

interface Props {
  view: MyPlayerView;
  skill: MyPlayerSkill;
  onSaved: (view: MyPlayerView) => void;
}

function Price({ tokens, coins, have }: { tokens: number; coins: number; have: number }) {
  return (
    <span className="flex items-center gap-2 font-mono text-caption">
      {tokens > 0 && <span className={have >= tokens ? "text-ink-chalk" : "text-red-400"}>🎟 {have}/{tokens}</span>}
      {coins > 0 && (
        <span className="flex items-center gap-0.5 text-ink-chalk">
          <IconCoin size={11} /> {coins}
        </span>
      )}
      {tokens === 0 && coins === 0 && <span className="text-accent-lime">бесплатно</span>}
    </span>
  );
}

/** Skill of «Мой игрок»: assign / upgrade / replace for skill tokens + coins —
 * the very same operations and prices as a card skill (admin «Навыки карточек»). */
export default function MyPlayerSkillSection({ view, skill, onSaved }: Props) {
  const [error, setError] = useState<string | null>(null);
  const onSuccess = (next: MyPlayerView) => { setError(null); hapticNotify("success"); onSaved(next); };
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));
  const choose = useMutation({ mutationFn: setMyPlayerSkill, onSuccess, onError });
  const upgrade = useMutation({ mutationFn: upgradeMyPlayerSkill, onSuccess, onError });
  const busy = choose.isPending || upgrade.isPending;
  const balance = view.balance;

  if (!skill.enabled) {
    return (
      <section className="rounded-2xl bg-bg-surface p-4">
        <h2 className="font-display text-base font-bold text-ink-chalk">Навык</h2>
        <p className="mt-1 text-xs text-ink-mist">Навыки временно отключены.</p>
      </section>
    );
  }

  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">Навык</h2>
        {skill.code && (
          <span className="rounded-full bg-accent-lime/15 px-2 py-0.5 text-xs font-bold text-accent-lime">
            {skill.icon} {skill.name} · {skill.level_label}
          </span>
        )}
      </div>
      <p className="mt-1 text-caption text-ink-mist">
        Как у карточек: назначь навык, улучшай до III за жетоны этого навыка и монеты. Действует в матчах «Карьеры
        тренера». Жетоны выпадают из паков и наград турниров.
      </p>

      {skill.code && skill.upgrade && (
        <button
          disabled={busy || (skill.tokens[skill.code] ?? 0) < skill.upgrade.token_cost || balance < skill.upgrade.coin_cost}
          onClick={() => upgrade.mutate()}
          className="mt-3 flex w-full items-center justify-between rounded-xl bg-floodlight px-3 py-2.5 text-left text-bg-base disabled:opacity-40"
        >
          <span className="text-sm font-bold">Улучшить до {["", "I", "II", "III"][skill.upgrade.to_level]}</span>
          <span className="rounded-lg bg-black/20 px-2 py-0.5">
            <Price tokens={skill.upgrade.token_cost} coins={skill.upgrade.coin_cost} have={skill.tokens[skill.code] ?? 0} />
          </span>
        </button>
      )}

      {!skill.options.length ? (
        <p className="mt-3 text-xs text-ink-mist">Для позиции {view.player?.position} подходящих навыков пока нет.</p>
      ) : (
        <div className="mt-3 flex flex-col gap-2">
          {skill.options.map((o) => {
            const active = skill.code === o.code;
            const tokens = skill.code ? skill.replace_token_cost : skill.assign_token_cost;
            const coins = skill.code ? skill.replace_coin_cost : skill.assign_coin_cost;
            const have = skill.tokens[o.code] ?? 0;
            const affordable = have >= tokens && balance >= coins;
            return (
              <div
                key={o.code}
                className={`flex items-start gap-3 rounded-xl p-3 ${active ? "bg-accent-lime/15 ring-2 ring-accent-lime" : "bg-bg-raised"}`}
              >
                <span className="text-2xl leading-none">{o.icon}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-ink-chalk">{o.name}</span>
                  <span className="block text-caption text-ink-mist">{o.effect}</span>
                  {!active && (
                    <span className="mt-1.5 flex items-center justify-between gap-2">
                      <Price tokens={tokens} coins={coins} have={have} />
                      <button
                        disabled={busy || !affordable}
                        onClick={() => choose.mutate(o.code)}
                        className="rounded-lg bg-floodlight px-3 py-1 text-xs font-bold text-bg-base disabled:opacity-40"
                      >
                        {skill.code ? "Заменить" : "Назначить"}
                      </button>
                    </span>
                  )}
                </span>
              </div>
            );
          })}
        </div>
      )}
      {skill.code && (
        <p className="mt-2 text-micro text-ink-mist-dim">Замена начинает новый навык с уровня I.</p>
      )}
      {error && <p className="mt-3 rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
    </section>
  );
}
