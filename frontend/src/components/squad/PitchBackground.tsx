/** Striped grass with pitch markings, drawn behind any squad editor's
 * cards. Render it as the first child of a `relative overflow-hidden`
 * container (the chemistry overlay, if any, goes right after it). */
export default function PitchBackground() {
  return (
    <>
      <svg className="pointer-events-none absolute inset-0 h-full w-full" viewBox="0 0 100 140" preserveAspectRatio="none" aria-hidden>
        <g fill="none" stroke="#ffffff" strokeOpacity="0.16" strokeWidth="0.45">
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
