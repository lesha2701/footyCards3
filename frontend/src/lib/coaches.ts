import type { CoachBoost, CoachBoostType } from "@/types";

export const BOOST_TYPE_LABELS: Record<CoachBoostType, string> = {
  attack_central: "Атака в центре", attack_wing: "Атака на флангах", midfield_control: "Контроль полузащиты",
  defence_central: "Защита в центре", defence_wing: "Защита на флангах", goalkeeping: "Игра вратаря",
  passing_accuracy: "Точность передач", ball_control: "Контроль мяча", defensive_discipline: "Дисциплина в обороне",
  counter_mastery: "Мастерство контратак", squad_stability: "Стабильность состава",
  team_rating: "Рейтинг всей команды", opp_attack: "Атака соперника", opp_defence: "Оборона соперника",
  opp_goalkeeping: "Вратарь соперника", opp_team: "Рейтинг соперника",
};

export const BOOST_TYPES: CoachBoostType[] = [
  "attack_central", "attack_wing", "midfield_control", "defence_central", "defence_wing",
  "goalkeeping", "passing_accuracy", "ball_control", "defensive_discipline", "counter_mastery", "squad_stability",
  "team_rating", "opp_attack", "opp_defence", "opp_goalkeeping", "opp_team",
];

/** Boosts that weaken the opponent (Card Arena) — shown with a minus. */
export const OPPONENT_BOOSTS = new Set<CoachBoostType>(["opp_attack", "opp_defence", "opp_goalkeeping", "opp_team"]);

/** «Атака в центре +8», «Атака соперника −4»: one boost as players read it. */
export function boostText(boost: Pick<CoachBoost, "boost_type" | "magnitude">): string {
  const value = Number(boost.magnitude);
  const shown = value < 1 ? `${value}` : `${Math.round(value)}`;
  return `${BOOST_TYPE_LABELS[boost.boost_type] ?? boost.boost_type} ${OPPONENT_BOOSTS.has(boost.boost_type) ? "−" : "+"}${shown}`;
}
