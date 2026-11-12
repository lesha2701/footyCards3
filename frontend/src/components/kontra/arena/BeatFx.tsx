import { motion } from "framer-motion";
import { memo } from "react";

import { staticUrl } from "@/lib/api";
import type { KontraEvent, KontraUnit } from "@/types";

import { type Beat, type BeatPlan, fxOf, type Spot } from "./battleScript";

interface Props {
  beat: Beat;
  plan: BeatPlan;
  speed: number;
  units: KontraUnit[];
  spots: Record<string, Spot>;
  size: { w: number; h: number };
}

const s = (ms: number, speed: number) => ms / 1000 / speed;
const SPARKS = Array.from({ length: 9 }, (_, i) => (i / 9) * Math.PI * 2);

/** Everything one beat draws over the pitch: the ability banner, the
 *  leader's ultimate cut-in, balls in flight, bursts, damage numbers,
 *  dashes, rings and sweeps. Keyed by the beat — it plays once and goes. */
function BeatFx({ beat, plan, speed, units, spots, size }: Props) {
  const fx = fxOf(beat.ability);
  const byId = new Map(units.map((u) => [u.id, u]));
  const actor = beat.actor ? byId.get(beat.actor) : undefined;
  const px = (id?: string) => {
    const p = id ? spots[id] : undefined;
    return p ? { x: (p.x / 100) * size.w, y: (p.y / 100) * size.h - (byId.get(id!)?.role === "boss" ? 0 : size.h * 0.02) } : null;
  };
  const from = px(beat.actor);
  const showBanner = beat.kind === "action" && beat.ability !== "strike";
  const teamOf = (side?: string) => units.filter((u) => u.side === side).map((u) => u.id);

  return (
    <div className="pointer-events-none absolute inset-0 z-[200] overflow-hidden">
      {/* ultimate cut-in */}
      {beat.ult && actor && (
        <motion.div
          className="absolute inset-0 flex items-center"
          initial={{ opacity: 0 }}
          animate={{ opacity: [0, 1, 1, 0] }}
          transition={{ duration: s(plan.intro + 150, speed), times: [0, 0.12, 0.82, 1] }}
        >
          <div className="absolute inset-0 bg-black/60" />
          <motion.div
            className="absolute inset-x-[-10%] top-1/2 h-[34%] -translate-y-1/2 -skew-y-6"
            style={{ background: `linear-gradient(90deg, transparent, ${fx.color}cc 30%, ${fx.color} 50%, ${fx.color}cc 70%, transparent)` }}
            initial={{ x: "-100%" }} animate={{ x: "0%" }} transition={{ duration: s(260, speed), ease: "easeOut" }}
          />
          {actor.card?.image_path && (
            <motion.img
              src={staticUrl(actor.card.image_path)} alt=""
              className="absolute left-[6%] top-1/2 h-[44%] -translate-y-1/2 rounded-2xl object-cover shadow-2xl ring-4 ring-white"
              style={{ aspectRatio: "3 / 4" }}
              initial={{ x: -220, rotate: -12 }} animate={{ x: 0, rotate: -4 }}
              transition={{ delay: s(120, speed), type: "spring", stiffness: 220, damping: 18 }}
            />
          )}
          <motion.div
            className="absolute right-[5%] top-1/2 w-[55%] -translate-y-1/2 text-right"
            initial={{ x: 240, opacity: 0 }} animate={{ x: 0, opacity: 1 }}
            transition={{ delay: s(220, speed), type: "spring", stiffness: 240, damping: 20 }}
          >
            <p className="font-display text-[11px] font-black uppercase tracking-[0.3em] text-white/85">Суперудар лидера</p>
            <p className="font-display text-2xl font-black leading-none text-white drop-shadow-[0_3px_0_rgba(0,0,0,0.5)]">
              {fx.icon} {beat.name}
            </p>
          </motion.div>
        </motion.div>
      )}

      {/* ability banner */}
      {showBanner && !beat.ult && (
        <motion.div
          className="absolute left-1/2 top-[44%] -translate-x-1/2 -translate-y-1/2"
          initial={{ opacity: 0, scale: 0.6 }}
          animate={{ opacity: [0, 1, 1, 0], scale: [0.6, 1.08, 1, 0.95] }}
          transition={{ duration: s(900, speed), times: [0, 0.15, 0.8, 1] }}
        >
          <div className="flex items-center gap-1.5 whitespace-nowrap rounded-full bg-black/75 px-3 py-1.5 font-display text-sm font-black text-white shadow-xl"
            style={{ boxShadow: `0 0 0 2px ${fx.color}, 0 0 22px ${fx.color}88` }}>
            <span className="text-base">{fx.icon}</span>
            <span>{beat.name}</span>
          </div>
        </motion.div>
      )}

      {/* the actor's move: a dash, a flip, a wind-up */}
      {from && beat.kind === "action" && <ActorGhost beat={beat} plan={plan} speed={speed} from={from} spotW={size.w * ((spots[beat.actor!]?.w ?? 15) / 100)} px={px} />}

      {/* team-wide sweeps */}
      {fx.style === "offside" && (
        <motion.div className="absolute inset-x-0 h-1 bg-yellow-300 shadow-[0_0_14px_#fde047]"
          style={{ top: `${(spots[teamOf(actor?.side === "me" ? "foe" : "me")[0]]?.y ?? 25) + 7}%` }}
          initial={{ scaleX: 0, originX: 0 }} animate={{ scaleX: [0, 1, 1], opacity: [1, 1, 0] }}
          transition={{ delay: s(plan.intro + 300, speed), duration: s(700, speed) }}>
          <span className="absolute -top-6 right-1 text-xl">🚩</span>
        </motion.div>
      )}
      {fx.style === "slam" && from && (
        <motion.div className="absolute rounded-[50%] border-4 border-red-500/80 bg-red-500/10"
          style={{ left: from.x, top: from.y, width: 40, height: 20, x: "-50%", y: "-50%" }}
          initial={{ scale: 0.2, opacity: 1 }} animate={{ scale: [0.2, 14], opacity: [1, 0] }}
          transition={{ delay: s(plan.intro + 150, speed), duration: s(520, speed), ease: "easeOut" }} />
      )}
      {fx.style === "chant" && from && [0, 1, 2].map((i) => (
        <motion.div key={i} className="absolute rounded-full border-2 border-rose-400/80"
          style={{ left: from.x, top: from.y, width: 60, height: 60, x: "-50%", y: "-50%" }}
          initial={{ scale: 0.3, opacity: 0.9 }} animate={{ scale: 6, opacity: 0 }}
          transition={{ delay: s(plan.intro + 120 + i * 150, speed), duration: s(700, speed) }} />
      ))}

      {/* projectiles */}
      {plan.impacts.filter((i) => i.launch !== undefined).map((imp, k) => {
        const to = px(imp.event.target);
        if (!from || !to) return null;
        return <Projectile key={k} style={fx.style} color={fx.color} from={from} to={to}
          launch={imp.launch!} at={imp.at} speed={speed} miss={imp.event.kind === "miss"} />;
      })}

      {/* landings */}
      {plan.impacts.map((imp, k) => {
        const e = imp.event;
        const ids = e.target === "team" ? teamOf(actor?.side) : e.target === "foes" ? teamOf(actor?.side === "me" ? "foe" : "me") : e.target ? [e.target] : [];
        return ids.map((id) => {
          const p = px(id);
          if (!p) return null;
          return <Landing key={`${k}-${id}`} e={e} at={imp.at} speed={speed} x={p.x} y={p.y} color={fx.color} icon={fx.icon} boss={byId.get(id)?.role === "boss"} />;
        });
      })}

      {/* screen flash on a crit or an ultimate */}
      {plan.impacts.some((i) => i.event.crit) || beat.ult ? (
        <motion.div className="absolute inset-0 bg-white" initial={{ opacity: 0 }}
          animate={{ opacity: [0, 0.35, 0] }}
          transition={{ delay: s((plan.impacts.find((i) => i.event.kind === "hit")?.at ?? plan.intro), speed), duration: s(260, speed) }} />
      ) : null}
    </div>
  );
}

