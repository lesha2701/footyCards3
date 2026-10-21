import { useState } from "react";

import type { ManagerClub, ManagerLine, ManagerStyle, ManagerTacticsRules } from "@/api/manager";
import { formationLabel } from "@/lib/formationLayout";

const LINE_LABEL: Record<ManagerLine, string> = { FWD: "Атака", MID: "Полузащита", DEF: "Защита", GK: "Вратарь" };
const STYLE_ICON: Record<ManagerStyle, string> = { attacking: "⚔️", possession: "🔄", defensive: "🛡️", counter: "⚡" };

function signed(n: number): string {
  const r = Math.round(n * 10) / 10;
  return r > 0 ? `+${r}%` : r < 0 ? `−${Math.abs(r)}%` : "0%";
}

/** Tactics of «Менеджер», Card Arena style: a formation (slots + a small
 * attack/defense tilt) and one of four styles in a circle, with the next
 * opponent's style and «how a match is decided». */
export default function TacticsPanel({ club, rules, busy, onChange }: {
  club: ManagerClub; rules: ManagerTacticsRules; busy: boolean;
  onChange: (patch: { formation?: string; style?: ManagerStyle }) => void;
}) {
  const [help, setHelp] = useState(false);
  const styleLabel = (s: ManagerStyle) => rules.styles.find((x) => x.value === s)?.label ?? s;
  const next = club.next_match;
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4" data-testid="tactics">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">Тактика</h2>
        <button onClick={() => setHelp(!help)} className="text-micro text-ink-mist underline">Как считается матч?</button>
      </div>

      {next && (
        <div className={`rounded-xl p-3 text-xs ${next.edge === "win" ? "bg-emerald-500/15 ring-1 ring-emerald-500/40" : next.edge === "lose" ? "bg-red-500/10 ring-1 ring-red-500/30" : "bg-bg-raised"}`}>
          <p className="text-ink-chalk">
            Следующий соперник: <b>{next.opponent}</b>{next.owner_name && <span className="text-ink-mist"> · {next.owner_name}</span>}
            {next.rating != null && <span className="text-ink-mist"> · рейтинг {next.rating}</span>}
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
            const on = club.style === s.value;
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
            const on = club.formation === f.value;
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
        <p className="mt-1 text-micro text-ink-mist">Тактику можно менять и во время сезона — она действует со следующего тура.</p>
      </div>

      {help && (
        <div className="flex flex-col gap-1.5 rounded-xl bg-bg-raised p-3 text-micro text-ink-mist" data-testid="match-help">
          <p className="text-xs font-bold text-ink-chalk">Как считается матч</p>
          <p>1. <b className="text-ink-chalk">Состав.</b> 11 игроков по схеме: твой «Мой игрок» и игрок академии всегда в старте, остальные — сильнейшие по позиции. Игрок не на своей позиции играет слабее.</p>
          <p>2. <b className="text-ink-chalk">Тактика.</b> Стиль даёт % к рейтингу своих линий, схема — небольшой крен в атаку или защиту. Если твой стиль бьёт стиль соперника, все твои игроки получают +{rules.edge_pct}%.</p>
          <p>3. <b className="text-ink-chalk">Игра.</b> Движок разыгрывает владение и моменты: полузащита борется за мяч, нападающие — с защитниками в дуэлях, удары — против вратаря. Чем выше рейтинги в нужной зоне, тем больше и опаснее моменты. Навыки и артефакты «Моих игроков» тоже работают.</p>
          <p>4. <b className="text-ink-chalk">Случай.</b> Футбол есть футбол: слабый иногда побеждает, но на дистанции сезона решает сила и тактика.</p>
          <p>5. <b className="text-ink-chalk">Итог.</b> 3 очка за победу, 1 за ничью. Клуб получает € за результат и билеты на домашних матчах, «Мои игроки» — опыт и статистику для «Золотого мяча».</p>
        </div>
      )}
    </section>
  );
}
