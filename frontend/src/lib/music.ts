/** Background music of the menus: the instrumental «Campeones», looped.
 * Plays on menu / collection screens, pauses in games (they have their own
 * sounds), when the app is hidden, and with the «Музыка» switch off. Browsers
 * only start audio after a tap, so it waits for the first one. */
import menuTrack from "@/assets/music/menu.mp3";
import { audio } from "@/lib/sound";

const KEY = "fc.music";
const VOLUME_KEY = "fc.music.volume";
const DEFAULT_VOLUME = 0.35;
const FADE = 0.8;

let element: HTMLAudioElement | null = null;
let gain: GainNode | null = null;
let unlocked = false;
let routeAllowed = false;
let pauseTimer: ReturnType<typeof setTimeout> | null = null;

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* storage unavailable */
  }
}

export function musicEnabled(): boolean {
  return read(KEY) !== "off";
}

export function musicVolume(): number {
  const v = Number(read(VOLUME_KEY));
  return read(VOLUME_KEY) !== null && Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : DEFAULT_VOLUME;
}

export function setMusicEnabled(on: boolean): void {
  write(KEY, on ? "on" : "off");
  if (on) unlocked = true; // the switch itself is a tap
  sync();
}

export function setMusicVolume(v: number): void {
  write(VOLUME_KEY, String(v));
  ramp(musicVolume(), 0.1);
}

/** Whether the current screen wants the menu music. */
export function setMusicRoute(allowed: boolean): void {
  routeAllowed = allowed;
  sync();
}

/** Screens with their own sounds (games, pack opening) and the admin panel. */
export function isMusicRoute(pathname: string): boolean {
  if (pathname.startsWith("/admin")) return false;
  if (pathname.startsWith("/play/")) return false;
  if (/^\/packs\/[^/]+\/open/.test(pathname)) return false;
  if (pathname.startsWith("/newbie")) return false;
  return true;
}

function ensure(): HTMLAudioElement | null {
  if (element) return element;
  if (typeof Audio === "undefined") return null;
  element = new Audio(menuTrack);
  element.loop = true;
  element.preload = "auto";
  try {
    const ac = audio();
    if (ac) {
      gain = ac.createGain();
      gain.gain.value = 0;
      ac.createMediaElementSource(element).connect(gain).connect(ac.destination);
    }
  } catch {
    gain = null; // iOS without Web Audio: fall back to element.volume
  }
  if (!gain) element.volume = 0;
  return element;
}

function ramp(target: number, seconds: number): void {
  if (gain) {
    const ac = gain.context;
    gain.gain.cancelScheduledValues(ac.currentTime);
    gain.gain.setValueAtTime(gain.gain.value, ac.currentTime);
    gain.gain.linearRampToValueAtTime(target, ac.currentTime + seconds);
  } else if (element) {
    element.volume = target;
  }
}

function shouldPlay(): boolean {
  return unlocked && routeAllowed && musicEnabled() && document.visibilityState === "visible";
}

function sync(): void {
  if (typeof document === "undefined") return;
  if (shouldPlay()) {
    const el = ensure();
    if (!el) return;
    if (pauseTimer) clearTimeout(pauseTimer);
    pauseTimer = null;
    audio(); // resume the context after a tap
    if (el.paused) void el.play().catch(() => { /* blocked until the next tap */ });
    ramp(musicVolume(), FADE);
  } else if (element && !element.paused) {
    ramp(0, FADE / 2);
    if (pauseTimer) clearTimeout(pauseTimer);
    pauseTimer = setTimeout(() => {
      pauseTimer = null;
      if (!shouldPlay()) element?.pause();
    }, (FADE / 2) * 1000 + 50);
  }
}

let installed = false;
/** Listens for the first tap and app hide / show; safe to call many times. */
export function installMusic(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const unlock = () => {
    unlocked = true;
    sync();
    if (element && !element.paused) {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    }
  };
  window.addEventListener("pointerdown", unlock);
  window.addEventListener("keydown", unlock);
  document.addEventListener("visibilitychange", sync);
}