function ActorGhost({ beat, plan, speed, from, spotW, px }: {
  beat: Beat; plan: BeatPlan; speed: number; from: { x: number; y: number }; spotW: number;
  px: (id?: string) => { x: number; y: number } | null;
}) {
  const fx = fxOf(beat.ability);
  const first = plan.impacts.find((i) => i.event.kind === "hit" || i.event.kind === "miss");
  const to = first ? px(first.event.target) : null;
  const start = plan.intro + (beat.ability === "strike" ? 160 : 420);
  // A glowing aura on the actor while it winds up.
  return (
    <>
      <motion.div className="absolute rounded-full"
        style={{ left: from.x, top: from.y, width: spotW * 1.5, height: spotW * 1.5, x: "-50%", y: "-50%", background: `radial-gradient(circle, ${fx.color}88, transparent 65%)` }}
        initial={{ opacity: 0, scale: 0.5 }} animate={{ opacity: [0, 1, 0], scale: [0.5, 1.15, 1.3] }}
        transition={{ delay: s(plan.intro, speed), duration: s(start - plan.intro + 260, speed) }} />
      {fx.style === "dash" && to && (
        // the tackler's streak towards the target
        <motion.div className="absolute h-1.5 rounded-full"
          style={{ left: from.x, top: from.y, width: Math.hypot(to.x - from.x, to.y - from.y), originX: 0, rotate: (Math.atan2(to.y - from.y, to.x - from.x) * 180) / Math.PI, background: `linear-gradient(90deg, transparent, ${fx.color})` }}
          initial={{ scaleX: 0, opacity: 0 }} animate={{ scaleX: [0, 1, 1], opacity: [0, 1, 0] }}
          transition={{ delay: s(start, speed), duration: s(420, speed) }} />
      )}
      {fx.style === "flip" && (
        <motion.div className="absolute text-3xl" style={{ left: from.x, top: from.y - spotW * 0.9, x: "-50%", y: "-50%" }}
          initial={{ rotate: 0, opacity: 0 }} animate={{ rotate: 360, opacity: [0, 1, 0] }}
          transition={{ delay: s(plan.intro + 300, speed), duration: s(420, speed) }}>🤸</motion.div>
      )}
    </>
  );
}

