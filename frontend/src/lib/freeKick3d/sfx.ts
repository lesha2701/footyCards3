/** Free kick 3D sounds. The crowd is recorded (public/free-kick-3d/sfx,
 * loaded once the scene opens): a looping hum that swells while the ball
 * flies, chants while the kicker lines up (they fade the moment the shot
 * is decided), the goal roar, groans and laughter. The
 * strikes (kick, post, wall) are synthesized with Web Audio like the rest
 * of the app, and so is every crowd sound until its file is in. All muted
 * by the same «Звуки» switch. */
import { audio, soundEnabled } from "@/lib/sound";

export type FreeKickSfx = "kick" | "post" | "wall" | "net" | "roar" | "groan" | "laugh";

const BASE = "/free-kick-3d/sfx/";
const RECORDINGS = {
  roar: "goal-roar.mp3",
  net: "net.mp3",
  groan: "groan.mp3",
  laugh: "laugh.mp3",
  ambience: "ambience.mp3",
  chantSong: "chant-song.mp3",
  chantHey: "chant-hey.mp3",
} as const;
type Recording = keyof typeof RECORDINGS;

const recorded: Partial<Record<Recording, AudioBuffer>> = {};
let preloading: Promise<void> | null = null;

/** Fetch and decode the recordings (once); until they're in, the
 * synthesized versions play and the crowd is silent. */
export function preloadFreeKickSfx(): Promise<void> {
  preloading ??= (async () => {
    const ac = audio();
    if (!ac) return;
    await Promise.all(
      Object.entries(RECORDINGS).map(async ([name, file]) => {
        try {
          const data = await (await fetch(BASE + file)).arrayBuffer();
          recorded[name as Recording] = await ac.decodeAudioData(data);
        } catch {
          // Missing or undecodable: the synthesized sound stays.
        }
      }),
    );
  })();
  return preloading;
}

function playRecording(ac: AudioContext, buffer: AudioBuffer, volume: number, when = 0) {
  const src = ac.createBufferSource();
  src.buffer = buffer;
  const gain = ac.createGain();
  gain.gain.value = volume;
  src.connect(gain).connect(ac.destination);
  src.start(ac.currentTime + when);
  return { src, gain };
}

// ---------------------------------------------------------------------------
// The crowd: one looping hum for the whole scene plus chants on top.
// ---------------------------------------------------------------------------

const CALM = 0.32;
const TENSE = 0.6;
let crowd: { src: AudioBufferSourceNode; gain: GainNode } | null = null;
/** Chants still sounding (faded out by `crowdHush`). */
const chanting = new Set<{ src: AudioBufferSourceNode; gain: GainNode }>();
let chantTurn = 0;

/** Start the crowd hum (no-op if sound is off or it's already on);
 * returns the stop function. Waits for the recordings to load. */
export function startCrowd(): () => void {
  let stopped = false;
  void preloadFreeKickSfx().then(() => {
    const ac = audio();
    const buffer = recorded.ambience;
    if (stopped || crowd || !ac || !buffer || !soundEnabled()) return;
    const src = ac.createBufferSource();
    src.buffer = buffer;
    src.loop = true;
    // Skip the mp3 codec's padding at both ends, so the loop doesn't tick.
    src.loopStart = 0.05;
    src.loopEnd = buffer.duration - 0.05;
    const gain = ac.createGain();
    gain.gain.setValueAtTime(0.0001, ac.currentTime);
    gain.gain.exponentialRampToValueAtTime(CALM, ac.currentTime + 1.5);
    src.connect(gain).connect(ac.destination);
    src.start(ac.currentTime, 0.05);
    crowd = { src, gain };
  });
  return () => {
    stopped = true;
    if (!crowd) return;
    const { src, gain } = crowd;
    crowd = null;
    try {
      const now = audio()?.currentTime ?? 0;
      gain.gain.cancelScheduledValues(now);
      gain.gain.setTargetAtTime(0.0001, now, 0.2);
      src.stop(now + 1);
    } catch {
      // Already stopped.
    }
  };
}

/** The hum rises while the ball is in the air and settles afterwards. */
export function crowdTension(tense: boolean): void {
  const ac = audio();
  if (!crowd || !ac) return;
  crowd.gain.gain.cancelScheduledValues(ac.currentTime);
  crowd.gain.gain.setTargetAtTime(tense ? TENSE : CALM, ac.currentTime, tense ? 0.25 : 1.2);
}

/** The crowd gets behind the kicker: the song and «hey hey hey» take
 * turns. Waits for the recordings, so the first position isn't silent. */
export function crowdChant(): void {
  void preloadFreeKickSfx().then(() => {
    if (!soundEnabled()) return;
    try {
      const ac = audio();
      const chants = [recorded.chantSong, recorded.chantHey].filter((b): b is AudioBuffer => !!b);
      if (!ac || chants.length === 0) return;
      const node = playRecording(ac, chants[chantTurn++ % chants.length], 0.75, 0.4);
      chanting.add(node);
      node.src.onended = () => chanting.delete(node);
    } catch {
      // Audio is a nicety.
    }
  });
}

/** The shot is decided: whatever the crowd was chanting dies away, so the
 * roar or the groan has the stage (and no chant reads as applause). */
