/** «Где проводят время»: active seconds per section of the app, for the
 * admin report. Time counts only while the page is visible and the player
 * touched something in the last IDLE_MS; what is counted goes to the server
 * once a minute and when the page goes away — one small request a minute,
 * never one per screen. */

export const TICK_MS = 5_000;
export const IDLE_MS = 90_000;
export const FLUSH_MS = 60_000;
// A tick that arrives late (a frozen tab, a sleeping phone) counts no more than this.
const MAX_TICK_MS = 10_000;

const SEGMENT = /^[a-z0-9-]{1,19}$/;

/** "/" → "home", "/play/penalty/matches/5" → "play/penalty", "/clubs/war" →
 * "clubs", "/packs/3/open" → "packs". The admin panel is not counted (null). */
export function sectionOf(pathname: string): string | null {
  const parts = pathname.toLowerCase().split("/").filter(Boolean);
  if (parts.length === 0) return "home";
  if (parts[0] === "admin") return null;
  if (!SEGMENT.test(parts[0])) return "other";
  if (parts[0] === "play" && parts[1] && SEGMENT.test(parts[1])) return `play/${parts[1]}`;
  return parts[0];
}

export class SectionClock {
  private acc: Record<string, number> = {};
  private section: string | null;
  private lastTick: number;
  private lastInput: number;

  constructor(section: string | null, now: number) {
    this.section = section;
    this.lastTick = now;
    this.lastInput = now;
  }

  /** Counts the time since the last tick for the current section, if the
   * page was visible during it and the player wasn't idle. */
  tick(now: number, visible: boolean): void {
    const dt = Math.min(Math.max(0, now - this.lastTick), MAX_TICK_MS);
    if (visible && this.section && now - this.lastInput < IDLE_MS) {
      this.acc[this.section] = (this.acc[this.section] ?? 0) + dt;
    }
    this.lastTick = now;
  }

  setSection(section: string | null, now: number, visible: boolean): void {
    this.tick(now, visible);
    this.section = section;
  }

  input(now: number, visible: boolean): void {
    this.tick(now, visible);
    this.lastInput = now;
  }

  /** Whole seconds counted so far; the fractions stay for the next batch. */
  take(): Record<string, number> {
    const out: Record<string, number> = {};
    for (const [key, ms] of Object.entries(this.acc)) {
      const seconds = Math.floor(ms / 1000);
      if (seconds > 0) out[key] = seconds;
      this.acc[key] = ms - seconds * 1000;
    }
    return out;
  }
}
