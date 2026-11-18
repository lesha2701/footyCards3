import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import type { MyPlayerAppearance } from "@/api/myPlayer";
import { fetchProspect, type ProspectView } from "@/api/prospect";
import PlayerAvatar from "@/components/myPlayer/PlayerAvatar";
import { AGE_WORD, PROSPECT_KEY, roman } from "@/components/prospect/shared";
import { PROSPECT_ART, stageScene } from "@/lib/prospectArt";

// The child grows on the card: the avatar's scale by stage (as on his page).
const GROWTH = [0.62, 0.72, 0.82, 0.92, 1];

/** What waits for him today — the chips under the name, most urgent first. */
function events(v: ProspectView): string[] {
  const out: string[] = [];
  if (v.graduation?.available) out.push("🎓 Выпускной");
  if (v.position_pick) out.push("🧭 Выбери позицию");
  if (v.spec_pick) out.push("✨ Выбери талант");
  if (v.bday?.today && !v.bday.opened) out.push("🎂 День рождения");
  if ((v.duels ?? []).some((d) => d.can_play)) out.push("⚔️ Дуэль");
  if (v.training?.free_available) out.push("🏋️ Тренировка");
  if (v.story) out.push("📖 История");
  return out;
}

/** «Воспитанник Академии» on the home page, under «Менеджер»: one tap to him. A live scene of
 * his stage, the growing avatar, today's events; an invitation before the
 * first child and the graduate's card between generations. */
export default function ProspectHomeCard() {
  const navigate = useNavigate();
  const { data: v } = useQuery({ queryKey: PROSPECT_KEY, queryFn: fetchProspect, staleTime: 60_000 });
  if (!v) return null;
  const open = () => navigate("/academy/prospect");
  const p = v.prospect;

  if (!p && v.graduate) {
    const g = v.graduate;
    return (
      <Scene image={PROSPECT_ART.graduation} onClick={open} label="Выпускник Академии">
        <Figure appearance={g.appearance} number={g.number} scale={1} />
        <Info kicker={`🎓 Выпускник · ${roman(g.generation)} поколение`} title={g.name} rating={g.rating} ratingTone="text-legend">
          <span className="rounded-full bg-path px-2.5 py-1 text-[11px] font-bold text-bg-base">🌱 Новое поколение</span>
        </Info>
      </Scene>
    );
  }
  if (!p) {
    if (!v.enabled) return null;
    return (
      <Scene image={PROSPECT_ART.empty} onClick={open} label="Воспитанник Академии">
        <div className="relative mt-auto px-4 pb-3.5">
          <p className="text-micro uppercase tracking-wider text-path">Воспитанник Академии</p>
          <p className="font-display text-lg font-bold leading-tight text-ink-chalk">Вырасти своего игрока</p>
          <p className="text-xs text-ink-mist">С {v.start_age} лет до пика за ~100 дней: тренировки, матчи, выбор пути</p>
          <span className="mt-2 inline-block rounded-full bg-path px-3 py-1.5 text-xs font-bold text-bg-base">Взять в Академию</span>
        </div>
      </Scene>
    );
  }

  const stage = v.stages[p.stage];
  const todo = events(v);
  const pct = p.capped ? 100 : Math.round((p.xp_in_point / p.xp_per_point) * 100);
  return (
    <Scene image={stageScene(p.stage_code)} onClick={open} label={`Воспитанник ${p.name}`} alert={todo.length > 0}>
      <Figure appearance={p.appearance} number={p.number} scale={GROWTH[p.stage] ?? 1} />
      <Info kicker={`🌱 ${stage?.name ?? ""} · ${p.age} ${AGE_WORD(p.age)}`} title={p.name} rating={p.rating}>
        <div className="w-full">
          <div className="h-1.5 overflow-hidden rounded-full bg-black/40">
            <motion.div className="h-full rounded-full bg-path" initial={false} animate={{ width: `${pct}%` }} />
          </div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {todo.length ? todo.slice(0, 3).map((t) => (
              <span key={t} className="rounded-full bg-black/45 px-2 py-0.5 text-[11px] font-semibold text-ink-chalk ring-1 ring-path/40">{t}</span>
            )) : <span className="text-[11px] text-ink-mist">На сегодня всё — он отдыхает</span>}
          </div>
        </div>
      </Info>
    </Scene>
  );
}

function Scene({ image, onClick, label, alert, children }: {
  image: string; onClick: () => void; label: string; alert?: boolean; children: ReactNode;
}) {
  return (
    <button onClick={onClick} aria-label={label} data-testid="prospect-home-card"
      className="relative mb-2 flex h-[164px] w-full flex-col overflow-hidden rounded-3xl bg-bg-surface text-left ring-1 ring-path/25 active:scale-[0.99]">
      <img src={image} alt="" aria-hidden className="pointer-events-none absolute inset-0 h-full w-full object-cover object-top" />
      <span className="pointer-events-none absolute inset-0 bg-gradient-to-t from-bg-base/95 via-bg-base/30 to-transparent" />
      {alert && <span className="absolute right-3 top-3 h-2.5 w-2.5 animate-pulse rounded-full bg-accent-lime" aria-label="Есть дела" />}
      {children}
    </button>
  );
}

/** The avatar stands on the scene's ground (about the middle of the picture). */
function Figure({ appearance, number, scale }: { appearance: MyPlayerAppearance; number: number; scale: number }) {
  return (
    <div className="pointer-events-none absolute bottom-2 right-2 h-[136px] w-[110px] origin-bottom" style={{ transform: `scale(${scale})` }}>
      <PlayerAvatar appearance={appearance} number={number} className="h-full w-full" background={false} />
    </div>
  );
}

function Info({ kicker, title, rating, ratingTone = "text-ink-chalk", children }: {
  kicker: string; title: string; rating: number; ratingTone?: string; children: ReactNode;
}) {
  return (
    <div className="relative mt-auto flex flex-col gap-1.5 py-3 pl-4 pr-[118px]">
      <div>
        <p className="truncate text-micro uppercase tracking-wider text-path">{kicker}</p>
        <div className="flex items-baseline gap-2">
          <p className="truncate font-display text-lg font-bold leading-tight text-ink-chalk">{title}</p>
          <p className={`font-display text-2xl font-bold leading-none ${ratingTone}`}>{rating}</p>
        </div>
      </div>
      {children}
    </div>
  );
}