function Projectile({ style, color, from, to, launch, at, speed, miss }: {
  style: string; color: string; from: { x: number; y: number }; to: { x: number; y: number };
  launch: number; at: number; speed: number; miss: boolean;
}) {
  const arc = style === "lob" ? 130 : style === "pierce" ? 0 : style === "card" ? 30 : 46;
  const end = miss ? { x: to.x + (to.x > from.x ? 60 : -60), y: to.y - 40 } : to;
  const midX = (from.x + end.x) / 2;
  const midY = Math.min(from.y, end.y) + (Math.abs(end.y - from.y) / 2) - arc;
  const dur = s(at - launch, speed);
  const big = style === "pierce";
  const body = style === "card"
    ? <span className="block h-9 w-6 rounded-[3px] bg-red-600 shadow-[0_0_16px_rgba(239,68,68,0.9)] ring-1 ring-white/60" />
    : big
      ? <span className="block h-9 w-9 rounded-full bg-[radial-gradient(circle_at_35%_35%,#fff,#fde047_25%,#f97316_55%,#dc2626)] shadow-[0_0_30px_10px_rgba(249,115,22,0.75)]" />
      : <span className="block text-[20px] leading-none drop-shadow-[0_2px_3px_rgba(0,0,0,0.6)]">⚽</span>;
  const trail = [0.06, 0.12, 0.18];
  return (
    <>
      {trail.map((lag, i) => (
        <motion.div key={i} className="absolute rounded-full"
          style={{ left: 0, top: 0, width: big ? 26 - i * 6 : 12 - i * 3, height: big ? 26 - i * 6 : 12 - i * 3, background: color, filter: "blur(2px)" }}
          initial={{ x: from.x, y: from.y, opacity: 0 }}
          animate={{ x: [from.x, midX, end.x], y: [from.y, midY, end.y], opacity: [0, 0.55 - i * 0.15, 0] }}
          transition={{ delay: s(launch, speed) + lag / speed, duration: dur, ease: "linear", times: [0, 0.5, 1] }} />
      ))}
      <motion.div className="absolute left-0 top-0 -ml-3 -mt-3"
        initial={{ x: from.x, y: from.y, opacity: 0, rotate: 0, scale: 0.7 }}
        animate={{ x: [from.x, midX, end.x], y: [from.y, midY, end.y], opacity: [1, 1, miss ? 0 : 1, 0], rotate: style === "card" ? 540 : 720, scale: [0.7, style === "lob" ? 1.35 : 1.1, 1] }}
        transition={{ delay: s(launch, speed), duration: dur, ease: "linear", times: [0, 0.5, 1], opacity: { times: [0, 0.1, 0.95, 1], duration: dur, delay: s(launch, speed) } }}
      >
        {body}
      </motion.div>
    </>
  );
}

