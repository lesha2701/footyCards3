import type { MyPlayerAttr, MyPlayerCosmeticKind, MyPlayerDrill, MyPlayerTier } from "@/api/myPlayer";

// Option sets — counts must match backend my_player_service.APPEARANCE_OPTIONS.
export const SKIN_TONES = ["#f6d7c3", "#eac0a0", "#d7a27c", "#b67b52", "#8d5a3b", "#5e3b26"];
export const HAIR_COLORS = ["#1f1a17", "#4a2f1f", "#7b4a26", "#c08a3e", "#e3c27a", "#a33a1f", "#bdbdbd"];
export const HAIR_LABELS = [
  "Ёжик", "Короткая", "Кок", "Кудри", "Длинные", "Ирокез", "Афро", "Лысый",
  "Андеркат", "Дреды", "Пучок", "Зачёс назад", "Пробор", "Косички",
];
export const EYE_COLORS = ["#4a3426", "#24160d", "#3b82c4", "#3f8f5a", "#7b8794", "#8a6a2f"];
export const EYE_LABELS = ["Карие", "Тёмные", "Голубые", "Зелёные", "Серые", "Ореховые"];
export const BEARD_LABELS = ["Нет", "Щетина", "Эспаньолка", "Борода", "Усы"];
export const KIT_COLORS = [
  "#d62828", "#1d4ed8", "#38bdf8", "#15803d", "#facc15", "#f97316", "#7c3aed", "#18181b", "#f4f4f5", "#7f1d1d",
];
export const KIT_PATTERN_LABELS = ["Однотонная", "Полосы", "Обручи", "Лента"];

export const TIER_FRAMES: Record<MyPlayerTier, string> = {
  bronze: "from-amber-700 via-orange-800 to-amber-950",
  silver: "from-slate-200 via-slate-400 to-slate-600",
  gold: "from-yellow-200 via-amber-400 to-yellow-600 shadow-glow-legendary",
  legend: "from-fuchsia-400 via-cyan-300 to-violet-500 shadow-glow-diamond bg-[length:100%_400%] animate-diamond-shimmer",
};

export const TIER_TEXT: Record<MyPlayerTier, string> = {
  bronze: "text-amber-600",
  silver: "text-slate-300",
  gold: "text-yellow-300",
  legend: "text-fuchsia-300",
};

export const ATTR_ORDER: MyPlayerAttr[] = ["atk", "def"];
export const ATTR_SHORT: Record<MyPlayerAttr, string> = { atk: "АТК", def: "ЗЩТ" };

export const DRILL_ICONS: Record<MyPlayerDrill, string> = { shot: "⚽", pass: "🎯", tackle: "🛡️", save: "🧤" };

export const COSMETIC_GROUPS: { kind: MyPlayerCosmeticKind; title: string }[] = [
  { kind: "hair", title: "Прически звёзд" },
  { kind: "accessory", title: "Аксессуары" },
  { kind: "background", title: "Фон карточки" },
  { kind: "effect", title: "Эффект карточки" },
  { kind: "celebration", title: "Празднование гола" },
  { kind: "ball", title: "Мяч (штрафной и пенальти)" },
  { kind: "boots", title: "Бутсы (штрафной и пенальти)" },
  { kind: "gloves", title: "Перчатки вратаря (пенальти)" },
  { kind: "walkout", title: "Выход на поле" },
  { kind: "showcase", title: "Шкаф трофеев" },
];

export const CELEBRATION_EMOJI: Record<string, string> = {
  cel_siu: "🙌", cel_plane: "✈️", cel_heart: "❤️", cel_dance: "🕺", cel_fist: "✊", cel_shush: "🤫",
  cel_flex: "💪", cel_knee: "🧎", cel_calma: "🙏", cel_flip: "🤸", cel_siu_gold: "🏆", cel_silly: "🤪",
};

export const WALKOUT_EMOJI: Record<string, string> = {
  walk_tunnel: "🚇", walk_flags: "🚩", walk_smoke: "💨", walk_fireworks: "🎆", walk_legend: "👑",
};

/** Trophy cabinet styles: the shelf gradient and the frame ring. null = wood. */
export const SHOWCASE_STYLE: Record<string, { shelf: string; ring: string; label: string }> = {
  wood: { shelf: "from-amber-900/50 via-amber-800/30 to-bg-surface", ring: "ring-amber-700/50", label: "Деревянная витрина" },
  sc_marble: { shelf: "from-slate-200/25 via-slate-400/15 to-bg-surface", ring: "ring-slate-300/60", label: "Мраморная витрина" },
  sc_gold: { shelf: "from-yellow-400/35 via-amber-500/20 to-bg-surface", ring: "ring-yellow-300/80", label: "Золотая витрина" },
  sc_crystal: { shelf: "from-cyan-300/30 via-fuchsia-300/20 to-bg-surface", ring: "ring-cyan-200/80", label: "Хрустальная витрина" },
};

export const TIER_NAMES: Record<MyPlayerTier, string> = { bronze: "Бронза", silver: "Серебро", gold: "Золото", legend: "Легенда" };
