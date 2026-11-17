// Tiny synthesized sound effects for «Мяч и Магия» (WebAudio, no files).
// Off by default switch lives in localStorage; every access is guarded.

export type Sfx = "step" | "chest" | "coin" | "hit" | "shoot" | "spell" | "bonus" | "win" | "lose" | "day" | "click";

const KEY = "magic.sound";
let ctx: AudioContext | null = null;

export function soundOn(): boolean {
  try {
    return localStorage.getItem(KEY) !== "off";
  } catch {
    return true;
  }
}

export function setSoundOn(on: boolean): void {
  try {
    localStorage.setItem(KEY, on ? "on" : "off");
  } catch {
    /* storage blocked: the choice lasts this session only */
  }
  if (on) sfx("click");
}

function audio(): AudioContext | null {
  if (typeof window === "undefined") return null;
  try {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    ctx = ctx ?? new Ctor();
    if (ctx.state === "suspended") void ctx.resume();
    return ctx;
  } catch {
    return null;
  }
}

function tone(a: AudioContext, freq: number, at: number, dur: number, type: OscillatorType, vol: number, slide?: number) {
  const o = a.createOscillator();
  const g = a.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, a.currentTime + at);
  if (slide) o.frequency.exponentialRampToValueAtTime(slide, a.currentTime + at + dur);
  g.gain.setValueAtTime(0.0001, a.currentTime + at);
  g.gain.exponentialRampToValueAtTime(vol, a.currentTime + at + 0.01);
  g.gain.exponentialRampToValueAtTime(0.0001, a.currentTime + at + dur);
  o.connect(g).connect(a.destination);
  o.start(a.currentTime + at);
  o.stop(a.currentTime + at + dur + 0.02);
}

function noise(a: AudioContext, at: number, dur: number, vol: number) {
  const buf = a.createBuffer(1, Math.max(1, Math.floor(a.sampleRate * dur)), a.sampleRate);
  const d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length);
  const s = a.createBufferSource();
  const g = a.createGain();
  g.gain.value = vol;
  s.buffer = buf;
  s.connect(g).connect(a.destination);
  s.start(a.currentTime + at);
}

export function sfx(kind: Sfx): void {
  if (!soundOn()) return;
  const a = audio();
  if (!a) return;
  try {
    switch (kind) {
      case "step": noise(a, 0, 0.05, 0.08); break;
      case "click": tone(a, 660, 0, 0.06, "square", 0.04); break;
      case "coin": tone(a, 988, 0, 0.08, "square", 0.05); tone(a, 1319, 0.07, 0.14, "square", 0.05); break;
      case "chest": tone(a, 392, 0, 0.1, "triangle", 0.08); tone(a, 523, 0.09, 0.1, "triangle", 0.08); tone(a, 784, 0.18, 0.22, "triangle", 0.08); break;
      case "hit": noise(a, 0, 0.09, 0.22); tone(a, 140, 0, 0.12, "sawtooth", 0.06, 60); break;
      case "shoot": tone(a, 900, 0, 0.12, "triangle", 0.05, 300); break;
      case "spell": tone(a, 523, 0, 0.35, "sine", 0.06, 1047); tone(a, 784, 0.05, 0.35, "sine", 0.04, 1568); break;
      case "bonus": tone(a, 784, 0, 0.08, "triangle", 0.07); tone(a, 1175, 0.08, 0.16, "triangle", 0.07); break;
      case "day": tone(a, 330, 0, 0.5, "sine", 0.05, 494); tone(a, 494, 0.25, 0.5, "sine", 0.04, 659); break;
      case "win": [523, 659, 784, 1047].forEach((f, i) => tone(a, f, i * 0.12, 0.3, "triangle", 0.08)); break;
      case "lose": [392, 330, 262].forEach((f, i) => tone(a, f, i * 0.18, 0.35, "sine", 0.07)); break;
    }
  } catch {
    /* audio may be blocked until the first tap */
  }
}
