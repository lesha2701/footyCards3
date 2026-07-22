import type { Rarity } from "@/types";

export const RARITY_LABELS: Record<Rarity, string> = {
  common: "Обычная",
  rare: "Редкая",
  epic: "Эпическая",
  legendary: "Легендарная",
};

export const RARITY_GRADIENTS: Record<Rarity, string> = {
  common: "from-slate-500 to-slate-700",
  rare: "from-blue-500 to-cyan-600",
  epic: "from-purple-500 to-fuchsia-600",
  legendary: "from-amber-400 via-orange-500 to-red-500",
};

export const RARITY_GLOW: Record<Rarity, string> = {
  common: "",
  rare: "shadow-glow-rare",
  epic: "shadow-glow-epic",
  legendary: "shadow-glow-legendary animate-pulse-slow",
};

export const RARITY_TEXT: Record<Rarity, string> = {
  common: "text-slate-300",
  rare: "text-blue-400",
  epic: "text-purple-400",
  legendary: "text-amber-400",
};

export const RARITY_ORDER: Record<Rarity, number> = { common: 0, rare: 1, epic: 2, legendary: 3 };

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
