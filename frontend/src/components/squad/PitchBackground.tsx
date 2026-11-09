/** Striped grass with pitch markings, drawn behind any squad editor's
 * cards. Render it as the first child of a `relative overflow-hidden`
 * container (the chemistry overlay, if any, goes right after it). `vivid`
 * draws brighter grass with crisp mowing stripes (vector, so it stays sharp). */
export default function PitchBackground({ vivid }: { vivid?: boolean }) {
  return (
    <>
      {vivid && (
        <>
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[#229a4e] via-[#187f41] to-[#0f6133]" />
          <div
            className="pointer-events-none absolute inset-0"
            style={{ backgroundImage: "repeating-linear-gradient(to bottom, rgba(255,255,255,0.075) 0 10%, rgba(0,0,0,0.085) 10% 20%)" }}
          />
          <div className="pointer-events-none absolute inset-0 shadow-[inset_0_0_40px_rgba(0,40,18,0.45)]" />
        </>
      )}
      <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 140" preserveAspectRatio="none" aria-hidden>
        <g fill="none" stroke="#ffffff" strokeOpacity={vivid ? 0.6 : 0.16} strokeWidth={vivid ? 0.55 : 0.45}>
          <rect x="2.5" y="1.5" width="95" height="137" rx="1.5" />
          <line x1="2.5" y1="70" x2="97.5" y2="70" />
          <circle cx="50" cy="70" r="9" />
          <rect x="25" y="1.5" width="50" height="15" />
          <rect x="37" y="1.5" width="26" height="6" />
          <rect x="25" y="123.5" width="50" height="15" />
          <rect x="37" y="132.5" width="26" height="6" />
        </g>
      </svg>
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(255,255,255,0.08),transparent_60%)]" />
    </>
  );
}
