import { useState, type ReactNode } from "react";

import type { ManagerLine, ManagerStyle, ManagerTacticsRules } from "@/api/manager";
import { formationLabel } from "@/lib/formationLayout";

const LINE_LABEL: Record<ManagerLine, string> = { FWD: "Атака", MID: "Полузащита", DEF: "Защита", GK: "Вратарь" };
const STYLE_ICON: Record<ManagerStyle, string> = { attacking: "⚔️", possession: "🔄", defensive: "🛡️", counter: "⚡" };

function signed(n: number): string {
  const r = Math.round(n * 10) / 10;
  return r > 0 ? `+${r}%` : r < 0 ? `−${Math.abs(r)}%` : "0%";
}

export interface TacticsNextMatch {
  opponent: string;
  /** Shown after the name: owner, rating, round… */
  detail?: string;
  style: ManagerStyle;
  formation: string;
  edge: "win" | "lose" | "even";
  mods: Record<ManagerLine, number>;
}

/** Tactics, Card Arena style: a formation (slots + a small attack/defense
 * tilt) and one of four styles in a circle, with the next opponent's style
 * and «how a match is decided». Used by «Менеджер» and «Личный турнир». */
export default function TacticsPanel({ style, formation, rules, next, busy, onChange, help, note }: {
  style: ManagerStyle; formation: string; rules: ManagerTacticsRules; next: TacticsNextMatch | null; busy: boolean;
  onChange: (patch: { formation?: string; style?: ManagerStyle }) => void;
  /** «Как считается матч?» body. */
  help: ReactNode;
  /** Under the formations. */
  note?: string;
}) {
  const [helpOpen, setHelpOpen] = useState(false);
  const styleLabel = (s: ManagerStyle) => rules.styles.find((x) => x.value === s)?.label ?? s;
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4" data-testid="tactics">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">Тактика</h2>
        <button onClick={() => setHelpOpen(!helpOpen)} className="text-micro text-ink-mist underline">Как считается матч?</button>
      </div>

      {next && (
        <div className={`rounded-xl p-3 text-xs ${next.edge === "win" ? "bg-emerald-500/15 ring-1 ring-emerald-500/40" : next.edge === "lose" ? "bg-red-500/10 ring-1 ring-red-500/30" : "bg-bg-raised"}`}>
          <p className="text-ink-chalk">
            Следующий соперник: <b>{next.opponent}</b>{next.detail && <span className="text-ink-mist"> · {next.detail}</span>}
          </p>
          <p className="mt-0.5 text-ink-mist">
            Их стиль: {STYLE_ICON[next.style]} {styleLabel(next.style)} · {formationLabel(next.formation)} ·{" "}
            {next.edge === "win" ? <b className="text-emerald-400">твой стиль бьёт их (+{rules.edge_pct}% ко всем)</b>
              : next.edge === "lose" ? <b className="text-red-400">их стиль бьёт твой — подумай о смене</b>
                : "стили не пересекаются"}
          </p>
          <p className="mt-1 text-micro text-ink-mist">
            В этом матче: {(["FWD", "MID", "DEF", "GK"] as ManagerLine[]).map((l) => `${LINE_LABEL[l]} ${signed(next.mods[l])}`).join(" · ")}
          </p>
        </div>
      )}

      <div>
        <p className="mb-1.5 text-micro font-bold uppercase tracking-wide text-ink-mist">Стиль · Атака › Оборона › Владение › Контратака › Атака</p>
        <div className="grid grid-cols-2 gap-2">
          {rules.styles.map((s) => {
            const on = style === s.value;
            return (
              <button key={s.value} disabled={busy} onClick={() => onChange({ style: s.value })}
                className={`flex flex-col items-start gap-0.5 rounded-xl p-2.5 text-left ${on ? "bg-accent-lime/15 ring-2 ring-accent-lime" : "bg-bg-raised"}`}>
                <span className="text-sm font-bold text-ink-chalk">{STYLE_ICON[s.value]} {s.label}</span>
                <span className="text-micro text-ink-mist">{s.about}</span>
                <span className="text-micro text-emerald-400">Бьёт «{s.beats_label}»: {s.reason}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-micro font-bold uppercase tracking-wide text-ink-mist">Схема</p>
        <div className="flex flex-wrap gap-1.5">
          {rules.formations.map((f) => {
            const on = formation === f.value;
            return (
              <button key={f.value} disabled={busy} onClick={() => onChange({ formation: f.value })}
                className={`flex flex-col items-center rounded-xl px-2.5 py-1.5 ${on ? "bg-accent-cyan text-bg-base" : "bg-bg-raised text-ink-chalk"}`}>
                <span className="text-xs font-bold">{f.label}</span>
                <span className={`text-[9px] ${on ? "text-bg-base/80" : "text-ink-mist"}`}>
                  {f.attack === 0 && f.defense === 0 ? "баланс" : `ат ${signed(f.attack)} · защ ${signed(f.defense)}`}
                </span>
              </button>
            );
          })}
        </div>
        {note && <p className="mt-1 text-micro text-ink-mist">{note}</p>}
      </div>

      {helpOpen && (
        <div className="flex flex-col gap-1.5 rounded-xl bg-bg-raised p-3 text-micro text-ink-mist" data-testid="match-help">
          <p className="text-xs font-bold text-ink-chalk">Как считается матч</p>
          {help}
        </div>
      )}
    </section>
  );
}
