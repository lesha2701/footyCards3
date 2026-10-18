import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { setCardsLocked } from "@/api/collection";
import { fetchActiveLineup, setActiveLineup } from "@/api/lineups";
import { IconCoin, IconLock, IconLockOpen, IconPlay, IconUpgrade } from "@/components/icons";
import { squadLabel } from "@/lib/cardLocks";
import { formatGameError } from "@/lib/errors";
import { planArenaPlacement } from "@/lib/lineupPlacement";
import { haptic } from "@/lib/telegram";
import type { UserCard } from "@/types";

/** Quick actions on a long-pressed card — lock, put in the Card Arena
 * lineup, sell, open — without going through the full card sheet. */
export default function CardQuickActions({
  card, onClose, onOpen, onSell,
}: {
  card: UserCard;
  onClose: () => void;
  onOpen: () => void;
  onSell: () => void;
}) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const frozen = card.is_locked_by_admin || card.is_locked_in_trade;
  const squad = squadLabel(card);
  const locked = !!card.is_user_locked;
  const refresh = () => {
    for (const key of [["collection"], ["album-detail"], ["upgrade-cards"], ["lineup"], ["lineup-templates"]]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };
  const done = () => { haptic("light"); refresh(); onClose(); };

  const lock = useMutation({
    mutationFn: () => setCardsLocked([card.id], !locked),
    onSuccess: done,
    onError: (err) => setError(formatGameError(err, "Не удалось поставить замок")),
  });
  const arena = useMutation({
    mutationFn: async () => {
      const plan = planArenaPlacement(await fetchActiveLineup(), card);
      if (!plan.ok) throw new Error(plan.reason);
      await setActiveLineup(plan.slots);
    },
    onSuccess: done,
    onError: (err) => setError(formatGameError(err, "Не удалось поставить в состав")),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        className="w-full max-w-md rounded-t-3xl bg-bg-surface px-4 pb-[calc(1rem+env(safe-area-inset-bottom))] pt-3"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={`Действия: ${card.player.display_name}`}
      >
        <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-white/15" aria-hidden />
        <p className="font-display text-base font-bold text-ink-chalk">{card.player.display_name}</p>
        <p className="mb-3 text-xs text-ink-mist">
          {card.player.rating} · {card.player.position}{squad ? ` · ${squad}` : ""}{locked ? " · под замком" : ""}
        </p>
        <div className="grid grid-cols-2 gap-2">
          <Action icon={locked ? <IconLockOpen size={16} /> : <IconLock size={16} />} disabled={lock.isPending} onClick={() => lock.mutate()}>
            {locked ? "Снять замок" : "Замок"}
          </Action>
          {!card.is_in_lineup && !frozen ? (
            <Action icon={<IconPlay size={16} />} disabled={arena.isPending} onClick={() => arena.mutate()}>
              В состав Arena
            </Action>
          ) : (
            <Action icon={<IconPlay size={16} />} disabled>
              Уже в составе
            </Action>
          )}
          <Action icon={<IconUpgrade size={16} />} onClick={() => { onClose(); onOpen(); }}>
            Прокачать
          </Action>
          <Action
            icon={<IconCoin size={16} />}
            danger
            disabled={frozen || !!squad || locked}
            onClick={() => { onClose(); onSell(); }}
          >
            Продать
          </Action>
        </div>
        {error && <p className="mt-2 text-xs text-red-400" role="alert">{error}</p>}
      </div>
    </div>
  );
}

function Action({
  icon, children, onClick, disabled, danger,
}: {
  icon: React.ReactNode;
  children: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`flex min-h-[52px] items-center justify-center gap-2 rounded-2xl text-sm font-semibold active:scale-95 disabled:opacity-35 ${
        danger ? "bg-red-500/15 text-red-300" : "bg-bg-raised text-ink-chalk"
      }`}
    >
      {icon}
      {children}
    </button>
  );
}
