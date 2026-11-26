/** Music of «Campeones»: on launch the original with vocals (its choir
 * intro), handed over in the instrumental gap to the menu instrumental, which
 * then loops; the choir sings on wins and legendary pulls.
 * The menu music plays on menu / collection screens and pauses in games
 * (they have their own sounds), when the app is hidden and with the «Музыка»
 * switch off. Browsers only start audio after a tap, so it waits for one. */
import choirTrack from "@/assets/music/choir.mp3";
import introTrack from "@/assets/music/intro.mp3";
import menuTrack from "@/assets/music/menu.mp3";
import { audio } from "@/lib/sound";

const KEY = "fc.music";
const VOLUME_KEY = "fc.music.volume";
const DEFAULT_VOLUME = 0.35;
const FADE = 0.8;
/** Where the intro hands over to the instrumental: the gap after the choir. */
const HANDOVER_AT = 42;
const HANDOVER_FADE = 2.5;
/** The instrumental runs this far ahead of the original mix. */
const MENU_OFFSET = 0.028;
/** How much the menu music steps back while the choir sings. */
const DUCK = 0.25;

interface Channel {
  el: HTMLAudioElement;
  gain: GainNode | null;
  level: number;
}

let menu: Channel | null = null;
let intro: Channel | null = null;
let choir: Channel | null = null;
/** The intro plays once per launch; after that only the instrumental. */
let introDone = false;
let unlocked = false;
let routeAllowed = false;
let ducked = false;
let pauseTimer: ReturnType<typeof setTimeout> | null = null;
let duckTimer: ReturnType<typeof setTimeout> | null = null;

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
  const raw = read(VOLUME_KEY);
  const v = Number(raw);
  return raw !== null && Number.isFinite(v) ? Math.min(1, Math.max(0, v)) : DEFAULT_VOLUME;
}

export function setMusicEnabled(on: boolean): void {
  write(KEY, on ? "on" : "off");
  if (on) unlocked = true; // the switch itself is a tap
  sync();
}

export function setMusicVolume(v: number): void {
  write(VOLUME_KEY, String(v));
  sync(0.1);
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

function channel(src: string, loop: boolean): Channel | null {
  if (typeof Audio === "undefined") return null;
  const el = new Audio(src);
  el.loop = loop;
  el.preload = "auto";
  let gain: GainNode | null = null;
  try {
    const ac = audio();
    if (ac) {
      gain = ac.createGain();
      gain.gain.value = 0;
      ac.createMediaElementSource(el).connect(gain).connect(ac.destination);
    }
  } catch {
    gain = null; // no Web Audio: fall back to el.volume
  }
  if (!gain) el.volume = 0;
  return { el, gain, level: 0 };
}

function ramp(ch: Channel, target: number, seconds: number): void {
  ch.level = target;
  if (ch.gain) {
    const ac = ch.gain.context;
    ch.gain.gain.cancelScheduledValues(ac.currentTime);
    ch.gain.gain.setValueAtTime(ch.gain.gain.value, ac.currentTime);
    ch.gain.gain.linearRampToValueAtTime(target, ac.currentTime + seconds);
  } else {
    ch.el.volume = Math.min(1, target);
  }
}

function play(ch: Channel): void {
  audio(); // resume the context after a tap
  if (!ch.el.paused) return;
  try {
    void ch.el.play()?.catch(() => { /* blocked until the next tap */ });
  } catch {
    /* no media playback here */
  }
}

function shouldPlay(): boolean {
  return unlocked && routeAllowed && musicEnabled() && document.visibilityState === "visible";
}

function background(): number {
  return musicVolume() * (ducked ? DUCK : 1);
}

/** The intro's clock: hand over to the instrumental at the same moment. */
function onIntroTime(): void {
  if (!intro || introDone || intro.el.currentTime < HANDOVER_AT) return;
  introDone = true;
  menu = menu ?? channel(menuTrack, true);
  if (!menu) return;
  menu.el.currentTime = intro.el.currentTime + MENU_OFFSET;
  play(menu);
  ramp(menu, background(), HANDOVER_FADE);
  ramp(intro, 0, HANDOVER_FADE);
  const finished = intro;
  setTimeout(() => finished.el.pause(), HANDOVER_FADE * 1000 + 100);
}

function sync(fade = FADE): void {
  if (typeof document === "undefined") return;
  if (shouldPlay()) {
    if (pauseTimer) clearTimeout(pauseTimer);
    pauseTimer = null;
    if (!introDone) {
      if (!intro) {
        intro = channel(introTrack, false);
        intro?.el.addEventListener("timeupdate", onIntroTime);
        intro?.el.addEventListener("ended", () => { introDone = true; sync(); });
      }
      if (intro) {
        play(intro);
        ramp(intro, background(), fade);
        return;
      }
      introDone = true;
    }
    menu = menu ?? channel(menuTrack, true);
    if (!menu) return;
    play(menu);
    ramp(menu, background(), fade);
  } else {
    const playing = [intro, menu].filter((ch): ch is Channel => !!ch && !ch.el.paused);
    if (!playing.length) return;
    for (const ch of playing) ramp(ch, 0, FADE / 2);
    if (pauseTimer) clearTimeout(pauseTimer);
    pauseTimer = setTimeout(() => {
      pauseTimer = null;
      if (!shouldPlay()) for (const ch of playing) ch.el.pause();
    }, (FADE / 2) * 1000 + 50);
  }
}

/** The «Campeones» choir — a win, a legendary card. The menu music steps
 * back while it sings; a second call restarts it rather than overlapping. */
export function playChoir(): void {
  if (!musicEnabled() || typeof document === "undefined") return;
  unlocked = true; // a win / a reveal always follows a tap
  choir = choir ?? channel(choirTrack, false);
  if (!choir) return;
  choir.el.currentTime = 0;
  ramp(choir, Math.min(1, musicVolume() * 1.6), 0.05);
  play(choir);
  ducked = true;
  sync(0.4);
  if (duckTimer) clearTimeout(duckTimer);
  duckTimer = setTimeout(() => {
    ducked = false;
    sync(1.5);
  }, 9500);
}

let installed = false;
/** Listens for the first tap and app hide / show; safe to call many times. */
export function installMusic(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;
  const unlock = () => {
    unlocked = true;
    sync();
    const ch = introDone ? menu : intro;
    if (ch && !ch.el.paused) {
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
    }
  };
  window.addEventListener("pointerdown", unlock);
  window.addEventListener("keydown", unlock);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") choir?.el.pause();
    sync();
  });
}
