import { useEffect, useRef } from "react";

/** «Сегодня в клубе» → straight to the action: a tip carries a `target`;
 * `goTo(target)` tells the mounted tabs (each opens its own sub-section via
 * `useFocusTarget`), then scrolls to `[data-focus="<target>"]` once it shows
 * up and lights it for a moment. */

type Listener = (target: string) => void;

const listeners = new Set<Listener>();
let pending: string | null = null;
let timer: number | undefined;

const FLASH = ["ring-2", "ring-accent-lime", "ring-offset-2", "ring-offset-bg-base", "transition-shadow"];
const WAIT_MS = 3000;
const STEP_MS = 80;

function find(target: string): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-focus="${CSS.escape(target)}"]`);
}

function flash(el: HTMLElement) {
  el.scrollIntoView({ behavior: "smooth", block: "center" });
  el.classList.add(...FLASH);
  window.setTimeout(() => el.classList.remove(...FLASH), 2200);
}

function poll(target: string, started: number) {
  window.clearTimeout(timer);
  const el = find(target);
  if (el) {
    pending = null;
    flash(el);
    return;
  }
  if (Date.now() - started > WAIT_MS) {
    pending = null;
    return;
  }
  timer = window.setTimeout(() => poll(target, started), STEP_MS);
}

export function goTo(target?: string | null) {
  if (!target) return;
  pending = target;
  listeners.forEach((l) => l(target));
  poll(target, Date.now());
}

/** A tab with sub-sections opens the one that holds `target` (also when it
 * mounts right after the tab switch). */
export function useFocusTarget(onTarget: Listener) {
  const ref = useRef(onTarget);
  ref.current = onTarget;
  useEffect(() => {
    const l: Listener = (t) => ref.current(t);
    listeners.add(l);
    if (pending) l(pending);
    return () => {
      listeners.delete(l);
    };
  }, []);
}

/** `?go=<tab>:<target>` from the home tile. */
export function parseGo(search: string): { tab: string; target?: string } | null {
  const go = new URLSearchParams(search).get("go");
  if (!go) return null;
  const [tab, target] = go.split(":");
  return tab ? { tab, target: target || undefined } : null;
}
