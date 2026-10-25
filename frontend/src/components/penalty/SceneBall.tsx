/** The match ball for the penalty / free-kick scenes: square SVG that fills
 * its box, with a soft shadow under it. */
export function SceneBall() {
  return (
    <svg viewBox="0 0 24 24" className="block w-full drop-shadow-[0_3px_3px_rgba(0,0,0,0.55)]" aria-hidden>
      <circle fill="#f6f8f6" cx={12} cy={12} r={10} />
      <path fill="#1f2937" d="M12 7.2 15.2 9.5 14 13.3H10L8.8 9.5Z" />
      <path
        fill="none" stroke="#1f2937" strokeWidth={1.1} strokeLinecap="round"
        d="M12 7.2V2.6M15.2 9.5 19.6 8M14 13.3l2.7 3.9M10 13.3l-2.7 3.9M8.8 9.5 4.4 8"
      />
      <circle fill="none" stroke="#1f2937" strokeWidth={1} cx={12} cy={12} r={10} />
    </svg>
  );
}
