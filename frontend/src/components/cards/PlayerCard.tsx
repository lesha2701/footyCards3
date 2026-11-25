import { memo, useRef } from "react";

import { useCardSkin } from "@/lib/cardSkin";
import { IconLock } from "@/components/icons";
import PathCardMark from "@/components/path/PathCardMark";
import { staticUrl } from "@/lib/api";
import { cardSkinClass } from "@/lib/cosmetics";
import { useFanColor } from "@/lib/fanBattle";
import { cardHalloweenSkin, halloweenArt, useZombiePlayerId } from "@/lib/halloween";
import { pathFrameClass } from "@/lib/pathCards";
import { prestigeMarks, prestigeStyle } from "@/lib/prestige";
import { RARITY_GLOW_STATIC, RARITY_GRADIENTS, RARITY_LABELS } from "@/lib/rarity";
import { specialSerial } from "@/lib/serials";
import { asFinish, FINISH_LABELS, signatureName } from "@/lib/finish";
import goldFrame from "@/assets/cards/gold-frame.webp";
import type { Player } from "@/types";

interface Props {
  player: Player;
  size?: "sm" | "md" | "lg";
  badge?: React.ReactNode;
  footer?: React.ReactNode;
  onClick?: () => void;
  selected?: boolean;
  dimmed?: boolean;
  /** «Звёзды» of this specific copy (its rating already includes them). */
  stars?: number;
  /** «Академия»: stage of this specific copy (omit for a design). */
  pathStage?: number;
  /** «Академия» prestige tier of this copy (◆ marks; it also tints the frame). */
  prestige?: number;
  /** Talent picked in a prestige reforge (overrides the design's). */
  talentOverride?: string | null;
  /** The card is the focus (pack reveal, detail): adds the GPU shine. */
  animated?: boolean;
  /** This copy plays in a squad: the photo is shaded under a lock. */
  inSquad?: boolean;
  /** The owner's «замок» on this copy: a lock mark at the top centre. */
  userLocked?: boolean;
  /** «Основная копия»: a crown instead of the lock mark (it is locked too). */
  mainCopy?: boolean;
  /** Press and hold (~0.45 s): quick actions without opening the card. */
  onLongPress?: () => void;
  /** This copy's number: a numbered edition shows «№37/100». */
  serial?: number | null;
  /** «Редкая версия» of this copy: gold frame / autograph / night edition. */
  finish?: string | null;
}

const LONG_PRESS_MS = 450;

// One corner = one meaning: top-left rating + status (★ stars / ◆ prestige),
// top-right position, bottom-left skill (badge slot), bottom-right «Академия»;
// the owner's lock sits top-centre, a squad copy is shaded under a lock.
// The footer keeps only the name (+ club and attack/defence from md up):
// rarity and «Академия» are already said by the frame, so no repeated text.
const RATING_TEXT = { sm: "text-[12px]", md: "text-sm", lg: "text-base" } as const;
const NAME_TEXT = { sm: "text-caption", md: "text-xs", lg: "text-sm" } as const;

