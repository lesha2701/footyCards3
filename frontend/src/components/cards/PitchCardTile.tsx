import CardSkillBadge from "@/components/cards/CardSkillBadge";
import PathCardMark from "@/components/path/PathCardMark";
import { staticUrl } from "@/lib/api";
import { pathFrameClass } from "@/lib/pathCards";
import { RARITY_GRADIENTS } from "@/lib/rarity";
import type { Rarity } from "@/types";

/** The compact card used on squad pitches (Card Arena, player tournaments,
 * clubs, FUT Draft). Same corner language as PlayerCard so a card reads the
 * same everywhere: frame = rarity (or «Академия»), top-left rating (+ ★ stars),
 * top-right position, bottom-left skill, bottom-right «Академия» mark.
 * Nothing sits on the middle of the image, where the face is. Whatever the
 * pitch shows *about the slot* (chemistry diamonds) goes below, as children. */
export default function PitchCardTile({
  player,
  stars = 0,
  pathStage,
  prestige = 0,
  talentOverride,
  skillCode,
  skillLevel,
  skillInactiveReason = null,
  unavailable = null,
  children,
}: {
  /** Anything card-like: owned cards, club cards, FUT Draft candidates. */
  player: {
    image_path?: string | null;
    rating: number;
    position: string;
    rarity: Rarity;
    path_talent_code?: string | null;
  };
  stars?: number;
  pathStage?: number;
  prestige?: number;
  talentOverride?: string | null;
  skillCode?: string | null;
  skillLevel?: number | null;
  skillInactiveReason?: string | null;
  /** Club squads: suspended / injured — red frame + mark (bottom-right,
   * which club cards never use for «Академия»). */
  unavailable?: "red_card" | "injury" | null;
  children?: React.ReactNode;
}) {
  const isPath = !!player.path_talent_code;
  const frame = unavailable
    ? "from-red-500 to-red-700"
    : isPath
      ? pathFrameClass(pathStage, prestige)
      : RARITY_GRADIENTS[player.rarity];
  const imageUrl = staticUrl(player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp");

  return (
    <>
      <div className={`relative aspect-square w-full rounded-lg bg-gradient-to-b ${frame} p-[2px]`}>
        <div className="relative h-full w-full overflow-hidden rounded-[6px] bg-black/40">
          <img src={imageUrl} alt="" className="h-full w-full object-cover" loading="lazy" decoding="async" draggable={false} />
          <span className="absolute left-0.5 top-0.5 rounded bg-black/75 px-1 py-px text-center font-display text-micro font-bold leading-none text-white">
            {player.rating}
            {stars > 0 && (
              <span className="block text-micro leading-none text-amber-300" aria-label={`Звёзд: ${stars}`}>
                {"★".repeat(stars)}
              </span>
            )}
          </span>
          <span className="absolute right-0.5 top-0.5 rounded bg-black/75 px-1 py-px font-mono text-micro font-bold leading-none text-accent-cyan">
            {player.position}
          </span>
          {skillCode && skillLevel ? (
            <span className="absolute bottom-0.5 left-0.5">
              <CardSkillBadge code={skillCode} level={skillLevel} inactiveReason={skillInactiveReason} className="!px-1" />
            </span>
          ) : null}
          {unavailable && !isPath && (
            <span
              className="absolute bottom-0.5 right-0.5 flex h-4 w-4 items-center justify-center rounded-sm bg-red-600 text-micro font-black leading-none text-white"
              aria-label={unavailable === "red_card" ? "Дисквалификация" : "Травма"}
            >
              {unavailable === "red_card" ? "▮" : "+"}
            </span>
          )}
          {isPath && (
            <span className="absolute bottom-0.5 right-0.5">
              <PathCardMark talentCode={talentOverride || player.path_talent_code!} stage={pathStage} size="sm" />
            </span>
          )}
        </div>
      </div>
      {children}
    </>
  );
}
