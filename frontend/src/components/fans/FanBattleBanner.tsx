import type { CSSProperties } from "react";
import { useNavigate } from "react-router-dom";

import FanTug from "@/components/fans/FanTug";
import { IconChevronRight, IconClock } from "@/components/icons";
import { fanArt, fanBattlePhase, sideByCode, useFanBattle } from "@/lib/fanBattle";
import { timeLeft, useMinuteTick } from "@/lib/halloween";

/** «⚔️ Битва фанатов» on the home screen: the live tug-of-war, the time left
 *  and the way into the event — or the teaser before the start, or the
 *  results while rewards wait. */
export default function FanBattleBanner() {
  const navigate = useNavigate();
  const now = useMinuteTick();
  const { data } = useFanBattle();
  const phase = fanBattlePhase(data, now);
  if (!phase || !data) return null;
  const art = fanArt("banner");
  const mine = sideByCode(data.sides, data.my_side);
  const [a, b] = data.sides;

  return (
    <button
      onClick={() => navigate("/fans")}
      className="fans-sky relative flex min-h-[112px] flex-col gap-3 overflow-hidden rounded-3xl p-4 text-left ring-1 ring-white/10 active:scale-[0.98]"
      style={a && b ? ({ "--fan-a": a.color, "--fan-b": b.color } as CSSProperties) : undefined}
    >
      {art && <img src={art} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover opacity-70" />}
      <span className="relative flex items-start justify-between gap-2">
        <span>
          <span className="block font-display text-[17px] font-black uppercase leading-tight tracking-wide text-white drop-shadow">
            ⚔️ Битва фанатов
          </span>
          <span className="mt-0.5 flex items-center gap-1 font-mono text-micro text-white/75">
            <IconClock size={11} />
            {phase === "teaser"
              ? `старт через ${timeLeft(data.starts_at, now)}`
              : phase === "live"
                ? `до конца ${timeLeft(data.ends_at, now)}`
                : "итоги подведены"}
          </span>
        </span>
        <span className="flex items-center gap-1">
          {data.claimable > 0 && (
            <span className="fans-pulse whitespace-nowrap rounded-full bg-accent-lime px-2.5 py-1 text-micro font-bold text-black">🎁 Забрать</span>
          )}
          <IconChevronRight size={18} className="text-white/80" />
        </span>
      </span>
      <span className="relative block">
        {phase === "teaser" || !mine ? (
          <span className="flex items-center gap-2">
            {data.sides.map((side, i) => (
              <span key={side.code} className="contents">
                {i === 1 && <span className="font-display text-sm font-black text-white/70">VS</span>}
                <span
                  className="flex flex-1 items-center justify-center gap-1 rounded-2xl py-2 font-display text-sm font-black uppercase text-white"
                  style={{ background: `${side.color}55`, boxShadow: `inset 0 0 0 1px ${side.color}` }}
                >
                  {side.emoji} {side.name}
                </span>
              </span>
            ))}
          </span>
        ) : (
          <FanTug sides={data.sides} mine={data.my_side} compact />
        )}
        {!mine && data.can_join && (
          <span className="mt-2 block text-center text-micro font-bold text-white">Выбери сторону — за кого болеешь?</span>
        )}
      </span>
    </button>
  );
}
