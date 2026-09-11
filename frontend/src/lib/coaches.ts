import type { CoachBoostType, Rarity } from "@/types";

export const BOOST_TYPE_LABELS: Record<CoachBoostType, string> = {
  attack_central: "Атака в центре", attack_wing: "Атака на флангах", midfield_control: "Контроль полузащиты",
  defence_central: "Защита в центре", defence_wing: "Защита на флангах", goalkeeping: "Игра вратаря",
  passing_accuracy: "Точность передач", ball_control: "Контроль мяча", defensive_discipline: "Дисциплина в обороне",
  counter_mastery: "Мастерство контратак", squad_stability: "Стабильность состава",
};

export const BOOST_TYPES: CoachBoostType[] = [
  "attack_central", "attack_wing", "midfield_control", "defence_central", "defence_wing",
  "goalkeeping", "passing_accuracy", "ball_control", "defensive_discipline", "counter_mastery", "squad_stability",
];

// Mirrors backend/app/services/coach_service.py's _TIER_INDEX_BY_RARITY /
// _BASE_UNIT_BY_BOOST_TYPE (spec §4) for a live read-only preview in the admin
// form. Display-only — the backend is the sole source of truth for the actual
// stored magnitude; the client no longer sends one at all.
const TIER_INDEX_BY_RARITY: Partial<Record<Rarity, number>> = { common: 1, rare: 2, epic: 3, legendary: 4 };
const BASE_UNIT_BY_BOOST_TYPE: Record<CoachBoostType, number> = {
  attack_central: 2, attack_wing: 2, midfield_control: 2, defence_central: 2, defence_wing: 2, goalkeeping: 2,
  passing_accuracy: 1, squad_stability: 1,
  ball_control: 0.03, defensive_discipline: 0.01, counter_mastery: 0.1,
};

export function magnitudeFor(boostType: CoachBoostType, rarity: Rarity): number {
  const tier = TIER_INDEX_BY_RARITY[rarity] ?? 0;
  return Math.round(BASE_UNIT_BY_BOOST_TYPE[boostType] * tier * 1000) / 1000;
}
