/** «Матч 3D» on the screen: the landscape box (a real rotation when the phone
 * can do it, a CSS one when it can't), the loading, the controls and the HUD
 * over the canvas, the final whistle. */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { haptic } from "@/lib/telegram";
import { enterImmersive } from "@/lib/immersive";
import { preloadFreeKickSfx } from "@/lib/freeKick3d/sfx";
import { HALF_L, HALF_W, Phase } from "@/lib/match3d/core";
import type { Press } from "@/lib/match3d/engine";

import { loadMatchAssets } from "./assets";
import { MatchGame, type GameEnd, type Hud } from "./game";

const SETUP = { home: "Твой клуб", away: "Гранит", homeRating: 0.78, awayRating: 0.76 };

type Box = { w: number; h: number; rotated: boolean };

const measure = (): Box => {
  const vw = window.innerWidth, vh = window.innerHeight;
  return vh > vw ? { w: vh, h: vw, rotated: true } : { w: vw, h: vh, rotated: false };
};

/** A touch in the box's own axes: rotated 90° clockwise, its x runs down the screen. */
const toBox = (box: Box, x: number, y: number) => (box.rotated ? { x: y, y: window.innerWidth - x } : { x, y: y });

const STICK_R = 54;
const FULL_POWER_S = 0.8;
const CURL_PX = 70;

type ChargeKind = "shot" | "pass" | "through" | "lob";

function Stick({ game, box }: { game: MatchGame | null; box: Box }) {
  const pad = useRef<{ id: number; x: number; y: number } | null>(null);
  const [view, setView] = useState<{ x: number; y: number; dx: number; dy: number } | null>(null);
  const set = (x: number, y: number) => {
    if (game) { game.stick.x = x; game.stick.y = y; }
  };
  return (
    <div
      style={{ position: "absolute", left: 0, top: 44, bottom: 0, width: "44%", touchAction: "none" }}
      onPointerDown={(e) => {
        (e.target as Element).setPointerCapture?.(e.pointerId);
        const p = toBox(box, e.clientX, e.clientY);
        pad.current = { id: e.pointerId, ...p };
        setView({ ...p, dx: 0, dy: 0 });
      }}
      onPointerMove={(e) => {
        const c = pad.current;
        if (!c || c.id !== e.pointerId) return;
        const p = toBox(box, e.clientX, e.clientY);
        let dx = p.x - c.x, dy = p.y - c.y;
        const l = Math.sqrt(dx * dx + dy * dy);
        if (l > STICK_R) {
          // The stick's base follows the thumb.
          c.x += (dx / l) * (l - STICK_R);
          c.y += (dy / l) * (l - STICK_R);
          dx = p.x - c.x; dy = p.y - c.y;
        }
        const k = l < 8 ? 0 : 1 / STICK_R;
        set(dx * k, -dy * k);
        setView({ x: c.x, y: c.y, dx, dy });
      }}
      onPointerUp={() => { pad.current = null; set(0, 0); setView(null); }}
      onPointerCancel={() => { pad.current = null; set(0, 0); setView(null); }}
    >
      {view ? (
        <>
          <div style={{ position: "fixed", left: 0, top: 0, width: STICK_R * 2, height: STICK_R * 2, marginLeft: view.x - STICK_R, marginTop: view.y - STICK_R, borderRadius: "50%", border: "2px solid rgba(255,255,255,.45)", background: "rgba(0,0,0,.18)", pointerEvents: "none" }} />
          <div style={{ position: "fixed", left: 0, top: 0, width: 46, height: 46, marginLeft: view.x + view.dx - 23, marginTop: view.y + view.dy - 23, borderRadius: "50%", background: "rgba(255,255,255,.6)", pointerEvents: "none" }} />
        </>
      ) : (
        <div style={{ position: "absolute", left: 34, bottom: 26, width: 96, height: 96, borderRadius: "50%", border: "2px dashed rgba(255,255,255,.28)", pointerEvents: "none" }} />
      )}
    </div>
  );
}

const btnStyle = (size: number, x: number, y: number, tone: string): React.CSSProperties => ({
  position: "absolute", right: x, bottom: y, width: size, height: size, borderRadius: "50%", border: "2px solid rgba(255,255,255,.55)",
  background: tone, color: "#fff", fontSize: size > 66 ? 13 : 11, fontWeight: 800, letterSpacing: 0.2,
  touchAction: "none", userSelect: "none", WebkitUserSelect: "none", display: "flex", alignItems: "center", justifyContent: "center",
  textShadow: "0 1px 2px rgba(0,0,0,.6)", padding: 0,
});

