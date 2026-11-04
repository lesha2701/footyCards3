/** The thumbs of «Матч 3D»: the same hands as «Ответка» (`lib/oneOnOne/gesture`,
 * the layout of `AttackRun`). Left half: a floating stick, its rim is the
 * sprint. Right half: the big button (tap, hold for power, swipe up for the
 * finesse, flick sideways for the feint) with the others on an arc round it,
 * caught by nearness rather than a precise press. */
import { useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from "react";

import { Finger, STICK_SPRINT, Stick } from "@/lib/oneOnOne/gesture";
import { haptic } from "@/lib/telegram";

import type { Hud, MatchGame } from "./game";

/** Maps a touch to the landscape box, whichever way the screen really is. */
export type ToBox = (x: number, y: number) => { x: number; y: number };

const CHARGE_MS = 900;
const TAP_GRACE_MS = 200;
const OVER_POWER = 0.9;
const BUTTON_REACH = 0.65;
const LIME = "#c6e63a";
const BIG = 80;
const SMALL = 52;
/** From the box's bottom right corner to the big button's corner. */
const RIGHT = 20;
const BOTTOM = 36;
/** The arc, as offsets of a small button from the big one's corner. */
const ARC = { top: { left: 7, top: -70 }, side: { left: -70, top: 21 }, mid: { left: -50, top: -40 }, feint: { left: -118, top: -28 } };
/** A drag this long (px) across the big button, mostly sideways, is a feint. */
const FEINT_DRAG = 26;
const FEINT_SLOPE = 1.3;
const DEAD = 0.22;
const BAR_R = 46;
const BAR_LENGTH = 2 * Math.PI * BAR_R;

type Slot = keyof typeof ARC;
type Role = "stick" | "pad" | Slot;
type Held = { role: "pad" | Slot; at: number; feinted: boolean };
/** A quick touch on the stick's side still may mean a man. */
const TAP_MS = 240;
const TAP_MOVE = 14;

const face: CSSProperties = {
  width: "100%", height: "100%", borderRadius: "50%", border: "2px solid rgba(255,255,255,.3)", background: "rgba(0,0,0,.6)", color: "#fff",
  display: "flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: 600, textAlign: "center", lineHeight: 1,
  boxShadow: "0 2px 10px rgba(0,0,0,.5)", textShadow: "0 1px 2px rgba(0,0,0,.9)",
};

function Ring({ barRef }: { barRef: React.RefObject<SVGCircleElement> }) {
  return (
    <svg viewBox="0 0 100 100" style={{ position: "absolute", inset: -6, width: "calc(100% + 12px)", height: "calc(100% + 12px)", transform: "rotate(-90deg)", pointerEvents: "none" }}>
      <circle ref={barRef} cx={50} cy={50} r={BAR_R} fill="none" stroke="#fff" strokeWidth={6} strokeLinecap="round" strokeDasharray={BAR_LENGTH} strokeDashoffset={BAR_LENGTH} />
    </svg>
  );
}

export default function Controls({ game, hud, w, h, toBox }: { game: MatchGame; hud: Hud; w: number; h: number; toBox: ToBox }) {
  const stick = useMemo(() => new Stick(w, h), []); // eslint-disable-line react-hooks/exhaustive-deps -- resized below
  const pad = useMemo(() => new Finger(w, h), []); // eslint-disable-line react-hooks/exhaustive-deps -- resized below
  useEffect(() => { stick.resize(w, h); pad.resize(w, h); }, [stick, pad, w, h]);
  const fingers = useRef(new Map<number, Role>());
  const held = useRef<Held | null>(null);
  const stickDown = useRef({ x: 0, y: 0, t: 0 });
  const padDown = useRef({ x: 0, y: 0 });
  const bigBar = useRef<SVGCircleElement>(null);
  const midBar = useRef<SVGCircleElement>(null);
  const anchor = useRef<HTMLDivElement>(null);
  const knob = useRef<HTMLDivElement>(null);
  const [started, setStarted] = useState(false);
  const attack = hud.attack;
  // Read by the handlers, which outlive a render by a thumb's press.
  const now = useRef(hud);
  now.current = hud;

  const centre = (slot: Slot | "big") => {
    const x0 = w - RIGHT - BIG, y0 = h - BOTTOM - BIG;
    if (slot === "big") return { x: x0 + BIG / 2, y: y0 + BIG / 2 };
    return { x: x0 + ARC[slot].left + SMALL / 2, y: y0 + ARC[slot].top + SMALL / 2 };
  };

  const syncStick = () => {
    const st = stick.read();
    const r = stick.radius;
    const dx = st.knob.x - st.anchor.x, dy = st.knob.y - st.anchor.y;
    const k = Math.sqrt(dx * dx + dy * dy) / r;
    const on = stick.down && k >= DEAD;
    game.stick.x = on ? Math.max(-1, Math.min(1, dx / r)) : 0;
    game.stick.y = on ? Math.max(-1, Math.min(1, -dy / r)) : 0;
    game.sprint = on && k >= STICK_SPRINT;
    if (anchor.current) {
      anchor.current.style.opacity = stick.down ? "1" : "0";
      anchor.current.style.width = anchor.current.style.height = `${r * 2}px`;
      anchor.current.style.transform = `translate(${st.anchor.x - r}px, ${st.anchor.y - r}px)`;
      anchor.current.style.borderColor = game.sprint ? LIME : "rgba(255,255,255,.85)";
    }
    if (knob.current) {
      knob.current.style.opacity = stick.down ? "1" : "0";
      knob.current.style.transform = `translate(${st.knob.x - 20}px, ${st.knob.y - 20}px)`;
    }
  };

  const powerOf = (p: Held, t: number) => Math.min(1, Math.max(0, t - p.at - TAP_GRACE_MS) / CHARGE_MS);
  const drawBars = () => {
    const p = held.current;
    const power = p && !p.feinted ? powerOf(p, performance.now()) : 0;
    for (const [bar, on] of [[bigBar.current, p?.role === "pad"], [midBar.current, p?.role === "mid"]] as const) {
      if (!bar) continue;
      const k = on ? power : 0;
      bar.style.strokeDashoffset = `${BAR_LENGTH * (1 - k)}`;
      bar.style.stroke = k > OVER_POWER ? "#f87171" : "#fff";
    }
    if (p) requestAnimationFrame(drawBars);
  };
  const startHold = (role: Held["role"]) => {
    held.current = { role, at: performance.now(), feinted: false };
    requestAnimationFrame(drawBars);
  };
  const endHold = () => {
    const p = held.current;
    held.current = null;
    drawBars();
    const t = performance.now();
    return { power: p ? powerOf(p, t) : 0, tap: !!p && t - p.at < TAP_GRACE_MS, feinted: !!p?.feinted };
  };

  const onDown = (e: PointerEvent<HTMLDivElement>) => {
    try {
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      // Not every WebView lets a pointer be captured; the controls still work.
    }
    if (!started) setStarted(true);
    const p = toBox(e.clientX, e.clientY);
    const touchMan = () => {
      const m = game.mateAt(p.x, p.y, w, h);
      if (m < 0) return false;
      game.act({ k: "to", i: m });
      haptic("medium");
      return true;
    };
    if (p.x < w / 2) {
      if (stick.down) { touchMan(); return; }
      fingers.current.set(e.pointerId, "stick");
      stick.start(p);
      stickDown.current = { x: p.x, y: p.y, t: e.timeStamp };
      syncStick();
      return;
    }
    const off = (slot: Slot) => {
      const c = centre(slot);
      return Math.sqrt((p.x - c.x) ** 2 + (p.y - c.y) ** 2) / SMALL;
    };
    const fight = now.current.attack;
    const near = ((fight ? ["top", "side", "mid", "feint"] : ["top", "side"]) as Slot[]).reduce((a, b) => (off(b) < off(a) ? b : a));
    const onArc = off(near) < BUTTON_REACH;
    if (onArc) {
      fingers.current.set(e.pointerId, near);
      haptic("light");
      if (fight && near === "top") game.act({ k: "pass", power: 0.4 });
      else if (fight && near === "side") game.act({ k: "through", power: 0.5 });
      else if (fight && near === "feint") game.act({ k: "feint" });
      else if (fight) startHold("mid");
      else if (near === "top") game.act({ k: "switch" });
      else game.act({ k: "slide" });
      return;
    }
    const big = centre("big");
    const onBig = Math.hypot(p.x - big.x, p.y - big.y) < BIG * 0.8;
    if (!onBig && touchMan()) return;
    if (!held.current && !pad.down) {
      fingers.current.set(e.pointerId, "pad");
      pad.start({ ...p, t: e.timeStamp });
      padDown.current = p;
      if (fight) startHold("pad");
      else { game.act({ k: "tackle" }); haptic("light"); }
    }
  };

  const onMove = (e: PointerEvent<HTMLDivElement>) => {
    const role = fingers.current.get(e.pointerId);
    if (!role) return;
    const p = toBox(e.clientX, e.clientY);
    if (role === "stick") {
      stick.move(p);
      syncStick();
    } else if (role === "pad") {
      pad.move({ ...p, t: e.timeStamp });
      const dx = Math.abs(p.x - padDown.current.x), dy = Math.abs(p.y - padDown.current.y);
      if (dx > FEINT_DRAG && dx > dy * FEINT_SLOPE && held.current && !held.current.feinted && now.current.attack) {
        held.current.feinted = true;
        game.act({ k: "feint" });
        haptic("light");
      }
    }
  };

  const onUp = (e: PointerEvent<HTMLDivElement>, cancelled: boolean) => {
    const role = fingers.current.get(e.pointerId);
    fingers.current.delete(e.pointerId);
    const p = toBox(e.clientX, e.clientY);
    if (role === "stick") {
      stick.end();
      syncStick();
      const d = stickDown.current;
      if (!cancelled && e.timeStamp - d.t < TAP_MS && Math.hypot(p.x - d.x, p.y - d.y) < TAP_MOVE) {
        const m = game.mateAt(p.x, p.y, w, h);
        if (m >= 0) { game.act({ k: "to", i: m }); haptic("medium"); }
      }
    } else if (role === "mid") {
      if (!held.current) return;
      const { power, tap } = endHold();
      if (cancelled) return;
      // Near goal, in front of it, the lofted ball is the chip.
      if (now.current.chipHere) game.act({ k: "shot", power: 0.5, curl: 0, chip: true });
      else game.act({ k: "lob", power: tap ? 0.35 : power });
      haptic("light");
    } else if (role === "pad") {
      const hold = endHold();
      if (cancelled) { pad.cancel(); return; }
      const intent = pad.end({ ...p, t: e.timeStamp });
      if (!now.current.attack || hold.feinted) return;
      haptic("medium");
      if (intent.shot) {
        // The finesse: curls the way the thumb bent it.
        const bend = intent.shot.curve / 250 + intent.shot.dx / 1500;
        game.act({ k: "shot", power: 0.6, curl: Math.max(-1, Math.min(1, bend)) || 0.45, chip: false });
      } else if (intent.tap) game.act({ k: "shot", power: 0.5, curl: 0, chip: false });
      else game.act({ k: "shot", power: 0.3 + hold.power * 0.7, curl: 0, chip: false });
    }
  };

  const small = (slot: Slot, label: string, hint?: string, ring?: boolean) => (
    <div style={{ position: "absolute", left: ARC[slot].left, top: ARC[slot].top, width: SMALL, height: SMALL }}>
      {ring && <Ring barRef={midBar} />}
      <div style={{ ...face, ...(hint ? { borderColor: hint } : null) }}>{label}</div>
    </div>
  );

  return (
    <div style={{ position: "absolute", inset: 0, touchAction: "none" }} onPointerDown={onDown} onPointerMove={onMove} onPointerUp={(e) => onUp(e, false)} onPointerCancel={(e) => onUp(e, true)}>
      <div ref={anchor} style={{ position: "absolute", left: 0, top: 0, borderRadius: "50%", border: "3px solid rgba(255,255,255,.85)", background: "rgba(0,0,0,.45)", opacity: 0, pointerEvents: "none", boxSizing: "border-box" }} />
      <div ref={knob} style={{ position: "absolute", left: 0, top: 0, width: 40, height: 40, borderRadius: "50%", background: LIME, border: "2px solid rgba(0,0,0,.5)", opacity: 0, pointerEvents: "none", boxSizing: "border-box" }} />
      <div style={{ position: "absolute", left: 20, bottom: BOTTOM, width: 96, height: 96, borderRadius: "50%", border: "2px solid rgba(255,255,255,.3)", background: "rgba(0,0,0,.45)", display: "flex", alignItems: "center", justifyContent: "center", textAlign: "center", fontSize: 11, fontWeight: 600, color: "#fff", pointerEvents: "none", padding: 6, boxSizing: "border-box" }}>
        {started ? <div style={{ width: 40, height: 40, borderRadius: "50%", background: "rgba(198,230,58,.8)", border: "2px solid rgba(0,0,0,.5)" }} /> : "Бег, у края — спринт"}
      </div>
      <div style={{ position: "absolute", right: RIGHT, bottom: BOTTOM, width: BIG, height: BIG, pointerEvents: "none" }}>
        {attack ? (
          <>
            <Ring barRef={bigBar} />
            <div style={{ ...face, background: LIME, color: "#000", fontSize: 14, fontWeight: 700, border: 0, flexDirection: "column", textShadow: "none" }}>
              {hud.keeper ? "Выбить" : "Удар"}
              {!started && !hud.keeper && <span style={{ fontSize: 9, fontWeight: 500, marginTop: 3, opacity: 0.7 }}>вбок — финт</span>}
            </div>
            {small("top", "Пас")}
            {small("side", "Разрез")}
            {small("mid", hud.chipHere ? "Парашют" : "Навес", "rgba(252,211,77,.8)", true)}
            {small("feint", "Финт")}
          </>
        ) : (
          <>
            <div style={{ ...face, background: LIME, color: "#000", fontSize: 14, fontWeight: 700, border: 0, textShadow: "none" }}>Отбор</div>
            {small("top", "Смена")}
            {small("side", "Подкат")}
          </>
        )}
      </div>
    </div>
  );
}
