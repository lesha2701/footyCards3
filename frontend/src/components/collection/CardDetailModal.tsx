import { IconCoin, IconLock, IconTag, IconUpgrade } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { POSITION_LABELS, RARITY_LABELS } from "@/lib/rarity";
import type { UserCard } from "@/types";

export default function CardDetailModal({
  card,
  onClose,
  onSell,
  onToggleHidden,
  hiddenPending,
  onUpgrade,
}: {
  card: UserCard;
  onClose: () => void;
  onSell: () => void;
  onToggleHidden: (hidden: boolean) => void;
  hiddenPending: boolean;
  onUpgrade?: () => void;
}) {
  const player = card.player;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6 backdrop-blur-sm" onClick={onClose}>
      <div className="w-full max-w-xs rounded-3xl border border-white/10 bg-bg-surface p-5" onClick={(e) => e.stopPropagation()}>
        <img
          src={staticUrl(player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
          alt={player.display_name}
          className="aspect-square w-full rounded-2xl object-cover"
        />
        <p className="mt-3 font-display text-lg font-bold text-ink-chalk">{player.display_name}</p>
        <p className="text-sm text-ink-mist">{POSITION_LABELS[player.position]} · {player.club}</p>
        {player.collection_name && (
          <p className="mt-1 flex items-center gap-1 text-xs font-semibold text-accent-lime">
            <IconTag size={12} />
            Коллекция: {player.collection_name}
          </p>
        )}
        <div className="mt-2 grid grid-cols-2 gap-2 text-sm">
          <span className="text-ink-mist">Рейтинг: <b className="font-mono text-accent-cyan">{player.rating}</b></span>
          <span className="text-ink-mist">№ {card.serial_number}</span>
          <span className="text-ink-mist">Атака: <b className="font-mono text-accent-cyan">{player.attack_rating}</b></span>
          <span className="text-ink-mist">Защита: <b className="font-mono text-accent-cyan">{player.defense_rating}</b></span>
          <span className="text-ink-mist">Редкость: <b className="text-ink-chalk">{RARITY_LABELS[player.rarity]}</b></span>
          <span className="text-ink-mist">Страна: <b className="text-ink-chalk">{player.country}</b></span>
        </div>
        {(card.is_locked_by_admin || card.is_locked_in_trade || card.is_in_lineup) && (
          <p className="mt-2 flex items-center gap-1.5 text-xs text-ink-mist">
            <IconLock size={13} />
            Заблокирована {card.is_in_lineup ? "(в составе)" : card.is_locked_in_trade ? "(в обмене)" : "(администратором)"}
          </p>
        )}
        <label className="mt-3 flex items-center justify-between gap-3 rounded-xl bg-black/20 px-3 py-2">
          <span className="text-xs text-ink-mist">Скрыть от предложений обмена</span>
          <input
            type="checkbox"
            checked={card.hidden_from_trade}
            disabled={hiddenPending}
            onChange={(e) => onToggleHidden(e.target.checked)}
            className="h-5 w-5 shrink-0 accent-accent-lime"
          />
        </label>
        {onUpgrade && (
          <button
            onClick={onUpgrade}
            disabled={card.is_locked_by_admin || card.is_locked_in_trade || card.is_in_lineup}
            className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-2xl bg-bg-raised py-2.5 text-sm font-semibold text-accent-lime disabled:opacity-40"
          >
            <IconUpgrade size={15} />
            Апгрейд редкости
          </button>
        )}
        <div className="mt-2 flex gap-2">
          <button onClick={onClose} className="flex-1 rounded-2xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist">Закрыть</button>
          <button
            onClick={onSell}
            disabled={card.is_locked_by_admin || card.is_locked_in_trade || card.is_in_lineup}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-red-500 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
          >
            Продать за
            <IconCoin size={13} />
            {player.quick_sell_price}
          </button>
        </div>
      </div>
    </div>
  );
}
