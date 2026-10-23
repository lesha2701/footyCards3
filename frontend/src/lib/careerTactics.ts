import type { MatchupHint, Tactic, TacticsCatalog } from "@/api/career";

export function tacticLabel(list: { value: string; label: string }[], value: string | null | undefined): string {
  return list.find((o) => o.value === value)?.label ?? value ?? "—";
}

export const HINT_TEXT: Record<MatchupHint, { label: string; tone: string }> = {
  advantage: { label: "Преимущество", tone: "bg-accent-lime/15 text-accent-lime" },
  neutral: { label: "Нейтрально", tone: "bg-white/10 text-ink-mist" },
  disadvantage: { label: "Невыгодно", tone: "bg-red-500/15 text-red-400" },
};

/** Phases of play the axes are grouped into on the tactics screen. */
export const AXIS_PHASES: { title: string; axes: string[] }[] = [
  { title: "С мячом", axes: ["direction", "buildup"] },
  { title: "Переходы", axes: ["on_loss", "on_win"] },
  { title: "Без мяча", axes: ["block", "tackling"] },
];

export function axisValueLabel(catalog: TacticsCatalog | null | undefined, axis: string, value: string | undefined): string {
  const found = catalog?.axes.find((a) => a.key === axis)?.values.find((v) => v.value === value);
  return found?.label ?? value ?? "—";
}

export function axisLabel(catalog: TacticsCatalog | null | undefined, axis: string): string {
  return catalog?.axes.find((a) => a.key === axis)?.label ?? axis;
}

export function presetOf(catalog: TacticsCatalog | null | undefined, tactic: Tactic | null | undefined): string | null {
  if (!catalog || !tactic) return null;
  const preset = catalog.presets.find((p) => catalog.axes.every((a) => p.tactic[a.key] === tactic[a.key]));
  return preset ? preset.label : null;
}

export function sameTactic(a: Tactic | null | undefined, b: Tactic | null | undefined): boolean {
  if (!a || !b) return a === b;
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  return [...keys].every((k) => a[k] === b[k]);
}

/** Familiarity a tactic would play at — the server's rule (a new formation
 * keeps keep_pct, each changed axis keeps axis_keep_pct), for the preview
 * before saving. */
export function previewFamiliarity(
  stored: number, keepPct: number, axisKeepPct: number,
  lastFormation: string | null, lastTactic: Tactic | null, formation: string, tactic: Tactic,
): number {
  let value = stored;
  if (lastFormation && formation !== lastFormation) value = (value * keepPct) / 100;
  if (lastTactic) {
    for (const [axis, v] of Object.entries(lastTactic)) {
      if (tactic[axis] !== undefined && tactic[axis] !== v) value = (value * axisKeepPct) / 100;
    }
  }
  return Math.round(value * 10) / 10;
}
