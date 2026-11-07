import { createContext, useCallback, useContext } from "react";
import { useSearchParams } from "react-router-dom";

import type { ClubSheetKey } from "@/lib/clubTabs";

export const ClubSheetContext = createContext<{ close: () => void } | null>(null);

/** Set while a club section is shown inside the sheet over the club home. */
export function useClubSheetContext() {
  return useContext(ClubSheetContext);
}

/** Opens a section over the club home, keeping the current tab. A history
 * entry of its own, so the back button closes the sheet. */
export function useOpenClubSheet() {
  const [, setParams] = useSearchParams();
  return useCallback((sheet: ClubSheetKey | "trophies") => {
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set("sheet", sheet);
      return next;
    });
  }, [setParams]);
}
