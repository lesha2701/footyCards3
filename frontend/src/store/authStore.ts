import { create } from "zustand";

import type { UserMe } from "@/types";

interface AuthState {
  user: UserMe | null;
  adminToken: string | null;
  isReady: boolean;
  setUser: (user: UserMe) => void;
  setAdminToken: (token: string | null) => void;
  setReady: (ready: boolean) => void;
  updateBalance: (balance: number) => void;
  reset: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  adminToken: null,
  isReady: false,
  setUser: (user) => set({ user }),
  setAdminToken: (adminToken) => set({ adminToken }),
  setReady: (isReady) => set({ isReady }),
  updateBalance: (balance) =>
    set((state) => (state.user ? { user: { ...state.user, balance } } : state)),
  reset: () => set({ user: null, adminToken: null, isReady: false }),
}));
