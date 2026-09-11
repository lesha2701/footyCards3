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
