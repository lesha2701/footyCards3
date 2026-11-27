/** The game's soundtrack: «Campeones» opens every launch, then the rest of
 * the playlist in a shuffled order, one track handing over to the next with a
 * crossfade; the «Campeones» choir sings on wins and legendary pulls.
 * The music plays on menu / collection screens and pauses in games (they have
 * their own sounds), when the app is hidden, on the player's ⏸ and with the
 * «Музыка» switch off. Browsers only start audio after a tap, so it waits for
 * one. Tracks load one at a time, when they are about to play. */
import choirTrack from "@/assets/music/choir.mp3";
import { audio } from "@/lib/sound";

/** Shown in «Сейчас играет»; a file in assets/music/playlist/<key>.mp3. */
const TITLES: Record<string, string> = {
  campeones: "Campeones",
  bajo_la_luna: "Bajo la Luna",
  hearts_in_motion: "Hearts in Motion",
  mi_chico_baila_conmigo: "Mi Chico Baila Conmigo",
  move_as_one: "Move as One",
  one_heart_one_sky: "One Heart, One Sky",
  stadium_serenity: "Stadium Serenity",
  triumph_in_the_net: "Triumph in the Net",
};
const OPENER = "campeones";

const FILES = import.meta.glob("../assets/music/playlist/*.mp3", { eager: true, query: "?url", import: "default" }) as Record<string, string>;

export interface Track {
  key: string;
  title: string;
  url: string;
}

export const TRACKS: Track[] = Object.entries(FILES).map(([path, url]) => {
  const key = path.split("/").pop()!.replace(/\.mp3$/, "");
  return { key, title: TITLES[key] ?? key.replace(/_/g, " "), url };
});

const KEY = "fc.music";
const VOLUME_KEY = "fc.music.volume";
const DEFAULT_VOLUME = 0.35;
const FADE = 0.8;
/** The overlap of two tracks at a handover. */
const CROSSFADE = 3;
/** How much the music steps back while the choir sings. */
const DUCK = 0.25;

interface Channel {
  el: HTMLAudioElement;
  gain: GainNode | null;
}

/** Two decks: the current track and the next one fading in. */
let decks: [Channel, Channel] | null = null;
let live = 0;
let current: Track | null = null;
let queue: Track[] = [];
let choir: Channel | null = null;
let unlocked = false;
let routeAllowed = false;
let userPaused = false;
let ducked = false;
let handingOver = false;
let pauseTimer: ReturnType<typeof setTimeout> | null = null;
let duckTimer: ReturnType<typeof setTimeout> | null = null;

// ---- settings ------------------------------------------------------------

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
  if (on) {
    unlocked = true; // the switch itself is a tap
    userPaused = false;
  }
  sync();
}

export function setMusicVolume(v: number): void {
  write(VOLUME_KEY, String(v));
  sync(0.1);
}

// ---- state for the UI ----------------------------------------------------

export interface MusicState {
  track: Track | null;
  playing: boolean;
}

let state: MusicState = { track: null, playing: false };
const listeners = new Set<() => void>();

function emit(): void {
  const playing = !!decks && !decks[live].el.paused && !userPaused;
  if (state.track === current && state.playing === playing) return;
  state = { track: current, playing };
  listeners.forEach((l) => l());
}

export function subscribeMusic(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function musicState(): MusicState {
  return state;
}

// ---- playback ------------------------------------------------------------

/** Whether the current screen wants the music. */
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

function channel(loop: boolean, src?: string): Channel | null {
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
  return { el, gain };
}

function ramp(ch: Channel, target: number, seconds: number): void {
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

function shuffled(tracks: Track[]): Track[] {
  const out = [...tracks];
  for (let i = out.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [out[i], out[j]] = [out[j], out[i]];
  }
  return out;
}

/** The next track: «Campeones» first, then shuffled rounds, never the same twice in a row. */
function nextTrack(): Track | null {
  if (!TRACKS.length) return null;
  if (!current) return TRACKS.find((t) => t.key === OPENER) ?? TRACKS[0];
  if (!queue.length) {
    queue = shuffled(TRACKS);
    if (queue.length > 1 && queue[0].key === current.key) queue.push(queue.shift()!);
  }
  return queue.shift() ?? null;
}

function level(): number {
  return musicVolume() * (ducked ? DUCK : 1);
}

function ensureDecks(): [Channel, Channel] | null {
  if (decks) return decks;
  const a = channel(false);
  const b = channel(false);
  if (!a || !b) return null;
  decks = [a, b];
  for (const [i, ch] of decks.entries()) {
    ch.el.addEventListener("timeupdate", () => onTime(i));
    ch.el.addEventListener("ended", () => { if (i === live) advance(1); });
    ch.el.addEventListener("play", emit);
    ch.el.addEventListener("pause", emit);
  }
  return decks;
}

/** Near the end of the live track: hand over to the next one. */
function onTime(i: number): void {
  if (i !== live || handingOver || !decks) return;
  const el = decks[i].el;
  if (el.duration && el.duration - el.currentTime <= CROSSFADE) advance(CROSSFADE);
}

/** Start the next track on the other deck and crossfade to it. */
function advance(fade: number): void {
  const d = ensureDecks();
  const track = nextTrack();
  if (!d || !track) return;
  handingOver = true;
  const from = d[live];
  live = 1 - live;
  const to = d[live];
  current = track;
  to.el.src = track.url;
  to.el.currentTime = 0;
  if (shouldPlay()) {
    play(to);
    ramp(to, level(), fade);
  }
  ramp(from, 0, fade);
  setTimeout(() => {
    if (decks && decks[1 - live] === from) from.el.pause();
    handingOver = false;
  }, fade * 1000 + 100);
  emit();
}

function shouldPlay(): boolean {
  return unlocked && routeAllowed && !userPaused && musicEnabled() && document.visibilityState === "visible";
}

function sync(fade = FADE): void {
  if (typeof document === "undefined") return;
  if (shouldPlay()) {
    if (pauseTimer) clearTimeout(pauseTimer);
    pauseTimer = null;
    const d = ensureDecks();
    if (!d) return;
    if (!current) {
      advance(fade);
      return;
    }
    play(d[live]);
    ramp(d[live], level(), fade);
  } else if (decks && !decks[live].el.paused) {
    const playing = decks.filter((ch) => !ch.el.paused);
    for (const ch of playing) ramp(ch, 0, FADE / 2);
    if (pauseTimer) clearTimeout(pauseTimer);
    pauseTimer = setTimeout(() => {
      pauseTimer = null;
      if (!shouldPlay()) for (const ch of playing) ch.el.pause();
      emit();
    }, (FADE / 2) * 1000 + 50);
  }
  emit();
}

/** ⏯ in the player. */
export function toggleMusicPause(): void {
  userPaused = !userPaused;
  unlocked = true;
  sync(0.4);
}

/** ⏭ in the player. */
export function nextMusicTrack(): void {
  unlocked = true;
  userPaused = false;
  if (!musicEnabled()) return;
  advance(1);
}

/** The «Campeones» choir — a win, a legendary card. The music steps back
 * while it sings; a second call restarts it rather than overlapping. */
export function playChoir(): void {
  if (!musicEnabled() || typeof document === "undefined") return;
  unlocked = true; // a win / a reveal always follows a tap
  choir = choir ?? channel(false, choirTrack);
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
    if (decks && !decks[live].el.paused) {
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
