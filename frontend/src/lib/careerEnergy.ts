/** A player's energy: 100 − the backend's fatigue, and how tired that is. */

/** Energy left (0-100) from the backend's fatigue (0-100). */
export function energyOf(fatigue: number): number {
  return Math.max(0, Math.min(100, Math.round(100 - fatigue)));
}

export type EnergyLevel = "fresh" | "tired" | "spent";

/** Fresh from 60 %, a bit tired from 30 %, spent below (fatigue 70 + —
 * when the plan and the half-time proposal take a player off). */
export function energyLevel(energy: number): EnergyLevel {
  return energy >= 60 ? "fresh" : energy >= 30 ? "tired" : "spent";
}
