/** «Редкие версии»: a copy that came out of a pack as a special print. */
export type CardFinish = "gold" | "autograph" | "night";

export const FINISH_LABELS: Record<CardFinish, string> = {
  gold: "Золотая версия",
  autograph: "С автографом",
  night: "Ночная версия",
};

export const FINISH_ICONS: Record<CardFinish, string> = { gold: "✨", autograph: "✍️", night: "🌙" };

export function asFinish(value: string | null | undefined): CardFinish | null {
  return value === "gold" || value === "autograph" || value === "night" ? value : null;
}

/** «Месси» from «Лионель Месси»: the name a player would sign. */
export function signatureName(displayName: string): string {
  const parts = displayName.trim().split(/\s+/);
  return parts[parts.length - 1] || displayName;
}
