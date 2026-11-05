import { create } from "zustand";

/** What an admin chose for a Stars purchase: pay as everyone does, or the
 * outcome of taking it free (AdminPaySheet). */
export type AdminPayChoice = "pay" | "paid" | "gifted" | "cancelled";

interface AdminPayState {
  /** The pending invoice the sheet is open for. */
  token: string | null;
  resolve: ((choice: AdminPayChoice) => void) | null;
  ask: (token: string) => Promise<AdminPayChoice>;
  close: (choice: AdminPayChoice) => void;
}

export const useAdminPayStore = create<AdminPayState>((set, get) => ({
  token: null,
  resolve: null,
  ask: (token) => new Promise((resolve) => set({ token, resolve })),
  close: (choice) => {
    get().resolve?.(choice);
    set({ token: null, resolve: null });
  },
}));
