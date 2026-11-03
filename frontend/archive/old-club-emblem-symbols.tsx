/*
 * Archive: the first hand-drawn club emblem symbols (style_key ball, crown, lion,
 * eagle, lightning, castle, star, trophy, wings, anchor, wolf, swords), drawn in
 * frontend/src/components/clubs/ClubLogo.tsx until they were replaced by the
 * picture set (static/emblems/symbols/*.webp, style_key img_*). Not imported
 * anywhere — kept only to be able to bring them back.
 *
 * Helpers it needs (were in ClubLogo.tsx):
 *   const LION_MANE = starPath(50, 50, 14, 21, 15);
 *   const STAR = starPath(50, 51, 5, 21, 9);
 */
/** Symbols in the middle, 100×100 space. `base` is the club colour (for cut-outs). */
function SymbolMark({ kind, fill, base, y = 0, scale = 1 }: { kind: string; fill: string; base: string; y?: number; scale?: number }) {
  const t = `translate(50 ${50 + y}) scale(${scale}) translate(-50 -50)`;
  const stroke = { stroke: "rgba(0,0,0,0.35)", strokeWidth: 1.5, strokeLinejoin: "round" as const };
  let body: JSX.Element | null = null;
  switch (kind) {
    case "ball":
      body = (
        <g>
          <circle cx={50} cy={50} r={17} fill={fill} {...stroke} />
          <path d="M50 42 L57.6 47.5 L54.7 56.5 L45.3 56.5 L42.4 47.5 Z" fill="#1b1b1b" />
          <path d="M50 42 V33.5 M57.6 47.5 L65.5 44.5 M54.7 56.5 L59.5 64 M45.3 56.5 L40.5 64 M42.4 47.5 L34.5 44.5" stroke="#1b1b1b" strokeWidth={1.6} />
        </g>
      );
      break;
    case "crown":
      body = (
        <g fill={fill} {...stroke}>
          <path d="M29 63 L29 39 L40 50 L50 32 L60 50 L71 39 L71 63 Z" />
          <rect x={29} y={65} width={42} height={6} rx={1.5} />
        </g>
      );
      break;
    case "lion":
      body = (
        <g>
          <path d={LION_MANE} fill={fill} {...stroke} />
          <circle cx={50} cy={51} r={11.5} fill={base} />
          <circle cx={45.5} cy={48} r={1.8} fill={fill} />
          <circle cx={54.5} cy={48} r={1.8} fill={fill} />
          <path d="M46.5 54 L50 57.5 L53.5 54 Z" fill={fill} />
        </g>
      );
      break;
    case "eagle":
      body = <path d="M50 34 L56 45 L76 37 L67 51 L58 54 L55 67 L50 63 L45 67 L42 54 L33 51 L24 37 L44 45 Z" fill={fill} {...stroke} />;
      break;
    case "lightning":
      body = <path d="M56 28 L37 55 L49 55 L43 74 L64 45 L52 45 Z" fill={fill} {...stroke} />;
      break;
    case "castle":
      body = (
        <path
          d="M32 70 V44 H37 V38 H42 V44 H47 V38 H53 V44 H58 V38 H63 V44 H68 V70 H57 V60 A7 7 0 0 0 43 60 V70 Z"
          fill={fill}
          {...stroke}
        />
      );
      break;
    case "star":
      body = <path d={STAR} fill={fill} {...stroke} />;
      break;
    case "trophy":
      body = (
        <g fill={fill} {...stroke}>
          <path d="M34 50 C26 50 24 36 33 36 M66 50 C74 50 76 36 67 36" fill="none" stroke={fill} strokeWidth={3.5} />
          <path d="M35 31 H65 V40 C65 52 58 59 50 59 C42 59 35 52 35 40 Z" />
          <rect x={46.5} y={58} width={7} height={7} />
          <rect x={38} y={65} width={24} height={6} rx={1.5} />
        </g>
      );
      break;
    case "wings":
      body = (
        <g fill={fill} {...stroke}>
          <path d="M47 52 C40 41 30 36 18 37 C24 41 27 43 29 46 C23 46 18 48 16 53 C24 52 29 53 32 55 C27 57 25 60 24 64 C33 62 41 58 47 55 Z" />
          <path d="M53 52 C60 41 70 36 82 37 C76 41 73 43 71 46 C77 46 82 48 84 53 C76 52 71 53 68 55 C73 57 75 60 76 64 C67 62 59 58 53 55 Z" />
          <circle cx={50} cy={53} r={5} />
        </g>
      );
      break;
    case "anchor":
      body = (
        <g fill="none" stroke={fill} strokeWidth={5} strokeLinecap="round" strokeLinejoin="round">
          <circle cx={50} cy={31} r={4.5} />
          <path d="M50 36 V69 M40 44 H60 M31 56 C33 66 41 70 50 70 C59 70 67 66 69 56" />
          <path d="M27 58 L31 54 L35 59 M73 58 L69 54 L65 59" />
        </g>
      );
      break;
    case "wolf":
      body = (
        <g>
          <path d="M31 30 L39 44 L45 42 L50 46 L55 42 L61 44 L69 30 L69 52 L61 65 L50 72 L39 65 L31 52 Z" fill={fill} {...stroke} />
          <path d="M40 51 L46 53 L43 56 Z M60 51 L54 53 L57 56 Z" fill={base} />
          <path d="M46.5 62 L50 66 L53.5 62 Z" fill={base} />
        </g>
      );
      break;
    case "swords":
      body = (
        <g stroke={fill} strokeLinecap="round">
          <path d="M33 31 L65 63 M67 31 L35 63" strokeWidth={5} />
          <path d="M58 67 L69 56 M42 67 L31 56" strokeWidth={5} />
          <path d="M66 65 L71 70 M34 65 L29 70" strokeWidth={6} />
        </g>
      );
      break;
    default:
      if (!isImageSymbol(kind)) return null;
      body = <ImageSymbol symbol={kind} fill={fill} x={24} y={24} size={52} />;
  }
  return <g transform={t}>{body}</g>;
}

