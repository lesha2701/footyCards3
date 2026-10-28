/** Free kick 3D sounds: synthesized with Web Audio like the rest of the
 * app, except the crowd's goal roar, a recording (public/free-kick-3d/sfx,
 * loaded once the scene opens). Muted by the same «Звуки» switch. */
import { audio, soundEnabled } from "@/lib/sound";

export type FreeKickSfx = "kick" | "post" | "wall" | "net" | "roar" | "groan";

const RECORDINGS = { roar: "/free-kick-3d/sfx/goal-roar.mp3" } as const;
const recorded: Partial<Record<keyof typeof RECORDINGS, AudioBuffer>> = {};
let preloading: Promise<void> | null = null;

/** Fetch and decode the recordings (once); until they're in, the
 * synthesized versions play. */
export function preloadFreeKickSfx(): Promise<void> {
  preloading ??= (async () => {
    const ac = audio();
    if (!ac) return;
    await Promise.all(
      Object.entries(RECORDINGS).map(async ([name, url]) => {
        try {
          const data = await (await fetch(url)).arrayBuffer();
          recorded[name as keyof typeof RECORDINGS] = await ac.decodeAudioData(data);
        } catch {
          // Missing or undecodable: the synthesized sound stays.
        }
      }),
    );
  })();
  return preloading;
}

function playRecording(ac: AudioContext, buffer: AudioBuffer, volume: number) {
  const src = ac.createBufferSource();
  src.buffer = buffer;
  const gain = ac.createGain();
  gain.gain.value = volume;
  src.connect(gain).connect(ac.destination);
  src.start();
}

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
        burst(ac, { freq: 3200, q: 0.6, attack: 0.01, hold: 0.05, release: 0.35, volume: 0.18, sweepTo: 1200 });
        break;
      case "roar":
        if (recorded.roar) {
          playRecording(ac, recorded.roar, 0.9);
          break;
        }
        burst(ac, { freq: 700, q: 0.5, attack: 0.25, hold: 1.2, release: 1.4, volume: 0.22 });
        burst(ac, { freq: 1800, q: 0.7, attack: 0.3, hold: 1, release: 1.2, volume: 0.08 });
        break;
      case "groan":
        burst(ac, { freq: 520, q: 1.2, attack: 0.15, hold: 0.5, release: 0.9, volume: 0.16, sweepTo: 260 });
        break;
    }
  } catch {
    // Audio is a nicety; never break the game over it.
  }
}
