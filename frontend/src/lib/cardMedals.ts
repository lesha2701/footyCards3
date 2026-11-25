/** «Легенда карты»: medals this very copy earned in the Arena. They are
 * the copy's own numbers, so they go with it to the next owner. */
export function cardMedals(goals: number, assists: number, mvps: number): string[] {
  const out: string[] = [];
  if (goals >= 100) out.push("⚽ Легенда-бомбардир");
  else if (goals >= 50) out.push("⚽ Бомбардир");
  if (assists >= 50) out.push("🎯 Распасовщик");
  if (mvps >= 25) out.push("🏆 Звезда матчей");
  else if (mvps >= 10) out.push("🏅 MVP");
  return out;
}
