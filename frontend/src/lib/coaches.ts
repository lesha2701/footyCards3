import type { CoachBoostType } from "@/types";

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

// Most boosts are flat rating points (legendary tier ~4-8). Three boosts are
// additive to a small multiplier instead and use a much smaller native unit
// — shown here so an admin doesn't enter a rating-point-sized number where a
// value like 0.1 is meant, matching backend/app/schemas/coach.py's
// _TIGHT_MAGNITUDE_BOUNDS for these same three boost types.
export const BOOST_TYPE_UNIT_HINTS: Partial<Record<CoachBoostType, string>> = {
  ball_control: "малое число, легендарный уровень ~0.12 (не рейтинг)",
  defensive_discipline: "малое число, легендарный уровень ~0.04 (не рейтинг)",
  counter_mastery: "малое число, легендарный уровень ~0.4 (не рейтинг)",
};