function Charge({ game, box, kind, label, size, x, y, tone, onPower }: { game: MatchGame | null; box: Box; kind: ChargeKind; label: string; size: number; x: number; y: number; tone: string; onPower: (p: number) => void }) {
  const hold = useRef<{ t: number; x: number; y: number; id: number; raf: number; curl: number; chip: boolean } | null>(null);
  const release = () => {
    const h = hold.current;
    if (!h) return;
    hold.current = null;
    cancelAnimationFrame(h.raf);
    const power = Math.min(1, (performance.now() - h.t) / 1000 / FULL_POWER_S);
    onPower(0);
    if (kind === "shot") game?.act({ k: "shot", power: 0.25 + power * 0.75, curl: h.curl, chip: h.chip });
    else game?.act({ k: kind, power });
    haptic("light");
  };
  return (
    <button
      type="button"
      style={btnStyle(size, x, y, tone)}
      onPointerDown={(e) => {
        (e.target as Element).setPointerCapture?.(e.pointerId);
        const p = toBox(box, e.clientX, e.clientY);
        const h = { t: performance.now(), ...p, id: e.pointerId, raf: 0, curl: 0, chip: false };
        hold.current = h;
        const tick = () => {
          const now = (performance.now() - h.t) / 1000 / FULL_POWER_S;
          onPower(Math.min(1, now));
          if (now >= 1.15) { release(); return; }
          h.raf = requestAnimationFrame(tick);
        };
        tick();
      }}
      onPointerMove={(e) => {
        const h = hold.current;
        if (!h || kind !== "shot") return;
        const p = toBox(box, e.clientX, e.clientY);
        h.curl = Math.max(-1, Math.min(1, (p.x - h.x) / CURL_PX));
        h.chip = p.y - h.y < -46;
      }}
      onPointerUp={release}
      onPointerCancel={release}
    >
      {label}
    </button>
  );
}

function Tap({ game, press, label, size, x, y, tone }: { game: MatchGame | null; press: Press; label: string; size: number; x: number; y: number; tone: string }) {
  return (
    <button type="button" style={btnStyle(size, x, y, tone)} onPointerDown={() => { game?.act(press); haptic("light"); }}>{label}</button>
  );
}

function Hold({ label, size, x, y, tone, on }: { label: string; size: number; x: number; y: number; tone: string; on: (v: boolean) => void }) {
  return (
    <button type="button" style={btnStyle(size, x, y, tone)}
      onPointerDown={(e) => { (e.target as Element).setPointerCapture?.(e.pointerId); on(true); }}
      onPointerUp={() => on(false)} onPointerCancel={() => on(false)}>
      {label}
    </button>
  );
}

function Radar({ game }: { game: MatchGame | null }) {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    if (!game) return undefined;
    const c = ref.current!;
    const g = c.getContext("2d")!;
    const W = c.width, H = c.height;
    const draw = () => {
      const s = game.s;
      g.clearRect(0, 0, W, H);
      g.fillStyle = "rgba(10,40,22,.55)";
      g.fillRect(0, 0, W, H);
      g.strokeStyle = "rgba(255,255,255,.5)";
      g.lineWidth = 1;
      g.strokeRect(0.5, 0.5, W - 1, H - 1);
      g.beginPath(); g.moveTo(W / 2, 0); g.lineTo(W / 2, H); g.stroke();
      const X = (x: number) => ((x + HALF_L) / (HALF_L * 2)) * W, Z = (z: number) => ((z + HALF_W) / (HALF_W * 2)) * H;
      for (const p of s.players) {
        g.fillStyle = p.i === s.user ? "#d6ff3f" : p.team === 0 ? "#ff4d5a" : "#ffffff";
        g.beginPath();
        g.arc(X(p.x), Z(p.z), p.i === s.user ? 3.6 : 2.6, 0, Math.PI * 2);
        g.fill();
      }
      g.fillStyle = "#ffd21f";
      g.fillRect(X(s.ball.x) - 2, Z(s.ball.z) - 2, 4, 4);
    };
    const t = setInterval(draw, 120);
    return () => clearInterval(t);
  }, [game]);
  return <canvas ref={ref} width={168} height={108} style={{ position: "absolute", left: "50%", bottom: 6, width: 112, height: 72, transform: "translateX(-50%)", pointerEvents: "none" }} />;
}