function Landing({ e, at, speed, x, y, color, icon, boss }: {
  e: KontraEvent; at: number; speed: number; x: number; y: number; color: string; icon: string; boss: boolean;
}) {
  const delay = s(at, speed);
  if (e.kind === "hit") {
    const crit = Boolean(e.crit);
    const blocked = !e.damage && Boolean(e.absorbed);
    const tint = blocked ? "#67e8f9" : crit ? "#fde047" : "#ffffff";
    return (
      <>
        <motion.div className="absolute rounded-full"
          style={{ left: x, top: y, width: boss ? 90 : 46, height: boss ? 90 : 46, x: "-50%", y: "-50%", border: `3px solid ${tint}`, boxShadow: `0 0 18px ${tint}` }}
          initial={{ scale: 0.2, opacity: 0 }} animate={{ scale: [0.2, crit ? 2 : 1.5], opacity: [1, 0] }}
          transition={{ delay, duration: s(380, speed), ease: "easeOut" }} />
        {SPARKS.map((a, i) => (
          <motion.span key={i} className="absolute h-1.5 w-1.5 rounded-full"
            style={{ left: x, top: y, background: i % 2 ? tint : color, boxShadow: `0 0 6px ${tint}` }}
            initial={{ x: 0, y: 0, opacity: 0 }}
            animate={{ x: Math.cos(a) * (crit ? 52 : 34), y: Math.sin(a) * (crit ? 52 : 34), opacity: [1, 1, 0] }}
            transition={{ delay, duration: s(420, speed), ease: "easeOut" }} />
        ))}
        <FloatText delay={delay} speed={speed} x={x} y={y} big={crit || boss}
          className={blocked ? "text-cyan-200" : crit ? "text-yellow-300" : "text-white"}>
          {blocked ? `🛡 ${e.absorbed}` : `−${e.damage}`}
          {crit && <span className="ml-1 text-[11px] font-black text-yellow-200">КРИТ</span>}
          {e.edge && <span className="ml-1 text-[11px]">⚔</span>}
        </FloatText>
      </>
    );
  }
  if (e.kind === "miss") {
    return <FloatText delay={delay} speed={speed} x={x} y={y} className="text-yellow-200">🚩 мимо</FloatText>;
  }
  if (e.kind === "heal") {
    return (
      <>
        {[0, 1, 2].map((i) => (
          <motion.span key={i} className="absolute text-sm font-black text-emerald-300"
            style={{ left: x + (i - 1) * 14, top: y }}
            initial={{ y: 0, opacity: 0 }} animate={{ y: -42, opacity: [0, 1, 0] }}
            transition={{ delay: delay + i * 0.08 / speed, duration: s(700, speed) }}>✚</motion.span>
        ))}
        <FloatText delay={delay} speed={speed} x={x} y={y} className="text-emerald-300">+{e.amount}</FloatText>
      </>
    );
  }
  if (e.kind === "tick") {
    return <FloatText delay={delay} speed={speed} x={x} y={y} className="text-rose-300">🩹 −{e.damage}</FloatText>;
  }
  if (e.kind === "down") {
    return <FloatText delay={delay} speed={speed} x={x} y={y - 18} className="text-red-400" big>ВЫБИТ</FloatText>;
  }
  if (e.kind === "stunned") {
    return <FloatText delay={delay} speed={speed} x={x} y={y} className="text-amber-200">💫 пропуск хода</FloatText>;
  }
  if (e.kind === "passive") {
    return <FloatText delay={delay} speed={speed} x={x} y={y - 10} className="text-yellow-300" big>⭐ Звёздный час!</FloatText>;
  }
  if (e.kind === "effect" || e.kind === "meter") {
    const label = e.kind === "meter" ? `⏩ +${e.pct}%` : EFFECT_TEXT[e.effect ?? ""] ?? icon;
    return (
      <>
        <motion.div className="absolute rounded-full"
          style={{ left: x, top: y, width: 50, height: 50, x: "-50%", y: "-50%", border: `2px solid ${color}`, boxShadow: `0 0 14px ${color}` }}
          initial={{ scale: 0.4, opacity: 0 }} animate={{ scale: [0.4, 1.6], opacity: [0.9, 0] }}
          transition={{ delay, duration: s(600, speed) }} />
        <FloatText delay={delay} speed={speed} x={x} y={y - 6} className="text-white">{label}</FloatText>
      </>
    );
  }
  return null;
}

const EFFECT_TEXT: Record<string, string> = {
  stun: "💫 оглушён", yellow: "🟨 жёлтая", slow: "🐢 замедлен", shield: "🛡️ щит", taunt: "📣 на себя",
  blind: "🚩 офсайд", injury: "🩹 травма", haste: "⚡ ускорение", cleanse: "✨ очищен",
};

function FloatText({ children, delay, speed, x, y, className, big = false }: {
  children: React.ReactNode; delay: number; speed: number; x: number; y: number; className: string; big?: boolean;
}) {
  return (
    <motion.div
      className={`absolute whitespace-nowrap font-display font-black ${big ? "text-2xl" : "text-lg"} ${className}`}
      style={{ left: x, top: y, x: "-50%", textShadow: "0 2px 0 rgba(0,0,0,0.85), 0 0 10px rgba(0,0,0,0.6)" }}
      initial={{ y: 0, opacity: 0, scale: 0.6 }}
      animate={{ y: [-4, -30, -44], opacity: [0, 1, 0], scale: [0.6, big ? 1.35 : 1.15, 1] }}
      transition={{ delay, duration: s(950, speed), times: [0, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}

export default memo(BeatFx);
