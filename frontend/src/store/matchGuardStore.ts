import { create } from "zustand";

interface MatchGuardState {
  active: boolean;
  message: string;
  onLeave: (() => void) | null;
  forfeitPath: string | null;
  pendingTo: string | null;
  activate: (message: string, onLeave?: () => void, forfeitPath?: string) => void;
  deactivate: () => void;
  requestNavigate: (to: string) => void;
  cancelNavigate: () => void;
}

/** Guards in-app navigation while an interactive match is in progress, so
 * players can't dodge a losing match by just switching tabs. `activate` is
 * called by the active match page; BottomNav/TopBar check `active` before
 * navigating and call `requestNavigate` instead, which surfaces a
 * confirmation dialog (rendered once in AppLayout) rather than navigating
 * immediately.
 *
 * `forfeitPath` is the same forfeit endpoint `onLeave` calls, kept as a plain
 * path (rather than only a closure) so AppLayout's `pagehide` handler can
 * fire it via `fetch(..., { keepalive: true })` when the page is actually
 * being torn down (real tab close/reload) — a normal axios call made from
 * `onLeave` there would get cut off before it reaches the network, letting
 * the loss silently go unrecorded. */
export const useMatchGuardStore = create<MatchGuardState>((set, get) => ({
  active: false,
  message: "",
  onLeave: null,
  forfeitPath: null,
  pendingTo: null,
  activate: (message, onLeave, forfeitPath) =>
    set({ active: true, message, onLeave: onLeave ?? null, forfeitPath: forfeitPath ?? null }),
  deactivate: () => set({ active: false, message: "", onLeave: null, forfeitPath: null, pendingTo: null }),
  requestNavigate: (to) => {
    if (get().active) set({ pendingTo: to });
  },
  cancelNavigate: () => set({ pendingTo: null }),
}));