function Final({ end, onAgain, onExit }: { end: GameEnd; onAgain: () => void; onExit: () => void }) {
  const t = end.s.teams;
  const won = end.g0 > end.g1, draw = end.g0 === end.g1;
  const row = (name: string, a: string | number, b: string | number) => (
    <div key={name} style={{ display: "flex", justifyContent: "space-between", gap: 24, padding: "3px 0", fontSize: 13 }}>
      <b>{a}</b><span style={{ opacity: 0.75 }}>{name}</span><b>{b}</b>
    </div>
  );
  const poss = t[0].possTicks + t[1].possTicks || 1;
  return (
    <div style={{ position: "absolute", inset: 0, background: "rgba(5,14,26,.72)", display: "flex", alignItems: "center", justifyContent: "center", color: "#fff" }}>
      <div style={{ width: 340, maxWidth: "90%", padding: 16, borderRadius: 16, background: "rgba(12,26,44,.92)", textAlign: "center" }}>
        <div style={{ fontSize: 15, fontWeight: 800, color: won ? "#d6ff3f" : draw ? "#fff" : "#ff8a8a" }}>{won ? "Победа!" : draw ? "Ничья: гола не хватило" : "Поражение"}</div>
        <div style={{ fontSize: 30, fontWeight: 900, margin: "4px 0 8px" }}>{end.g0} : {end.g1}</div>
        {row("Удары", t[0].shots, t[1].shots)}
        {row("В створ", t[0].onTarget, t[1].onTarget)}
        {row("Владение", `${Math.round((t[0].possTicks / poss) * 100)}%`, `${Math.round((t[1].possTicks / poss) * 100)}%`)}
        {row("Точность передач", `${Math.round((t[0].passesOk / (t[0].passes || 1)) * 100)}%`, `${Math.round((t[1].passesOk / (t[1].passes || 1)) * 100)}%`)}
        {row("Угловые", t[0].corners, t[1].corners)}
        <div style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <button type="button" onClick={onExit} style={{ flex: 1, padding: 11, borderRadius: 10, border: 0, background: "rgba(255,255,255,.14)", color: "#fff", fontWeight: 700 }}>Выйти</button>
          <button type="button" onClick={onAgain} style={{ flex: 1, padding: 11, borderRadius: 10, border: 0, background: "#d6ff3f", color: "#0c1a10", fontWeight: 800 }}>Ещё матч</button>
        </div>
      </div>
    </div>
  );
}

