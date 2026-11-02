import { useNavigate } from "react-router-dom";

import { IconChevronRight, IconClock } from "@/components/icons";
import { anniversaryArt, anniversaryClaimable, anniversaryPhase, communityPct, useAnniversary } from "@/lib/anniversary";
import { timeLeft, useMinuteTick } from "@/lib/halloween";

/** «💯 Нам 100 дней!» on the home screen: the community goal «Сотня», today's
 *  gift and the way into the party — or the teaser before the start. */
export default function AnniversaryBanner() {
  const navigate = useNavigate();
  const now = useMinuteTick();
  const { data } = useAnniversary();
  const phase = anniversaryPhase(data, now);
  if (!phase || !data) return null;
  const art = anniversaryArt("banner");
  const pct = communityPct(data.community);
  const waiting = anniversaryClaimable(data);

  return (
    <button
      onClick={() => navigate("/anniversary")}
      className="anni-sky relative flex min-h-[112px] flex-col gap-3 overflow-hidden rounded-3xl p-4 text-left ring-1 ring-amber-300/30 active:scale-[0.98]"
    >
      {art && <img src={art} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover opacity-70" />}
      <span className="relative flex items-start justify-between gap-2">
        <span>
          <span className="block font-display text-[17px] font-black uppercase leading-tight tracking-wide text-amber-100 drop-shadow">
            💯 Нам 100 дней!
          </span>
          <span className="mt-0.5 flex items-center gap-1 font-mono text-micro text-white/75">
            <IconClock size={11} />
            {phase === "teaser"
              ? `праздник через ${timeLeft(data.starts_at, now)}`
              : phase === "live"
                ? `до конца ${timeLeft(data.ends_at, now)}`
                : "праздник окончен — награды ждут"}
          </span>
        </span>
        <span className="flex items-center gap-1">
          {waiting > 0 && (
            <span className="fans-pulse whitespace-nowrap rounded-full bg-amber-300 px-2.5 py-1 text-micro font-bold text-black">🎁 Подарок</span>
          )}
          <IconChevronRight size={18} className="text-white/80" />
        </span>
      </span>
      <span className="relative block">
        {phase === "teaser" ? (
          <span className="block text-xs text-white/80">Подарки каждый день, общая цель «Сотня» и твои первые 100 дней в цифрах</span>
        ) : (
          <>
            <span className="flex justify-between font-mono text-micro text-white/75">
              <span>Цель «Сотня»</span>
              <span>{pct}%</span>
            </span>
            <span className="mt-1 block h-2 overflow-hidden rounded-full bg-white/10">
              <span className="block h-full rounded-full bg-gradient-to-r from-amber-200 to-amber-500" style={{ width: `${pct}%` }} />
            </span>
          </>
        )}
      </span>
    </button>
  );
}
