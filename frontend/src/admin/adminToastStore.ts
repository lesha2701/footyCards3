import { create } from "zustand";

export interface AdminToast {
  id: number;
  message: string;
  kind: "success" | "error";
}

interface AdminToastState {
  toasts: AdminToast[];
  push: (message: string, kind: AdminToast["kind"]) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;

export const useAdminToastStore = create<AdminToastState>((set) => ({
  toasts: [],
  push: (message, kind) => {
    const id = nextId++;
    set((state) => ({ toasts: [...state.toasts, { id, message, kind }] }));
  },
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) })),
}));