export default function Match3DGame({ onExit, demo = false }: { onExit: () => void; demo?: boolean }) {
  const [box, setBox] = useState<Box>(measure);
  const [stage, setStage] = useState<"intro" | "loading" | "play" | "end">(demo ? "loading" : "intro");
  const [share, setShare] = useState(0);
  const [failed, setFailed] = useState(false);
  const [game, setGame] = useState<MatchGame | null>(null);
  const [hud, setHud] = useState<Hud | null>(null);
  const [message, setMessage] = useState<{ text: string; big: boolean; id: number } | null>(null);
  const [power, setPower] = useState(0);
  const [end, setEnd] = useState<GameEnd | null>(null);
  const [seed, setSeed] = useState(() => (Date.now() >>> 3) & 0xffffff);
  const canvas = useRef<HTMLCanvasElement>(null);
  const leave = useRef<() => void>(() => {});
  const gameRef = useRef<MatchGame | null>(null);

  useEffect(() => {
    const on = () => setBox(measure());
    window.addEventListener("resize", on);
    window.addEventListener("orientationchange", on);
    return () => { window.removeEventListener("resize", on); window.removeEventListener("orientationchange", on); };
  }, []);
  useLayoutEffect(() => { gameRef.current?.resize(box.w, box.h); }, [box]);

  useEffect(() => {
    if (stage !== "loading") return undefined;
    let gone = false;
    setFailed(false);
    void preloadFreeKickSfx();
    loadMatchAssets(setShare).then((assets) => {
      if (gone) return;
      const g = new MatchGame(canvas.current!, assets, { ...SETUP, seed }, {
        onHud: setHud,
        onMessage: (text, big = false) => setMessage({ text, big, id: performance.now() }),
        onEnd: (e) => { setEnd(e); setStage("end"); },
      }, demo);
      g.resize(box.w, box.h);
      gameRef.current = g;
      (window as unknown as { __m3d: unknown }).__m3d = { g, assets };
      setGame(g);
      setStage("play");
    }).catch(() => { if (!gone) setFailed(true); });
    return () => { gone = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once per match
  }, [stage === "loading", seed]);

  useEffect(() => () => { gameRef.current?.dispose(); gameRef.current = null; leave.current(); }, []);

  useEffect(() => {
    if (!message) return undefined;
    const t = setTimeout(() => setMessage(null), message.big ? 3200 : 1700);
    return () => clearTimeout(t);
  }, [message]);

  // Keys, for a computer.
  useEffect(() => {
    if (!game) return undefined;
    const held = new Set<string>();
    const axes = () => {
      game.stick.x = (held.has("KeyD") || held.has("ArrowRight") ? 1 : 0) - (held.has("KeyA") || held.has("ArrowLeft") ? 1 : 0);
      game.stick.y = (held.has("KeyW") || held.has("ArrowUp") ? 1 : 0) - (held.has("KeyS") || held.has("ArrowDown") ? 1 : 0);
      game.sprint = held.has("ShiftLeft") || held.has("Space");
    };
    const down = (e: KeyboardEvent) => {
      held.add(e.code);
      axes();
      if (e.repeat) return;
      if (e.code === "KeyJ") game.act({ k: "shot", power: 0.75, curl: 0, chip: false });
      if (e.code === "KeyK") game.act({ k: "pass", power: 0.4 });
      if (e.code === "KeyL") game.act({ k: "through", power: 0.5 });
      if (e.code === "KeyI") game.act({ k: "lob", power: 0.6 });
      if (e.code === "KeyU") game.act({ k: "feint" });
      if (e.code === "KeyH") game.act({ k: "tackle" });
      if (e.code === "KeyG") game.act({ k: "slide" });
      if (e.code === "KeyQ") game.act({ k: "switch" });
    };
    const up = (e: KeyboardEvent) => { held.delete(e.code); axes(); };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => { window.removeEventListener("keydown", down); window.removeEventListener("keyup", up); };
  }, [game]);

  const start = useCallback(() => {
    leave.current = enterImmersive();
    setStage("loading");
  }, []);
  const again = () => {
    gameRef.current?.dispose();
    gameRef.current = null;
    setGame(null);
    setHud(null);
    setEnd(null);
    setSeed((s) => s + 1);
    setStage("loading");
  };

  const setSprint = (v: boolean) => { if (game) game.sprint = v; };
  const setContain = (v: boolean) => { if (game) game.contain = v; };
  const live = stage === "play" && hud && !hud.replay && game?.s.phase !== Phase.FullTime;
  const attack = hud?.attack ?? false;
  const blue = "rgba(30,120,230,.62)", green = "rgba(30,160,90,.62)", red = "rgba(220,50,60,.66)", grey = "rgba(20,30,44,.55)";

  return (
    <div style={{ position: "fixed", inset: 0, background: "#07121f", overflow: "hidden", zIndex: 60 }}>
      <div style={{
        position: "absolute", left: 0, top: 0, width: box.w, height: box.h, overflow: "hidden",
        transformOrigin: "0 0", transform: box.rotated ? `translateX(${box.h}px) rotate(90deg)` : undefined,
        font: "13px system-ui, -apple-system, sans-serif", color: "#fff", userSelect: "none", WebkitUserSelect: "none",
      }}>
        <canvas ref={canvas} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", display: "block", touchAction: "none" }} />

        {hud && (
          <div style={{ position: "absolute", top: 6, left: "50%", transform: "translateX(-50%)", display: "flex", alignItems: "center", gap: 0, borderRadius: 7, overflow: "hidden", fontWeight: 800, fontSize: 13, pointerEvents: "none", boxShadow: "0 1px 6px rgba(0,0,0,.4)" }}>
            <span style={{ padding: "4px 9px", background: "#c61c2b" }}>{SETUP.home}</span>
            <span style={{ padding: "4px 10px", background: "#0c1a2c", fontVariantNumeric: "tabular-nums" }}>{hud.g0} : {hud.g1}</span>
            <span style={{ padding: "4px 9px", background: "#1c3f94" }}>{SETUP.away}</span>
            <span style={{ padding: "4px 9px", background: "rgba(12,26,44,.82)", fontVariantNumeric: "tabular-nums", fontWeight: 700 }}>{hud.clock}</span>
          </div>
        )}
        {hud?.replay && <div style={{ position: "absolute", top: 10, left: 14, padding: "3px 9px", borderRadius: 5, background: "#c61c2b", fontWeight: 800, letterSpacing: 1, fontSize: 12 }}>ПОВТОР</div>}
        {message && !hud?.replay && (
          <div key={message.id} style={{ position: "absolute", top: message.big ? "30%" : 40, left: "50%", transform: "translateX(-50%)", padding: message.big ? "8px 22px" : "4px 12px", borderRadius: 8, background: message.big ? "rgba(198,28,43,.86)" : "rgba(10,20,34,.62)", fontWeight: message.big ? 900 : 600, fontSize: message.big ? 26 : 13, whiteSpace: "nowrap", pointerEvents: "none" }}>
            {message.text}
          </div>
        )}
        {hud?.replay && (
          <button type="button" onClick={() => game?.skipReplay()} style={{ position: "absolute", inset: 0, background: "transparent", border: 0 }} aria-label="Пропустить повтор" />
        )}

        {live && !demo && (
          <>
            <Radar game={game} />
            <Stick game={game} box={box} />
            {power > 0 && (
              <div style={{ position: "absolute", right: 150, bottom: 136, width: 120, height: 9, borderRadius: 5, background: "rgba(0,0,0,.45)", overflow: "hidden", pointerEvents: "none" }}>
                <div style={{ width: `${power * 100}%`, height: "100%", background: power > 0.85 ? "#ff5a4d" : "#d6ff3f" }} />
              </div>
            )}
            {attack ? (
              <>
                <Charge game={game} box={box} kind="shot" label="Удар" size={78} x={16} y={14} tone={red} onPower={setPower} />
                <Charge game={game} box={box} kind="pass" label="Пас" size={66} x={102} y={10} tone={green} onPower={setPower} />
                <Charge game={game} box={box} kind="through" label="Разрез" size={60} x={96} y={84} tone={blue} onPower={setPower} />
                <Charge game={game} box={box} kind="lob" label="Навес" size={60} x={22} y={102} tone={blue} onPower={setPower} />
                <Tap game={game} press={{ k: "feint" }} label="Финт" size={54} x={176} y={64} tone={grey} />
                <Hold label="Спринт" size={58} x={174} y={4} tone={grey} on={setSprint} />
              </>
            ) : (
              <>
                <Tap game={game} press={{ k: "slide" }} label="Подкат" size={74} x={16} y={14} tone={red} />
                <Tap game={game} press={{ k: "tackle" }} label="Отбор" size={66} x={100} y={10} tone={green} />
                <Tap game={game} press={{ k: "switch" }} label="Смена" size={60} x={22} y={98} tone={blue} />
                <Hold label="Прессинг" size={60} x={96} y={84} tone={blue} on={setContain} />
                <Hold label="Спринт" size={58} x={174} y={4} tone={grey} on={setSprint} />
              </>
            )}
          </>
        )}

        {stage === "intro" && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", padding: 16, background: "radial-gradient(circle at 50% 40%, #173a5e, #07121f)" }}>
            <div style={{ maxWidth: 420, textAlign: "center" }}>
              <div style={{ fontSize: 13, opacity: 0.7 }}>{SETUP.home} — {SETUP.away}, 0 : 0, 80-я минута</div>
              <div style={{ fontSize: 24, fontWeight: 900, margin: "6px 0" }}>Забей и выиграй</div>
              <div style={{ fontSize: 13, opacity: 0.85, lineHeight: 1.4 }}>
                Слева ведёшь игрока, справа кнопки. Удар и передачи: держи — сильнее, веди по кнопке вбок — закрутка, вверх — парашют.
              </div>
              <div style={{ display: "flex", gap: 8, justifyContent: "center", marginTop: 14 }}>
                <button type="button" onClick={onExit} style={{ padding: "11px 18px", borderRadius: 10, border: 0, background: "rgba(255,255,255,.14)", color: "#fff", fontWeight: 700 }}>Назад</button>
                <button type="button" onClick={start} style={{ padding: "11px 26px", borderRadius: 10, border: 0, background: "#d6ff3f", color: "#0c1a10", fontWeight: 800 }}>Начать матч</button>
              </div>
            </div>
          </div>
        )}
        {stage === "loading" && (
          <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, background: "#07121f" }}>
            {failed ? (
              <>
                <div>Не удалось загрузить матч</div>
                <button type="button" onClick={() => { setFailed(false); setSeed((s) => s + 1); }} style={{ padding: "9px 18px", borderRadius: 10, border: 0, background: "#d6ff3f", color: "#0c1a10", fontWeight: 800 }}>Ещё раз</button>
              </>
            ) : (
              <>
                <div>Выходим на поле…</div>
                <div style={{ width: 200, height: 6, borderRadius: 4, background: "rgba(255,255,255,.14)", overflow: "hidden" }}>
                  <div style={{ width: `${Math.round(share * 100)}%`, height: "100%", background: "#d6ff3f" }} />
                </div>
              </>
            )}
          </div>
        )}
        {stage === "end" && end && <Final end={end} onAgain={again} onExit={onExit} />}
      </div>
    </div>
  );
}
