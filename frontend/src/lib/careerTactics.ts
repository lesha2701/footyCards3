import type { MatchupHint } from "@/api/career";

export function tacticLabel(list: { value: string; label: string }[], value: string | null | undefined): string {
  return list.find((o) => o.value === value)?.label ?? value ?? "—";
}

export const HINT_TEXT: Record<MatchupHint, { label: string; tone: string }> = {
  advantage: { label: "Преимущество", tone: "bg-accent-lime/15 text-accent-lime" },
  neutral: { label: "Нейтрально", tone: "bg-white/10 text-ink-mist" },
  disadvantage: { label: "Невыгодно", tone: "bg-red-500/15 text-red-400" },
};
