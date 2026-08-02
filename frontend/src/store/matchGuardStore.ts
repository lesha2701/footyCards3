import { create } from "zustand";

interface MatchGuardState {
  active: boolean;
  message: string;
  onLeave: (() => void) | null;
  pendingTo: string | null;
  activate: (message: string, onLeave?: () => void) => void;
  deactivate: () => void;
  requestNavigate: (to: string) => void;
  cancelNavigate: () => void;
}

/** Guards in-app navigation while an interactive match is in progress, so
 * players can't dodge a losing match by just switching tabs. `activate` is
 * called by the active match page; BottomNav/TopBar check `active` before
 * navigating and call `requestNavigate` instead, which surfaces a
 * confirmation dialog (rendered once in AppLayout) rather than navigating
 * immediately. */
export const useMatchGuardStore = create<MatchGuardState>((set, get) => ({
  active: false,
  message: "",
  onLeave: null,
  pendingTo: null,
  activate: (message, onLeave) => set({ active: true, message, onLeave: onLeave ?? null }),
  deactivate: () => set({ active: false, message: "", onLeave: null, pendingTo: null }),
  requestNavigate: (to) => {
    if (get().active) set({ pendingTo: to });
  },
  cancelNavigate: () => set({ pendingTo: null }),
}));
