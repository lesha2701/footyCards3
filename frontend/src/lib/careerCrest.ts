/** «Карьера тренера»: an emblem for a club that has none (bot clubs, and the
 * coaches' teams in a season), worked out from its name so the same club
 * always wears the same crest — in the table, the calendar, the cup and the
 * match. A word in the name can pick the symbol («Сокол» → hawk); otherwise
 * the hash does. Drawn by manager/Emblem with the clubs' picture symbols. */

const SHAPES = ["shield", "crest", "circle", "hexagon", "shield", "crest", "diamond", "castle"] as const;

// Main colour and the band / symbol colour: classic football pairs.
const COLOURS: [string, string][] = [
  ["#c8102e", "#ffffff"], ["#1d4ed8", "#ffffff"], ["#15803d", "#ffffff"], ["#111827", "#f5f5f5"],
  ["#facc15", "#1e3a8a"], ["#7f1d1d", "#7dd3fc"], ["#ea580c", "#111827"], ["#1e3a8a", "#fbbf24"],
  ["#b91c1c", "#111827"], ["#f8fafc", "#1e3a8a"], ["#6d28d9", "#ffffff"], ["#0f766e", "#fde68a"],
  ["#0369a1", "#facc15"], ["#166534", "#facc15"], ["#9f1239", "#fde68a"], ["#374151", "#f97316"],
];

const SYMBOLS = [
  "anchor", "ball", "bear", "bison", "boar", "bull", "compass", "crocodile", "crossed_swords", "crown", "eagle",
  "flame", "fox", "griffin", "hawk", "horse", "horseshoe", "knight_helmet", "kraken", "lightning", "lion",
  "mountain", "oak", "owl", "panther", "pegasus", "phoenix", "ram", "raven", "rhino", "rocket", "rose",
  "scorpion", "shark", "stag", "star", "tiger", "tower", "trident", "wave", "winged_ball", "wolf", "dragon", "cobra",
];

// Word stems in a club name that suggest its symbol.
const BY_WORD: [string, string][] = [
  ["сокол", "hawk"], ["орл", "eagle"], ["орёл", "eagle"], ["беркут", "eagle"], ["ворон", "raven"], ["волк", "wolf"],
  ["лев", "lion"], ["львы", "lion"], ["медвед", "bear"], ["тигр", "tiger"], ["барс", "panther"], ["зубр", "bison"],
  ["лис", "fox"], ["олен", "stag"], ["конь", "horse"], ["кон", "horse"], ["дракон", "dragon"], ["акул", "shark"],
  ["звезд", "star"], ["звёзд", "star"], ["сатурн", "star"], ["комет", "star"], ["ракет", "rocket"], ["торпед", "rocket"],
  ["космос", "rocket"], ["факел", "flame"], ["пламя", "flame"], ["огон", "flame"], ["энерг", "lightning"],
  ["динамо", "lightning"], ["молни", "lightning"], ["якор", "anchor"], ["моряк", "anchor"], ["балтик", "anchor"],
  ["волн", "wave"], ["нептун", "trident"], ["горняк", "mountain"], ["шахт", "mountain"], ["урал", "mountain"],
  ["арсенал", "crossed_swords"], ["спартак", "knight_helmet"], ["витяз", "knight_helmet"], ["крыль", "winged_ball"],
  ["дуб", "oak"], ["лесн", "oak"], ["роза", "rose"], ["корон", "crown"], ["царь", "crown"], ["башн", "tower"],
  ["крепост", "tower"], ["заря", "phoenix"], ["феникс", "phoenix"], ["сова", "owl"], ["компас", "compass"],
];

function hash(text: string): number {
  let h = 2166136261;
  for (const ch of text) {
    h ^= ch.codePointAt(0) ?? 0;
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

export type CrestLook = { shape: string; symbol: string; color: string; color2: string };

export function careerCrest(name: string): CrestLook {
  const key = name.trim().toLowerCase();
  const h = hash(key);
  const [color, color2] = COLOURS[h % COLOURS.length];
  const word = BY_WORD.find(([stem]) => key.includes(stem));
  const symbol = word ? word[1] : SYMBOLS[(h >>> 8) % SYMBOLS.length];
  return { shape: SHAPES[(h >>> 16) % SHAPES.length], symbol: `img_${symbol}`, color, color2 };
}
