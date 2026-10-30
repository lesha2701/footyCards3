/** Small UI sounds synthesized with Web Audio (no audio files to load).
 * Off with the «Звуки» switch in the profile (stored per device). */
type SoundName = "reveal" | "rare" | "reward" | "tap" | "goal" | "concede" | "whistle";

const KEY = "fc.sound";
let ctx: AudioContext | null = null;

export function soundEnabled(): boolean {
  try {
    return localStorage.getItem(KEY) !== "off";
  } catch {
    return true;
  }
}

export function setSoundEnabled(on: boolean): void {
  try {
    localStorage.setItem(KEY, on ? "on" : "off");
  } catch {
    /* storage unavailable */
  }
}

function audio(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  ctx = ctx ?? new Ctor();
  if (ctx.state === "suspended") void ctx.resume();
  return ctx;
}

function tone(ac: AudioContext, freq: number, start: number, length: number, type: OscillatorType, volume: number) {
  const osc = ac.createOscillator();
  const gain = ac.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, ac.currentTime + start);
  gain.gain.setValueAtTime(0.0001, ac.currentTime + start);
  gain.gain.exponentialRampToValueAtTime(volume, ac.currentTime + start + 0.015);
  gain.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + start + length);
  osc.connect(gain).connect(ac.destination);
  osc.start(ac.currentTime + start);
  osc.stop(ac.currentTime + start + length + 0.05);
}

const PATTERNS: Record<SoundName, [number, number, number, OscillatorType, number][]> = {
  // [frequency, start, length, wave, volume]
  tap: [[660, 0, 0.06, "triangle", 0.05]],
  reveal: [[523, 0, 0.12, "triangle", 0.07], [784, 0.08, 0.16, "triangle", 0.06]],
  rare: [[523, 0, 0.14, "triangle", 0.08], [659, 0.1, 0.14, "triangle", 0.08], [784, 0.2, 0.14, "triangle", 0.08], [1047, 0.3, 0.4, "sine", 0.09]],
  reward: [[784, 0, 0.1, "square", 0.035], [1175, 0.09, 0.22, "square", 0.035]],
  // Match view: my goal (a rising fanfare), the opponent's, the final whistle.
  goal: [[392, 0, 0.12, "square", 0.035], [523, 0.1, 0.12, "square", 0.035], [659, 0.2, 0.12, "square", 0.035], [784, 0.3, 0.5, "triangle", 0.08]],
  concede: [[330, 0, 0.2, "triangle", 0.06], [247, 0.16, 0.34, "triangle", 0.06]],
  whistle: [[2750, 0, 0.16, "sine", 0.035], [2750, 0.22, 0.12, "sine", 0.035], [2750, 0.4, 0.55, "sine", 0.035]],
};

export function playSound(name: SoundName): void {
  if (!soundEnabled()) return;
  try {
    const ac = audio();
    if (!ac) return;
    for (const [f, s, l, w, v] of PATTERNS[name]) tone(ac, f, s, l, w, v);
  } catch {
    /* audio unavailable — sounds are optional */
  }
}
