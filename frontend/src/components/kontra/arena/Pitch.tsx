import { memo } from "react";

// [x %, y %, delay s] — flash-bulbs in the stands.
const BULBS: [number, number, number][] = [
  [8, 6, 0.2], [17, 13, 1.7], [29, 4, 0.9], [41, 11, 2.3], [55, 7, 0.5],
  [63, 14, 1.3], [74, 5, 2.0], [86, 10, 0.1], [93, 15, 1.1], [35, 16, 2.6],
];

/** The pitch in perspective: striped grass tilted away from the camera,
 *  white lines, the stands with flash-bulbs behind the far goal and the
 *  floodlights. Pure decoration — fighters stand on an overlay above it. */
function Pitch({ boss = false }: { boss?: boolean }) {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden" aria-hidden>
      {/* night sky + stands */}
      <div className={`absolute inset-0 ${boss ? "bg-[radial-gradient(120%_70%_at_50%_0%,#4c0519_0%,#14070c_55%,#05070a_100%)]" : "bg-[radial-gradient(120%_70%_at_50%_0%,#1e3a5f_0%,#0b1220_55%,#05070a_100%)]"}`} />
      <div className="kontra-crowd absolute inset-x-0 top-0 h-[22%] opacity-70" />
      {BULBS.map(([x, y, d], i) => (
        <span key={i} className="kontra-bulb" style={{ left: `${x}%`, top: `${y}%`, animationDelay: `${d}s` }} />
      ))}
      {/* floodlight beams */}
      <div className="absolute -left-[10%] top-0 h-[60%] w-[45%] origin-top-left rotate-[-18deg] bg-gradient-to-b from-white/10 to-transparent blur-md" />
      <div className="absolute -right-[10%] top-0 h-[60%] w-[45%] origin-top-right rotate-[18deg] bg-gradient-to-b from-white/10 to-transparent blur-md" />

      {/* the grass plane */}
      <div className="absolute inset-x-0 bottom-0 top-[12%] [perspective:620px]">
        <div
          className="absolute left-1/2 top-0 h-[118%] w-[150%] origin-top"
          style={{
            transform: "translateX(-50%) rotateX(38deg)",
            background: boss
              ? "repeating-linear-gradient(180deg,#14532d 0 7%,#166534 7% 14%)"
              : "repeating-linear-gradient(180deg,#15803d 0 7%,#166534 7% 14%)",
          }}
        >
          <div className="absolute inset-[6%_18%_10%_18%] rounded-sm border-2 border-white/45">
            <div className="absolute inset-x-0 top-1/2 h-0.5 -translate-y-1/2 bg-white/45" />
            <div className="absolute left-1/2 top-1/2 aspect-square w-[26%] -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white/45" />
            <div className="absolute left-1/2 top-1/2 h-2 w-2 -translate-x-1/2 -translate-y-1/2 rounded-full bg-white/60" />
            <div className="absolute left-1/2 top-0 h-[15%] w-[46%] -translate-x-1/2 border-2 border-t-0 border-white/45" />
            <div className="absolute left-1/2 top-0 h-[6%] w-[22%] -translate-x-1/2 border-2 border-t-0 border-white/45" />
            <div className="absolute bottom-0 left-1/2 h-[15%] w-[46%] -translate-x-1/2 border-2 border-b-0 border-white/45" />
            <div className="absolute bottom-0 left-1/2 h-[6%] w-[22%] -translate-x-1/2 border-2 border-b-0 border-white/45" />
            {/* far goal */}
            <div className="absolute -top-[3.2%] left-1/2 h-[3.2%] w-[12%] -translate-x-1/2 rounded-t-sm border-2 border-b-0 border-white/70 bg-white/10" />
          </div>
          {/* mowing sheen */}
          <div className="absolute inset-0 bg-[radial-gradient(60%_40%_at_50%_45%,rgba(255,255,255,0.10),transparent)]" />
        </div>
      </div>

      {/* vignette */}
      <div className="absolute inset-0 bg-[radial-gradient(90%_80%_at_50%_55%,transparent_55%,rgba(0,0,0,0.65)_100%)]" />
    </div>
  );
}

export default memo(Pitch);
