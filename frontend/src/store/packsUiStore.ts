import { create } from "zustand";

import type { PackSortDirection } from "@/lib/packs";

interface PacksUiState {
  coinSortDirection: PackSortDirection;
  starsSortDirection: PackSortDirection;
  setCoinSortDirection: (direction: PackSortDirection) => void;
  setStarsSortDirection: (direction: PackSortDirection) => void;
}

export const usePacksUiStore = create<PacksUiState>((set) => ({
  coinSortDirection: "asc",
  starsSortDirection: "asc",
  setCoinSortDirection: (coinSortDirection) => set({ coinSortDirection }),
  setStarsSortDirection: (starsSortDirection) => set({ starsSortDirection }),
}));