export function crowdHush(): void {
  const ac = audio();
  if (!ac) return;
  for (const node of chanting) {
    try {
      node.gain.gain.cancelScheduledValues(ac.currentTime);
      node.gain.gain.setTargetAtTime(0.0001, ac.currentTime, 0.15);
      node.src.stop(ac.currentTime + 0.8);
    } catch {
      // Already over.
    }
  }
  chanting.clear();
}

// ---------------------------------------------------------------------------
// Synthesized strikes (and the fallbacks for the crowd).
// ---------------------------------------------------------------------------

let noiseBuffer: AudioBuffer | null = null;

function noise(ac: AudioContext): AudioBuffer {
  if (noiseBuffer && noiseBuffer.sampleRate === ac.sampleRate) return noiseBuffer;
  const buf = ac.createBuffer(1, ac.sampleRate * 3, ac.sampleRate);
  const data = buf.getChannelData(0);
  for (let i = 0; i < data.length; i++) data[i] = Math.random() * 2 - 1;
  noiseBuffer = buf;
  return buf;
}

/** Noise through a band-pass filter with an attack/hold/release envelope. */
function burst(
  ac: AudioContext,
  { freq, q, attack, hold, release, volume, sweepTo }: {
    freq: number; q: number; attack: number; hold: number; release: number; volume: number; sweepTo?: number;
  },
) {
  const now = ac.currentTime;
  const src = ac.createBufferSource();
  src.buffer = noise(ac);
  const filter = ac.createBiquadFilter();
  filter.type = "bandpass";
  filter.Q.value = q;
  filter.frequency.setValueAtTime(freq, now);
  if (sweepTo) filter.frequency.exponentialRampToValueAtTime(sweepTo, now + attack + hold + release);
  const gain = ac.createGain();
  gain.gain.setValueAtTime(0.0001, now);
  gain.gain.exponentialRampToValueAtTime(volume, now + attack);
  gain.gain.setValueAtTime(volume, now + attack + hold);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + attack + hold + release);
  src.connect(filter).connect(gain).connect(ac.destination);
  src.start(now);
  src.stop(now + attack + hold + release + 0.05);
}

function thump(ac: AudioContext, from: number, to: number, length: number, volume: number) {
  const now = ac.currentTime;
  const osc = ac.createOscillator();
  const gain = ac.createGain();
  osc.type = "sine";
  osc.frequency.setValueAtTime(from, now);
  osc.frequency.exponentialRampToValueAtTime(to, now + length);
  gain.gain.setValueAtTime(volume, now);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + length);
  osc.connect(gain).connect(ac.destination);
  osc.start(now);
  osc.stop(now + length + 0.05);
}

function ping(ac: AudioContext, freq: number, length: number, volume: number) {
  const now = ac.currentTime;
  const osc = ac.createOscillator();
  const gain = ac.createGain();
  osc.type = "triangle";
  osc.frequency.setValueAtTime(freq, now);
  gain.gain.setValueAtTime(volume, now);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + length);
  osc.connect(gain).connect(ac.destination);
  osc.start(now);
  osc.stop(now + length + 0.05);
}

export function playFreeKickSfx(name: FreeKickSfx): void {
  if (!soundEnabled()) return;
  try {
    const ac = audio();
    if (!ac) return;
    switch (name) {
      case "kick":
        thump(ac, 140, 45, 0.18, 0.5);
        burst(ac, { freq: 2500, q: 0.8, attack: 0.003, hold: 0.01, release: 0.06, volume: 0.25 });
        break;
      case "post":
        ping(ac, 1850, 0.9, 0.12);
        ping(ac, 2790, 0.6, 0.07);
        thump(ac, 220, 90, 0.12, 0.3);
        break;
      case "wall":
        thump(ac, 110, 40, 0.16, 0.45);
        burst(ac, { freq: 600, q: 1, attack: 0.005, hold: 0.02, release: 0.12, volume: 0.15 });
        break;
      case "net":
        if (recorded.net) playRecording(ac, recorded.net, 0.8);
        else burst(ac, { freq: 3200, q: 0.6, attack: 0.01, hold: 0.05, release: 0.35, volume: 0.18, sweepTo: 1200 });
        break;
      case "roar":
        if (recorded.roar) {
          playRecording(ac, recorded.roar, 0.9);
          break;
        }
        burst(ac, { freq: 700, q: 0.5, attack: 0.25, hold: 1.2, release: 1.4, volume: 0.22 });
        burst(ac, { freq: 1800, q: 0.7, attack: 0.3, hold: 1, release: 1.2, volume: 0.08 });
        break;
      case "laugh":
        if (recorded.laugh) playRecording(ac, recorded.laugh, 0.6);
        else burst(ac, { freq: 520, q: 1.2, attack: 0.15, hold: 0.5, release: 0.9, volume: 0.16, sweepTo: 260 });
        break;
      case "groan":
        if (recorded.groan) playRecording(ac, recorded.groan, 0.75);
        else burst(ac, { freq: 520, q: 1.2, attack: 0.15, hold: 0.5, release: 0.9, volume: 0.16, sweepTo: 260 });
        break;
    }
  } catch {
    // Audio is a nicety; never break the game over it.
  }
}
