import type { Rarity } from "@/types";

export const RARITY_LABELS: Record<Rarity, string> = {
  common: "Обычная",
  rare: "Редкая",
  epic: "Эпическая",
  legendary: "Легендарная",
  diamond: "Диамантовая",
};

export const RARITY_GRADIENTS: Record<Rarity, string> = {
  common: "from-slate-500 to-slate-700",
  rare: "from-blue-500 to-cyan-600",
  epic: "from-purple-500 to-fuchsia-600",
  legendary: "from-amber-400 via-orange-500 to-red-500",
  // Pink → icy cyan → violet, not a single hue like the others — paired with
  // an oversized bg-[length:...] + animate-diamond-shimmer (see RARITY_GLOW)
  // so the band actually sweeps across the border, like light catching the
  // facets of a cut diamond rather than a static two-tone card. Every call
  // site prefixes this with the literal class `bg-gradient-to-b`, so the
  // gradient only varies along Y — richer/more saturated stops than the
  // other rarities' since this one has to read as "shifting", not static.
  diamond: "from-fuchsia-400 via-cyan-300 to-violet-500",
};

export const RARITY_GLOW: Record<Rarity, string> = {
  common: "",
  rare: "shadow-glow-rare",
  epic: "shadow-glow-epic",
  legendary: "shadow-glow-legendary animate-legendary-pulse",
  // bg-[length:...] belongs here (not RARITY_GRADIENTS) because every call
  // site already concatenates both onto the same element — this is what
  // gives animate-diamond-shimmer's background-position something to move
  // across. Every call site's gradient is `bg-gradient-to-b` (varies along
  // Y only), so only the Y size/position matters — X is left at 100% since
  // enlarging it would do nothing but isn't wrong either.
  diamond: "shadow-glow-diamond bg-[length:100%_400%] animate-diamond-shimmer",
};

export const RARITY_TEXT: Record<Rarity, string> = {
  common: "text-slate-300",
  rare: "text-blue-400",
  epic: "text-purple-400",
  legendary: "text-amber-400",
  diamond: "text-cyan-300",
};

export const RARITY_ORDER: Record<Rarity, number> = { common: 0, rare: 1, epic: 2, legendary: 3, diamond: 4 };

export const POSITION_LABELS: Record<string, string> = {
  GK: "Вратарь",
  LB: "Левый защитник",
  CB: "Центральный защитник",
  RB: "Правый защитник",
  CDM: "Опорный полузащитник",
  CM: "Центральный полузащитник",
  CAM: "Атакующий полузащитник",
  LM: "Левый полузащитник",
  RM: "Правый полузащитник",
  LW: "Левый нападающий",
  RW: "Правый нападающий",
  ST: "Нападающий",
};
