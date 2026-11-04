/** «Матч 3D» on the screen: the landscape box (a real rotation when the phone
 * can do it, a CSS one when it can't), the loading, the controls and the HUD
 * over the canvas, the final whistle. */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { enterImmersive } from "@/lib/immersive";
import { preloadFreeKickSfx } from "@/lib/freeKick3d/sfx";
import { HALF_L, HALF_W } from "@/lib/match3d/core";

import { loadMatchAssets } from "./assets";
import Controls from "./Controls";
import { MatchGame, type GameEnd, type Hud } from "./game";

const SETUP = { home: "Твой клуб", away: "Гранит", homeRating: 0.78, awayRating: 0.76 };

type Box = { w: number; h: number; rotated: boolean };

const measure = (): Box => {
  const vw = window.innerWidth, vh = window.innerHeight;
  return vh > vw ? { w: vh, h: vw, rotated: true } : { w: vw, h: vh, rotated: false };
};

/** A touch in the box's own axes: rotated 90° clockwise, its x runs down the screen. */
const toBox = (box: Box, x: number, y: number) => (box.rotated ? { x: y, y: window.innerWidth - x } : { x, y: y });

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

export default function Match3DGame({ onExit, demo = false, onGame }: { onExit: () => void; demo?: boolean; onGame?: (g: MatchGame) => void }) {
  const [box, setBox] = useState<Box>(measure);
  const [stage, setStage] = useState<"intro" | "loading" | "play" | "end">(demo ? "loading" : "intro");
  const [share, setShare] = useState(0);
  const [failed, setFailed] = useState(false);
  const [game, setGame] = useState<MatchGame | null>(null);
  const [hud, setHud] = useState<Hud | null>(null);
  const [message, setMessage] = useState<{ text: string; big: boolean; id: number } | null>(null);
  const [paused, setPaused] = useState(false);
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
      onGame?.(g);
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

  const pause = (v: boolean) => {
    setPaused(v);
    if (game) game.paused = v;
  };
  const live = stage === "play" && hud && !hud.replay && !hud.ended;

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
            <Controls game={game!} hud={hud!} w={box.w} h={box.h} toBox={(x, y) => toBox(box, x, y)} />
            <button type="button" onClick={() => pause(true)} aria-label="Пауза" style={{ position: "absolute", left: 8, top: 6, width: 34, height: 30, borderRadius: 8, border: 0, background: "rgba(10,20,34,.6)", color: "#fff", fontSize: 13, fontWeight: 800 }}>II</button>
          </>
        )}

        {stage === "intro" && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", padding: 16, background: "radial-gradient(circle at 50% 40%, #173a5e, #07121f)" }}>
            <div style={{ maxWidth: 420, textAlign: "center" }}>
              <div style={{ fontSize: 13, opacity: 0.7 }}>{SETUP.home} — {SETUP.away}, 0 : 0, 80-я минута</div>
              <div style={{ fontSize: 24, fontWeight: 900, margin: "6px 0" }}>Забей и выиграй</div>
              <div style={{ fontSize: 13, opacity: 0.85, lineHeight: 1.4 }}>
                Управление как в «Ответке»: слева бег, у края круга спринт. Удар: нажми, держи для силы, свайп вверх для закрутки, вбок для финта.
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
        {paused && (
          <div style={{ position: "absolute", inset: 0, background: "rgba(5,14,26,.66)", display: "flex", alignItems: "center", justifyContent: "center", gap: 10 }}>
            <button type="button" onClick={onExit} style={{ padding: "12px 22px", borderRadius: 10, border: 0, background: "rgba(255,255,255,.14)", color: "#fff", fontWeight: 700 }}>Выйти из матча</button>
            <button type="button" onClick={() => pause(false)} style={{ padding: "12px 26px", borderRadius: 10, border: 0, background: "#d6ff3f", color: "#0c1a10", fontWeight: 800 }}>Продолжить</button>
          </div>
        )}
        {stage === "end" && end && <Final end={end} onAgain={again} onExit={onExit} />}
      </div>
    </div>
  );
}
