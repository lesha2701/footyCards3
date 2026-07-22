import { staticUrl } from "@/lib/api";
import { RARITY_GLOW, RARITY_GRADIENTS, RARITY_LABELS } from "@/lib/rarity";
import type { Player } from "@/types";

interface Props {
  player: Player;
  size?: "sm" | "md" | "lg";
  badge?: React.ReactNode;
  footer?: React.ReactNode;
  onClick?: () => void;
  selected?: boolean;
  dimmed?: boolean;
}

const SIZE_CLASSES: Record<NonNullable<Props["size"]>, string> = {
  sm: "text-[10px]",
  md: "text-xs",
  lg: "text-sm",
};

export default function PlayerCard({ player, size = "md", badge, footer, onClick, selected, dimmed }: Props) {
  const imageUrl = staticUrl(player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp");

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className={`group relative flex aspect-[3/4] w-full flex-col overflow-hidden rounded-2xl bg-gradient-to-b ${
        RARITY_GRADIENTS[player.rarity]
      } ${RARITY_GLOW[player.rarity]} p-[2px] transition-transform active:scale-[0.97] ${
        selected ? "ring-4 ring-accent" : ""
      } ${dimmed ? "opacity-40 grayscale" : ""} ${onClick ? "cursor-pointer" : "cursor-default"}`}
    >
      <div className="flex h-full w-full flex-col overflow-hidden rounded-[14px] bg-bg-surface/90">
        <div className="relative flex-1 overflow-hidden">
          <img src={imageUrl} alt={player.display_name} className="h-full w-full object-cover" loading="lazy" />
          <div className="absolute left-1.5 top-1.5 rounded-md bg-black/60 px-1.5 py-0.5 font-display font-bold leading-none text-white">
            <span className={SIZE_CLASSES[size]}>{player.rating}</span>
          </div>
          <div className="absolute right-1.5 top-1.5 rounded-md bg-black/60 px-1.5 py-0.5 font-display font-semibold leading-none text-white">
            <span className={SIZE_CLASSES[size]}>{player.position}</span>
          </div>
          {badge && <div className="absolute bottom-1.5 left-1.5">{badge}</div>}
        </div>
        <div className="border-t border-white/10 bg-black/30 px-2 py-1.5 text-center">
          <p className={`truncate font-display font-semibold text-slate-100 ${SIZE_CLASSES[size]}`}>{player.display_name}</p>
          <p className="truncate text-[9px] text-slate-400">{player.club} · {RARITY_LABELS[player.rarity]}</p>
        </div>
        {footer}
      </div>
    </button>
  );
}
