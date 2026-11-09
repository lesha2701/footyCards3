import { ClubLogo } from "@/components/clubs/ClubLogo";
import type { ClubWarSide } from "@/types";

function Side({ side, logoSize, rating }: { side: ClubWarSide; logoSize: number; rating: boolean }) {
  return (
    <div className="flex min-w-0 flex-1 basis-0 flex-col items-center gap-1">
      <ClubLogo shape={side.logo_shape} color={side.logo_color} emblem={side.emblem} size={logoSize} />
      {/* A long name wraps, even a single long word: it must never push the score off the screen. */}
      <p className="line-clamp-2 w-full text-center text-caption font-semibold leading-tight text-white [overflow-wrap:anywhere]">{side.name}</p>
      {rating && <p className="text-micro text-white/60">рейтинг {side.war_rating}</p>}
    </div>
  );
}

/** Both clubs and the score. The sides share the width left by the score,
 * and the score scales with the screen, so it fits a 320 px phone too. It
 * sits on ClubWarArt, night-dark in both themes, hence the white text. */
export function ClubWarScoreboard({ me, opponent, logoSize = 48, rating = false, caption }: {
  me: ClubWarSide;
  opponent: ClubWarSide;
  logoSize?: number;
  rating?: boolean;
  caption?: string;
}) {
  return (
    <div className="flex w-full min-w-0 items-center gap-1.5">
      <Side side={me} logoSize={logoSize} rating={rating} />
      <div className="flex shrink-0 flex-col items-center">
        <span className="whitespace-nowrap font-display text-[clamp(1.375rem,8vw,2rem)] font-black leading-none text-white [text-shadow:0_2px_12px_rgba(0,0,0,0.7)]">
          {me.score}<span className="mx-0.5 text-white/60">:</span>{opponent.score}
        </span>
        {caption && <span className="mt-1 text-micro uppercase tracking-wider text-white/70">{caption}</span>}
      </div>
      <Side side={opponent} logoSize={logoSize} rating={rating} />
    </div>
  );
}