function PlayerCard({
  player, size = "md", badge, footer, onClick, selected, dimmed, stars = 0, pathStage, prestige = 0, talentOverride,
  animated = false, inSquad = false, userLocked = false, mainCopy = false, onLongPress, serial, finish: finishRaw,
}: Props) {
  const finish = asFinish(finishRaw);
  // Long press: a timer started on pointer down; moving the finger (scroll)
  // or lifting it early cancels it, and the click that follows a fired long
  // press is swallowed so the card doesn't also open.
  const pressTimer = useRef<number | null>(null);
  const pressStart = useRef<{ x: number; y: number } | null>(null);
  const longPressed = useRef(false);
  const cancelPress = () => {
    if (pressTimer.current !== null) window.clearTimeout(pressTimer.current);
    pressTimer.current = null;
  };
  const pressHandlers = onLongPress
    ? {
        onPointerDown: (e: React.PointerEvent) => {
          longPressed.current = false;
          pressStart.current = { x: e.clientX, y: e.clientY };
          cancelPress();
          pressTimer.current = window.setTimeout(() => {
            longPressed.current = true;
            pressTimer.current = null;
            onLongPress();
          }, LONG_PRESS_MS);
        },
        onPointerMove: (e: React.PointerEvent) => {
          const s = pressStart.current;
          if (s && Math.hypot(e.clientX - s.x, e.clientY - s.y) > 10) cancelPress();
        },
        onPointerUp: cancelPress,
        onPointerLeave: cancelPress,
        onPointerCancel: cancelPress,
        onContextMenu: (e: React.MouseEvent) => e.preventDefault(),
      }
    : {};
  const handleClick = () => {
    if (longPressed.current) {
      longPressed.current = false;
      return;
    }
    onClick?.();
  };
  const isPath = !!player.path_talent_code;
  // Equipped card skin (cosmetic, own cards only): an extra outline.
  const skin = cardSkinClass(useCardSkin());
  const frame = isPath
    ? pathFrameClass(pathStage, prestige, animated || selected)
    : `${RARITY_GRADIENTS[player.rarity]} ${RARITY_GLOW_STATIC[player.rarity]}${
        (animated || selected) && (player.rarity === "diamond" || player.rarity === "legendary") ? " card-shine" : ""
      }`;
  // «Ночь живых Легенд» (collection frame) or the door trick's zombie frame.
  const zombiePlayerId = useZombiePlayerId();
  const hwSkin = isPath ? null : cardHalloweenSkin(player, zombiePlayerId);
  const hwFrameArt = hwSkin ? halloweenArt(`frame-${hwSkin}`) : undefined;
  // «Капитаны» of «Битва фанатов»: the frame wears the viewer's side colour.
  const fanColor = useFanColor();
  const fanSkin = !isPath && !hwSkin && player.collection_skin === "fans";
  // «Клуб Центурионов» of «💯 Нам 100 дней!»: the gold anniversary frame.
  const goldSkin = !isPath && !hwSkin && player.collection_skin === "gold100";
  // «Редкий номер» (№1, last of an edition, famous shirt numbers) and a
  // starred-up copy both show on the card itself, not only in its sheet.
  const special = specialSerial(serial, player.edition_size);
  const starGlow = stars >= 5
    ? " ring-2 ring-amber-300/80 shadow-[0_0_18px_rgba(252,211,77,0.55)]"
    : stars >= 3 ? " ring-1 ring-amber-300/50 shadow-[0_0_10px_rgba(252,211,77,0.3)]" : "";
  // «Золотая версия» sits in the engraved gold frame (art) instead of the
  // rarity gradient; «Ночная» gets a midnight frame.
  const gold = finish === "gold" && !isPath;
  const night = finish === "night" && !isPath;
  // Full-art: a legendary or diamond footballer's photo runs under the whole
  // card and the name lies on it, no separate strip (not over event frames).
  const fullArt = (player.rarity === "legendary" || player.rarity === "diamond") && !isPath && !hwSkin && !fanSkin;
  const imageUrl = staticUrl(player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp");

  const photo = (
    <>
      <img
        src={imageUrl}
        alt=""
        className="h-full w-full object-cover"
        loading="lazy"
        decoding="async"
        draggable={false}
        style={night ? { filter: "saturate(0.55) brightness(0.8) contrast(1.15) hue-rotate(-12deg)" } : undefined}
      />
      {night && (
        <div aria-hidden className="pointer-events-none absolute inset-0 bg-gradient-to-b from-indigo-950/60 via-indigo-900/10 to-violet-950/50">
          <span className="absolute left-[18%] top-[22%] text-[8px] text-white/80">✦</span>
          <span className="absolute right-[22%] top-[34%] text-[6px] text-white/70">✦</span>
          <span className="absolute left-[40%] top-[12%] text-[5px] text-white/60">✦</span>
          <span className="absolute right-[12%] top-[14%] text-[10px] text-amber-100/80">☾</span>
        </div>
      )}
    </>
  );

  return (
    <button
      type="button"
      onClick={handleClick}
      {...pressHandlers}
      disabled={!onClick}
      aria-label={`${player.display_name}, ${player.position}, рейтинг ${player.rating}, ${RARITY_LABELS[player.rarity]}${
        isPath ? ", Академия" : ""
      }${inSquad ? ", в составе" : ""}${mainCopy ? ", основная копия" : userLocked ? ", под замком" : ""}`}
      className={`group relative flex select-none [-webkit-touch-callout:none] aspect-[3/4] w-full flex-col overflow-hidden rounded-2xl ${
        gold ? "shadow-[0_0_14px_rgba(234,179,8,0.45)]" : night ? "bg-gradient-to-b from-indigo-300 via-violet-700 to-slate-950 shadow-[0_0_14px_rgba(129,140,248,0.45)]" : `bg-gradient-to-b ${frame}`
      } ${
        gold ? "" : isPath ? "p-[3px]" : "p-[2px]"
      }${!selected ? starGlow : ""}${hwSkin ? ` hw-frame-${hwSkin}` : ""}${fanSkin ? " fans-frame" : ""}${goldSkin ? " gold100-frame" : ""} transition-transform active:scale-[0.97] ${
        selected ? (player.rarity === "diamond" ? "ring-4 ring-rarity-diamond" : "ring-4 ring-accent-lime") : ""
      } ${dimmed ? "opacity-40 grayscale" : ""} ${onClick ? "cursor-pointer" : "cursor-default"}${
        skin && !selected ? ` ${skin}` : ""
      }`}
      style={
        gold
          ? { backgroundImage: `url(${goldFrame})`, backgroundSize: "100% 100%", padding: "7.5% 8.5%" }
          : fanSkin && fanColor ? ({ "--fan": fanColor } as React.CSSProperties) : undefined
      }
      data-finish={finish ?? undefined}
    >
      <div className={`relative flex h-full w-full flex-col overflow-hidden bg-bg-surface ${gold ? "rounded-[8px]" : "rounded-[14px]"}`}>
        {fullArt && (
          <div className="absolute inset-0">
            {photo}
            {/* a foil sheen across the full-art photo */}
            <div aria-hidden className="pointer-events-none absolute inset-0 bg-[linear-gradient(115deg,transparent_30%,rgba(255,255,255,0.14)_45%,transparent_58%)]" />
          </div>
        )}
        <div className={`relative flex-1 overflow-hidden ${fullArt ? "" : "bg-black/20"}`}>
          {!fullArt && photo}
          {finish === "autograph" && (
            <span
              aria-label={FINISH_LABELS.autograph}
              className="pointer-events-none absolute bottom-[6%] right-[6%] max-w-[90%] -rotate-[10deg] truncate text-right leading-none text-white"
              style={{
                fontFamily: '"Segoe Script", "Brush Script MT", "Snell Roundhand", "Dancing Script", cursive',
                fontSize: size === "sm" ? 15 : size === "md" ? 20 : 26,
                textShadow: "0 1px 2px rgba(0,0,0,0.9), 0 0 6px rgba(0,0,0,0.6)",
              }}
            >
              {signatureName(player.display_name)}
            </span>
          )}
          <div className="absolute left-1 top-1 rounded-md bg-black/70 px-1.5 py-0.5 text-center font-display font-bold leading-none text-white">
            <span className={RATING_TEXT[size]}>{player.rating}</span>
            {prestige > 0 && (
              <span className={`mt-0.5 block text-micro leading-none ${prestigeStyle(prestige).mark}`} aria-label={`Престиж: ${prestige}`}>
                {prestigeMarks(prestige)}
              </span>
            )}
            {stars > 0 && (
              <span className="mt-0.5 block text-micro leading-none text-amber-300" aria-label={`Звёзд: ${stars}`}>
                {"★".repeat(stars)}
              </span>
            )}
          </div>
          <div className="absolute right-1 top-1 rounded-md bg-black/70 px-1.5 py-0.5 font-display font-semibold leading-none text-white">
            <span className={size === "sm" ? "text-micro" : "text-caption"}>{player.position}</span>
          </div>
          {inSquad && (
            <div className="absolute inset-0 flex items-center justify-center bg-black/50" aria-hidden>
              <span className="flex items-center gap-1 rounded-full bg-black/75 px-2 py-0.5 text-micro font-bold text-ink-chalk">
                <IconLock size={11} /> {size === "sm" ? "Состав" : "В составе"}
              </span>
            </div>
          )}
          {mainCopy ? (
            <div className="absolute left-1/2 top-1 -translate-x-1/2 rounded-md bg-amber-400 px-1 text-[10px] leading-4" aria-hidden>
              👑
            </div>
          ) : userLocked && (
            <div className="absolute left-1/2 top-1 -translate-x-1/2 rounded-md bg-amber-400 p-0.5 text-bg-base" aria-hidden>
              <IconLock size={size === "sm" ? 10 : 12} />
            </div>
          )}
          {badge && <div className="absolute bottom-1 left-1">{badge}</div>}
          {hwSkin && (
            <span className="absolute bottom-1 right-1 rounded-md bg-black/70 px-1 text-caption leading-tight" aria-label={hwSkin === "zombie" ? "Зомби-рамка" : "Вампир-рамка"}>
              {hwSkin === "zombie" ? "🧟" : "🧛"}
            </span>
          )}
          {fanSkin && (
            <span className="absolute bottom-1 right-1 rounded-md bg-black/70 px-1 text-caption leading-tight" aria-label="Капитан">
              👑
            </span>
          )}
          {player.chemistry_shield && !hwSkin && !fanSkin && !isPath && (
            <span
              className="absolute bottom-1 right-1 rounded-md bg-black/70 px-1 text-caption leading-tight"
              aria-label="Без отрицательной химии"
              title="Без отрицательной химии"
            >
              🛡️
            </span>
          )}
          {isPath && (
            <div className="absolute bottom-1 right-1">
              <PathCardMark talentCode={talentOverride || player.path_talent_code!} stage={pathStage} size={size} />
            </div>
          )}
        </div>
        <div
          className={`relative px-1.5 py-1 text-center ${
            fullArt ? "bg-gradient-to-t from-black/90 via-black/65 to-transparent pt-3" : "border-t border-white/10 bg-black/30"
          }`}
        >
          <p className={`truncate font-display font-semibold leading-tight text-ink-chalk ${NAME_TEXT[size]}`}>{player.display_name}</p>
          {player.edition_size != null ? (
            <p className="truncate font-mono text-micro font-bold leading-tight text-amber-300">
              {special && "✦ "}{serial != null ? `№${serial}/${player.edition_size}` : `Тираж ${player.edition_size}`}
            </p>
          ) : special && serial != null ? (
            <p className="truncate font-mono text-micro font-bold leading-tight text-amber-300" title={special}>
              ✦ №{serial}
            </p>
          ) : null}
          {size !== "sm" && (
            <p className="mt-0.5 truncate text-micro leading-tight text-ink-mist">
              {player.club} · <span className="font-mono text-accent-cyan">{player.attack_rating}/{player.defense_rating}</span>
            </p>
          )}
        </div>
        {footer}
      </div>
      {hwFrameArt && (
        <img src={hwFrameArt} alt="" aria-hidden draggable={false} className="pointer-events-none absolute inset-0 h-full w-full object-fill" />
      )}
    </button>
  );
}

export default memo(PlayerCard);
