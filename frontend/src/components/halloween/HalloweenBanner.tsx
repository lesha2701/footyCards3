import { useNavigate } from "react-router-dom";

import { IconChevronRight, IconClock } from "@/components/icons";
import { halloweenArt, pumpkinsWord, timeLeft, useHalloween, useMinuteTick } from "@/lib/halloween";

/** Bats and pumpkins drifting over a block (absolute, behind the content). */
export function HalloweenDecor({ dense = false }: { dense?: boolean }) {
  const items = dense
    ? [
        { e: "🦇", c: "left-[6%] top-1 text-lg hw-flap", d: "0s" },
        { e: "🦇", c: "right-[18%] top-3 text-sm hw-flap", d: "1.2s" },
        { e: "🦇", c: "left-[40%] -top-1 text-xs hw-flap", d: "2.1s" },
        { e: "🎃", c: "right-2 bottom-1 text-2xl hw-float", d: "0.6s" },
        { e: "🕸️", c: "left-1 bottom-0 text-xl opacity-60", d: "0s" },
      ]
    : [
        { e: "🦇", c: "right-[22%] top-1 text-sm hw-flap", d: "0.4s" },
        { e: "🦇", c: "right-[8%] top-4 text-xs hw-flap", d: "1.6s" },
      ];
  return (
    <span aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      {items.map((it, i) => (
        <span key={i} className={`absolute select-none ${it.c}`} style={{ animationDelay: it.d }}>
          {it.e}
        </span>
      ))}
    </span>
  );
}

/** «🎃 Ночь тыкв» on the home screen: the pumpkin counter, the time left and
 *  the way into the event. Rendered only while the event runs. */
export default function HalloweenBanner() {
  const navigate = useNavigate();
  const now = useMinuteTick();
  const { data, live } = useHalloween();
  if (!live || !data) return null;
  const art = halloweenArt("banner");
  const doorReady = !data.door_today;

  return (
    <button
      onClick={() => navigate("/halloween")}
      className="hw-sky hw-glow relative flex min-h-[112px] items-stretch overflow-hidden rounded-3xl text-left active:scale-[0.98]"
    >
      {art && <img src={art} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover opacity-90" />}
      <HalloweenDecor dense />
      <span className="relative flex flex-1 flex-col justify-between gap-2 p-4">
        <span>
          <span className="block font-display text-[17px] font-black uppercase leading-tight tracking-wide text-orange-300 drop-shadow">
            🎃 Ночь тыкв
          </span>
          <span className="mt-0.5 flex items-center gap-1 font-mono text-micro text-violet-200">
            <IconClock size={11} /> до конца {timeLeft(data.ends_at, now)}
          </span>
        </span>
        <span className="flex flex-wrap items-center gap-2">
          <span className="rounded-full bg-black/45 px-3 py-1 font-display text-sm font-bold text-orange-200 ring-1 ring-orange-400/50">
            {data.pumpkins.toLocaleString("ru-RU")} {pumpkinsWord(data.pumpkins)}
          </span>
          {doorReady && (
            <span className="hw-flicker rounded-full bg-violet-600/80 px-2.5 py-1 text-micro font-bold text-white">
              🚪 Кошелёк или жизнь?
            </span>
          )}
        </span>
      </span>
      <span className="relative flex items-center pr-3 text-orange-200">
        <IconChevronRight size={18} />
      </span>
    </button>
  );
}
