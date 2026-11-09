/** «Подготовка» sections as three big tiles: an icon, the name and, under it,
 * what stands there right now, so a problem with the squad shows without
 * opening it. */
import type { CareerSeason } from "@/api/career";
import { readiness } from "@/components/career/MatchScreens";
import { IconShirt, IconTarget, IconWhistle } from "@/components/icons";

export type PrepTab = "tactic" | "squad" | "training";

type Tone = "good" | "warn" | "bad" | "plain";
const TONE: Record<Tone, string> = {
  good: "text-accent-lime", warn: "text-amber-300", bad: "text-red-300", plain: "text-ink-mist",
};

function squadStatus(season: CareerSeason): { text: string; tone: Tone } {
  const { tired, out } = readiness(season);
  const missing = season.slots.length - Object.keys(season.lineup ?? {}).length;
  const critical = (season.squad_warnings ?? []).some((w) => w.level === "critical");
  if (out.length > 0) return { text: `Не сыграют: ${out.length}`, tone: "bad" };
  if (missing > 0) return { text: `Пусто: ${missing}`, tone: "bad" };
  if (critical) return { text: "Не по амплуа", tone: "bad" };
  if (tired.length > 0) return { text: `Устали: ${tired.length}`, tone: "warn" };
  return { text: "Готов", tone: "good" };
}

function tacticStatus(season: CareerSeason): { text: string; tone: Tone } {
  const pct = season.scouting?.win_pct;
  return pct == null ? { text: "План на матч", tone: "plain" } : { text: `${Math.round(pct)}% побед`, tone: "plain" };
}

function trainingStatus(season: CareerSeason): { text: string; tone: Tone } {
  const main = season.trainings?.find((t) => t.code === season.training)?.label;
  return main ? { text: season.training_plan?.extra ? `${main} +1` : main, tone: "good" } : { text: "Не выбрана", tone: "warn" };
}

export function PrepTabs({ season, value, onChange }: { season: CareerSeason; value: PrepTab; onChange: (tab: PrepTab) => void }) {
  const items = [
    { id: "tactic", label: "Тактика", Icon: IconTarget, status: tacticStatus(season) },
    { id: "squad", label: "Состав", Icon: IconShirt, status: squadStatus(season) },
    { id: "training", label: "Тренировка", Icon: IconWhistle, status: trainingStatus(season) },
  ] as const;
  return (
    <div className="grid grid-cols-3 gap-1.5" role="tablist" aria-label="Подготовка">
      {items.map(({ id, label, Icon, status }) => {
        const on = value === id;
        return (
          <button
            key={id}
            role="tab"
            aria-selected={on}
            onClick={() => onChange(id)}
            className={`flex min-w-0 flex-col items-center gap-1 rounded-2xl px-1 py-2.5 transition active:scale-95 ${
              on ? "bg-accent-lime/10 ring-2 ring-accent-lime/70" : "bg-bg-surface ring-1 ring-white/10"
            }`}
          >
            <span className={`flex h-9 w-9 items-center justify-center rounded-xl ${on ? "bg-floodlight text-bg-base" : "bg-white/10 text-ink-chalk"}`}>
              <Icon size={20} aria-hidden="true" />
            </span>
            <span className={`text-xs font-bold ${on ? "text-ink-chalk" : "text-ink-mist"}`}>{label}</span>
            <span className={`max-w-full truncate text-micro font-semibold ${TONE[status.tone]}`}>{status.text}</span>
          </button>
        );
      })}
    </div>
  );
}
